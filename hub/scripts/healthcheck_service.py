#!/usr/bin/env python3
import argparse
import json
import logging
import os
import pwd
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib import error, request

from dotenv import dotenv_values

LOGGER = logging.getLogger("inas-healthcheck")
STATE_VERSION = 1
COMPONENTS = ("hub", "mqtt", "network", "tunnel", "camera")
REBOOT_COMPONENTS = ("hub", "mqtt", "network", "tunnel")


@dataclass(frozen=True)
class HealthcheckConfig:
    instance: str
    env_file: Path
    work_dir: Path
    state_file: Path
    hub_port: int
    hub_service: str
    mqtt_service: str
    tunnel_service: str
    tunnel_ready_url: str
    network_interface: str
    network_connection: str
    external_host: str
    external_port: int
    camera_file: Path
    camera_check_enabled: bool
    tunnel_check_enabled: bool
    recovery_enabled: bool
    discord_enabled: bool
    discord_webhook_url: str
    failure_threshold: int
    network_manager_threshold: int
    reboot_threshold: int
    action_cooldown_seconds: int
    reboot_cooldown_seconds: int
    request_timeout_seconds: int
    heartbeat_interval_seconds: int
    boot_notification_enabled: bool
    boot_grace_seconds: int


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    detail: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RecoveryAction:
    name: str
    reason: str


def parse_bool(value, default=False):
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on"}


def parse_int(value, default, minimum=0):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def utc_now():
    return datetime.now(UTC)


def isoformat(value):
    return value.astimezone(UTC).isoformat(timespec="seconds")


def parse_datetime(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def env_file_home(env_file):
    try:
        return Path(pwd.getpwuid(env_file.stat().st_uid).pw_dir)
    except (KeyError, OSError):
        return Path.home()


def expand_config_path(value, home_dir):
    normalized = str(value or "").strip()
    if normalized == "~":
        return home_dir
    if normalized.startswith("~/"):
        return home_dir / normalized[2:]
    return Path(normalized).expanduser()


def load_config(args):
    env_file = Path(args.env_file).resolve()
    values = {key: str(value) for key, value in dotenv_values(env_file).items() if value is not None}
    home_dir = env_file_home(env_file)
    work_dir = expand_config_path(values.get("WORK_DIR", "~/.ina-device-hub"), home_dir)
    failure_threshold = parse_int(values.get("HEALTHCHECK_FAILURE_THRESHOLD"), 3, minimum=1)
    network_manager_threshold = max(
        failure_threshold + 1,
        parse_int(values.get("HEALTHCHECK_NETWORK_MANAGER_THRESHOLD"), 6, minimum=1),
    )
    reboot_threshold = parse_int(values.get("HEALTHCHECK_REBOOT_AFTER_FAILURES"), 0)
    if reboot_threshold:
        reboot_threshold = max(failure_threshold, reboot_threshold)
    return HealthcheckConfig(
        instance=args.instance,
        env_file=env_file,
        work_dir=work_dir,
        state_file=Path(args.state_dir) / f"{args.instance}.json",
        hub_port=parse_int(values.get("HUB_HTTP_PORT"), 39151, minimum=1),
        hub_service=f"inas-device-hub@{args.instance}.service",
        mqtt_service=values.get("HEALTHCHECK_MQTT_SERVICE", "mosquitto.service").strip() or "mosquitto.service",
        tunnel_service=values.get("HEALTHCHECK_TUNNEL_SERVICE", "inas-cloudflare-tunnel.service").strip() or "inas-cloudflare-tunnel.service",
        tunnel_ready_url=values.get("HEALTHCHECK_TUNNEL_READY_URL", "http://127.0.0.1:20241/ready").strip(),
        network_interface=values.get("HEALTHCHECK_NETWORK_INTERFACE", "wlan0").strip() or "wlan0",
        network_connection=values.get("HEALTHCHECK_NETWORK_CONNECTION", "").strip(),
        external_host=values.get("HEALTHCHECK_EXTERNAL_HOST", "archive-api.open-meteo.com").strip() or "archive-api.open-meteo.com",
        external_port=parse_int(values.get("HEALTHCHECK_EXTERNAL_PORT"), 443, minimum=1),
        camera_file=work_dir / ".camera_device_list.json",
        camera_check_enabled=parse_bool(values.get("HEALTHCHECK_CAMERA_ENABLED"), True),
        tunnel_check_enabled=parse_bool(values.get("HEALTHCHECK_TUNNEL_ENABLED"), True),
        recovery_enabled=parse_bool(values.get("HEALTHCHECK_RECOVERY_ENABLED"), True),
        discord_enabled=parse_bool(values.get("DISCORD_ENABLED"), True) and parse_bool(values.get("HEALTHCHECK_DISCORD_ENABLED"), True),
        discord_webhook_url=values.get("DISCORD_WEBHOOK_URL", "").strip(),
        failure_threshold=failure_threshold,
        network_manager_threshold=network_manager_threshold,
        reboot_threshold=reboot_threshold,
        action_cooldown_seconds=parse_int(values.get("HEALTHCHECK_ACTION_COOLDOWN_SECONDS"), 300, minimum=60),
        reboot_cooldown_seconds=parse_int(values.get("HEALTHCHECK_REBOOT_COOLDOWN_SECONDS"), 21600, minimum=3600),
        request_timeout_seconds=parse_int(values.get("HEALTHCHECK_REQUEST_TIMEOUT_SECONDS"), 5, minimum=1),
        heartbeat_interval_seconds=parse_int(values.get("HEALTHCHECK_HEARTBEAT_INTERVAL_SECONDS"), 21600, minimum=300),
        boot_notification_enabled=parse_bool(values.get("HEALTHCHECK_BOOT_NOTIFICATION_ENABLED"), True),
        boot_grace_seconds=parse_int(values.get("HEALTHCHECK_BOOT_GRACE_SECONDS"), 600, minimum=60),
    )


def empty_state():
    return {
        "version": STATE_VERSION,
        "components": {name: {"consecutive_failures": 0, "failure_started_at": ""} for name in COMPONENTS},
        "last_actions": {},
        "incident": None,
        "runtime": {
            "boot_id": "",
            "boot_notification_pending": False,
            "last_healthy_notification_at": "",
        },
    }


def load_state(path):
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty_state()
    except (OSError, json.JSONDecodeError):
        LOGGER.exception("Healthcheck state could not be loaded: %s", path)
        return empty_state()
    if not isinstance(document, dict) or document.get("version") != STATE_VERSION:
        return empty_state()
    document.setdefault("components", {})
    for name in COMPONENTS:
        document["components"].setdefault(name, {"consecutive_failures": 0, "failure_started_at": ""})
    document.setdefault("last_actions", {})
    document.setdefault("incident", None)
    runtime = document.setdefault("runtime", {})
    runtime.setdefault("boot_id", "")
    runtime.setdefault("boot_notification_pending", False)
    runtime.setdefault("last_healthy_notification_at", "")
    return document


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary_path.chmod(0o600)
    os.replace(temporary_path, path)


def update_component_state(state, checks, now, *, record_failures=True):
    now_text = isoformat(now)
    for name in COMPONENTS:
        component_state = state["components"][name]
        if checks[name].ok:
            component_state["consecutive_failures"] = 0
            component_state["failure_started_at"] = ""
            continue
        if not record_failures:
            continue
        component_state["consecutive_failures"] = int(component_state.get("consecutive_failures") or 0) + 1
        if not component_state.get("failure_started_at"):
            component_state["failure_started_at"] = now_text


def action_due(state, action_name, now, cooldown_seconds):
    last_action = parse_datetime(state.get("last_actions", {}).get(action_name))
    return last_action is None or (now - last_action).total_seconds() >= cooldown_seconds


def plan_recovery(config, state, checks, now):
    if not config.recovery_enabled:
        return []
    counts = {name: int(state["components"][name].get("consecutive_failures") or 0) for name in COMPONENTS}
    reboot_failures = [name for name in REBOOT_COMPONENTS if config.reboot_threshold and counts[name] >= config.reboot_threshold]
    if reboot_failures and action_due(state, "reboot_host", now, config.reboot_cooldown_seconds):
        reason = "; ".join(f"{name}: {checks[name].detail}" for name in reboot_failures)
        return [RecoveryAction("reboot_host", reason)]

    actions = []
    if counts["mqtt"] >= config.failure_threshold and action_due(state, "restart_mqtt_hub", now, config.action_cooldown_seconds):
        actions.append(RecoveryAction("restart_mqtt_hub", checks["mqtt"].detail))
    elif counts["hub"] >= config.failure_threshold and action_due(state, "restart_hub", now, config.action_cooldown_seconds):
        actions.append(RecoveryAction("restart_hub", checks["hub"].detail))

    if counts["network"] >= config.failure_threshold:
        if counts["network"] >= config.network_manager_threshold and action_due(state, "restart_network_manager", now, config.action_cooldown_seconds):
            actions.append(RecoveryAction("restart_network_manager", checks["network"].detail))
        elif action_due(state, "reconnect_wifi", now, config.action_cooldown_seconds):
            actions.append(RecoveryAction("reconnect_wifi", checks["network"].detail))
    elif counts["tunnel"] >= config.failure_threshold and action_due(state, "restart_tunnel", now, config.action_cooldown_seconds):
        actions.append(RecoveryAction("restart_tunnel", checks["tunnel"].detail))
    return actions


class HealthcheckService:
    def __init__(self, config, *, dry_run=False, command_runner=None, sleep=None):
        self.config = config
        self.dry_run = dry_run
        self.command_runner = command_runner or self._run_command
        self.sleep = sleep or time.sleep

    @staticmethod
    def _run_command(command, timeout=30):
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)

    def _http_json(self, url):
        http_request = request.Request(url, headers={"User-Agent": "ina-device-hub-healthcheck"})
        try:
            with request.urlopen(http_request, timeout=self.config.request_timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
                return response.status, json.loads(body)
        except error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8", errors="replace"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return exc.code, {}

    def _http_status(self, url):
        http_request = request.Request(url, headers={"User-Agent": "ina-device-hub-healthcheck"})
        try:
            with request.urlopen(http_request, timeout=self.config.request_timeout_seconds) as response:
                response.read(1)
                return response.status
        except error.HTTPError as exc:
            return exc.code

    def probe_hub(self):
        url = f"http://127.0.0.1:{self.config.hub_port}/readyz"
        try:
            status, payload = self._http_json(url)
        except Exception as exc:
            detail = f"local readyz unavailable: {type(exc).__name__}"
            return CheckResult(False, detail), CheckResult(False, detail)
        ready_checks = payload.get("checks") if isinstance(payload, dict) else {}
        ready_checks = ready_checks if isinstance(ready_checks, dict) else {}
        web_ok = bool(ready_checks.get("web"))
        mqtt_ok = bool(ready_checks.get("mqtt"))
        hub_ok = status in {200, 503} and web_ok
        return (
            CheckResult(hub_ok, f"readyz status={status} web={web_ok}"),
            CheckResult(mqtt_ok, f"readyz status={status} mqtt={mqtt_ok}"),
        )

    def default_gateway(self):
        result = self.command_runner(["ip", "-4", "route", "show", "default", "dev", self.config.network_interface], timeout=10)
        if result.returncode != 0:
            return ""
        words = result.stdout.split()
        try:
            return words[words.index("via") + 1]
        except (ValueError, IndexError):
            return ""

    def probe_network(self):
        gateway = self.default_gateway()
        if not gateway:
            return CheckResult(False, f"no default gateway on {self.config.network_interface}")
        ping = self.command_runner(["ping", "-c", "1", "-W", "2", gateway], timeout=5)
        if ping.returncode != 0:
            return CheckResult(False, f"gateway {gateway} unreachable")
        try:
            addresses = socket.getaddrinfo(self.config.external_host, self.config.external_port, type=socket.SOCK_STREAM)
        except OSError as exc:
            return CheckResult(False, f"DNS failed for {self.config.external_host}: {type(exc).__name__}")
        last_error = ""
        for family, socket_type, protocol, _, socket_address in addresses:
            connection = None
            try:
                connection = socket.socket(family, socket_type, protocol)
                connection.settimeout(self.config.request_timeout_seconds)
                connection.connect(socket_address)
                return CheckResult(True, f"gateway={gateway} external={self.config.external_host}:{self.config.external_port}")
            except OSError as exc:
                last_error = type(exc).__name__
            finally:
                if connection is not None:
                    connection.close()
        return CheckResult(False, f"external TCP failed for {self.config.external_host}:{self.config.external_port}: {last_error}")

    def probe_tunnel(self):
        if not self.config.tunnel_check_enabled:
            return CheckResult(True, "disabled")
        active = self.command_runner(["systemctl", "is-active", "--quiet", self.config.tunnel_service], timeout=10)
        if active.returncode != 0:
            return CheckResult(False, f"{self.config.tunnel_service} inactive")
        try:
            status = self._http_status(self.config.tunnel_ready_url)
        except Exception as exc:
            return CheckResult(False, f"tunnel readiness unavailable: {type(exc).__name__}")
        return CheckResult(status == 200, f"tunnel readiness status={status}")

    def probe_cameras(self):
        if not self.config.camera_check_enabled:
            return CheckResult(True, "disabled")
        try:
            cameras = json.loads(self.config.camera_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return CheckResult(True, "no camera registry")
        except (OSError, json.JSONDecodeError):
            return CheckResult(False, "camera registry unreadable")
        if not isinstance(cameras, dict) or not cameras:
            return CheckResult(True, "no registered cameras")
        failed = []
        checked = 0
        for camera_id, camera in cameras.items():
            if not isinstance(camera, dict) or not camera.get("timelapse", True):
                continue
            host = str(camera.get("ip_address") or "").strip()
            port = parse_int(camera.get("port"), 554, minimum=1)
            checked += 1
            try:
                with socket.create_connection((host, port), timeout=self.config.request_timeout_seconds):
                    pass
            except OSError:
                failed.append(str(camera_id))
        if failed:
            return CheckResult(False, f"camera TCP unavailable: {','.join(failed[:5])}")
        return CheckResult(True, f"registered cameras reachable={checked}")

    def collect_checks(self):
        hub, mqtt = self.probe_hub()
        return {
            "hub": hub,
            "mqtt": mqtt,
            "network": self.probe_network(),
            "tunnel": self.probe_tunnel(),
            "camera": self.probe_cameras(),
        }

    def active_connection(self):
        if self.config.network_connection:
            return self.config.network_connection
        result = self.command_runner(
            ["nmcli", "-g", "GENERAL.CONNECTION", "device", "show", self.config.network_interface],
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    def execute_action(self, action):
        LOGGER.warning("Recovery action: %s reason=%s", action.name, action.reason)
        if self.dry_run:
            return True
        commands = []
        if action.name == "restart_hub":
            commands = [["systemctl", "restart", self.config.hub_service]]
        elif action.name == "restart_mqtt_hub":
            commands = [
                ["systemctl", "restart", self.config.mqtt_service],
                ["systemctl", "restart", self.config.hub_service],
            ]
        elif action.name == "restart_tunnel":
            commands = [["systemctl", "restart", self.config.tunnel_service]]
        elif action.name == "restart_network_manager":
            commands = [["systemctl", "restart", "NetworkManager.service"]]
        elif action.name == "reconnect_wifi":
            connection_name = self.active_connection()
            if not connection_name:
                LOGGER.error("Cannot reconnect Wi-Fi because the active connection is unknown")
                return False
            commands = [
                ["nmcli", "device", "disconnect", self.config.network_interface],
                ["nmcli", "connection", "up", connection_name, "ifname", self.config.network_interface],
            ]
        elif action.name == "reboot_host":
            return True
        else:
            LOGGER.error("Unknown recovery action: %s", action.name)
            return False
        success = True
        for command in commands:
            result = self.command_runner(command, timeout=45)
            if result.returncode != 0:
                LOGGER.error("Recovery command failed: command=%s status=%s", command[0:3], result.returncode)
                success = False
            if action.name == "reconnect_wifi" and command[1:3] == ["device", "disconnect"]:
                self.sleep(2)
        return success

    def send_discord(self, content):
        if not self.config.discord_enabled or not self.config.discord_webhook_url:
            return True
        payload = json.dumps(
            {
                "username": "INA Hub Healthcheck",
                "allowed_mentions": {"parse": []},
                "content": content[:2000],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        webhook_request = request.Request(
            self.config.discord_webhook_url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "ina-device-hub-healthcheck"},
            method="POST",
        )
        try:
            with request.urlopen(webhook_request, timeout=self.config.request_timeout_seconds) as response:
                return response.status < 300
        except Exception as exc:
            LOGGER.warning("Discord healthcheck notification could not be sent: %s", type(exc).__name__)
            return False

    @staticmethod
    def current_boot_id():
        try:
            return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    @staticmethod
    def system_uptime_seconds():
        try:
            return float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
        except (OSError, ValueError, IndexError):
            return float("inf")

    @staticmethod
    def failure_summary(checks, state, threshold):
        summaries = []
        for name in COMPONENTS:
            count = int(state["components"][name].get("consecutive_failures") or 0)
            if count >= threshold:
                summaries.append(f"{name}({count}回): {checks[name].detail}")
        return summaries

    def update_incident(self, state, checks, actions, now):
        failures = self.failure_summary(checks, state, self.config.failure_threshold)
        incident = state.get("incident")
        action_records = [f"{isoformat(now)} {action.name}" for action in actions]
        if failures:
            if not isinstance(incident, dict):
                incident = {
                    "started_at": isoformat(now),
                    "notification_sent": False,
                    "failures": failures,
                    "actions": [],
                }
                state["incident"] = incident
            incident["failures"] = failures
            incident.setdefault("actions", []).extend(action_records)
            if not incident.get("notification_sent"):
                message = "⚠️ INA Hub healthcheckが異常を検出しました。\n" + "\n".join(f"- {item}" for item in failures)
                if action_records:
                    message += "\n復旧操作:\n" + "\n".join(f"- {item}" for item in action_records)
                incident["notification_sent"] = self.send_discord(message)
            return False
        if not isinstance(incident, dict):
            return False
        started_at = parse_datetime(incident.get("started_at"))
        duration_seconds = int((now - started_at).total_seconds()) if started_at else 0
        message = f"✅ INA Hub healthcheckが正常状態へ復旧しました。\n障害開始: {incident.get('started_at') or '不明'}\n継続時間: {duration_seconds // 60}分"
        incident_failures = incident.get("failures") if isinstance(incident.get("failures"), list) else []
        if incident_failures:
            message += "\n検出内容:\n" + "\n".join(f"- {item}" for item in incident_failures[-10:])
        incident_actions = incident.get("actions") if isinstance(incident.get("actions"), list) else []
        if incident_actions:
            message += "\n実施した復旧操作:\n" + "\n".join(f"- {item}" for item in incident_actions[-10:])
        if self.send_discord(message):
            state["incident"] = None
            return True
        return False

    def update_status_notification(self, state, checks, now, *, recovery_notified=False):
        runtime = state["runtime"]
        boot_id = self.current_boot_id()
        if boot_id and boot_id != runtime.get("boot_id"):
            runtime["boot_id"] = boot_id
            runtime["boot_notification_pending"] = True

        all_healthy = all(result.ok for result in checks.values())
        if not all_healthy:
            return
        if recovery_notified:
            runtime["boot_notification_pending"] = False
            runtime["last_healthy_notification_at"] = isoformat(now)
            return

        notification_kind = ""
        if self.config.boot_notification_enabled and runtime.get("boot_notification_pending"):
            notification_kind = "boot"
        else:
            last_notification = parse_datetime(runtime.get("last_healthy_notification_at"))
            if last_notification is None or (now - last_notification).total_seconds() >= self.config.heartbeat_interval_seconds:
                notification_kind = "heartbeat"
        if not notification_kind:
            return

        status_text = " ".join(f"{name}=ok" for name in COMPONENTS)
        if notification_kind == "boot":
            message = f"🟢 INA Hubの起動後正常動作を確認しました。\nホスト: {socket.gethostname()}\n{status_text}"
        else:
            message = f"💚 INA Hub定期正常確認\nホスト: {socket.gethostname()}\n{status_text}"
        if self.send_discord(message):
            runtime["boot_notification_pending"] = False
            runtime["last_healthy_notification_at"] = isoformat(now)

    def run_once(self, now=None):
        now = now or utc_now()
        state = load_state(self.config.state_file)
        checks = self.collect_checks()
        in_boot_grace = self.system_uptime_seconds() < self.config.boot_grace_seconds
        update_component_state(state, checks, now, record_failures=not in_boot_grace)
        actions = [] if in_boot_grace else plan_recovery(self.config, state, checks, now)
        reboot_requested = False
        for action in actions:
            if action.name == "reboot_host":
                reboot_requested = True
                state["last_actions"][action.name] = isoformat(now)
                continue
            self.execute_action(action)
            state["last_actions"][action.name] = isoformat(now)
        recovery_notified = self.update_incident(state, checks, actions, now)
        self.update_status_notification(state, checks, now, recovery_notified=recovery_notified)
        save_state(self.config.state_file, state)
        status_text = " ".join(f"{name}={'ok' if checks[name].ok else 'fail'}" for name in COMPONENTS)
        LOGGER.info("Healthcheck completed: %s boot_grace=%s", status_text, str(in_boot_grace).lower())
        if reboot_requested and not self.dry_run:
            LOGGER.critical("Requesting host reboot after persistent critical failure")
            self.command_runner(["systemctl", "reboot"], timeout=10)
        return checks, actions


def build_parser():
    parser = argparse.ArgumentParser(description="Monitor and recover an INA Local Hub")
    parser.add_argument("--instance", default="main")
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--state-dir", default="/var/lib/ina-device-hub-healthcheck")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--notify-test", action="store_true")
    return parser


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    config = load_config(args)
    service = HealthcheckService(config, dry_run=args.dry_run)
    if args.notify_test:
        success = service.send_discord("✅ INA Hub healthcheckのDiscord通知テストに成功しました。")
        LOGGER.info("Discord notification test: %s", "ok" if success else "failed")
        return 0 if success else 1
    service.run_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
