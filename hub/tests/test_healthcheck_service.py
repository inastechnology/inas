import importlib.util
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "healthcheck_service.py"
SPEC = importlib.util.spec_from_file_location("healthcheck_service", SCRIPT_PATH)
healthcheck_service = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = healthcheck_service
SPEC.loader.exec_module(healthcheck_service)


def make_config(state_file, **overrides):
    values = {
        "instance": "main",
        "env_file": Path("/tmp/test.env"),
        "work_dir": Path("/tmp"),
        "state_file": state_file,
        "hub_port": 39151,
        "hub_service": "inas-device-hub@main.service",
        "mqtt_service": "mosquitto.service",
        "tunnel_service": "inas-cloudflare-tunnel.service",
        "tunnel_ready_url": "http://127.0.0.1:20241/ready",
        "network_interface": "wlan0",
        "network_connection": "test-wifi",
        "external_host": "example.com",
        "external_port": 443,
        "camera_file": Path("/tmp/cameras.json"),
        "camera_check_enabled": True,
        "tunnel_check_enabled": True,
        "recovery_enabled": True,
        "discord_enabled": True,
        "discord_webhook_url": "https://discord.invalid/webhook",
        "failure_threshold": 3,
        "network_manager_threshold": 6,
        "reboot_threshold": 15,
        "action_cooldown_seconds": 300,
        "reboot_cooldown_seconds": 21600,
        "request_timeout_seconds": 5,
        "heartbeat_interval_seconds": 21600,
        "boot_notification_enabled": True,
        "boot_grace_seconds": 600,
    }
    values.update(overrides)
    return healthcheck_service.HealthcheckConfig(**values)


def checks(**failed_details):
    return {name: healthcheck_service.CheckResult(name not in failed_details, failed_details.get(name, "ok")) for name in healthcheck_service.COMPONENTS}


class HealthcheckServiceTest(unittest.TestCase):
    def test_expand_config_path_uses_env_file_owner_home(self):
        home = Path("/srv/inas")

        self.assertEqual(healthcheck_service.expand_config_path("~/.ina-device-hub", home), home / ".ina-device-hub")
        self.assertEqual(healthcheck_service.expand_config_path("/var/lib/inas", home), Path("/var/lib/inas"))

    def test_network_recovery_escalates_by_consecutive_failure_count(self):
        now = datetime(2026, 8, 5, tzinfo=UTC)
        config = make_config(Path("/tmp/state.json"))
        failed_checks = checks(network="external TCP failed")

        expected_actions = {3: "reconnect_wifi", 6: "restart_network_manager", 15: "reboot_host"}
        for failure_count, expected_action in expected_actions.items():
            state = healthcheck_service.empty_state()
            state["components"]["network"]["consecutive_failures"] = failure_count

            actions = healthcheck_service.plan_recovery(config, state, failed_checks, now)

            self.assertEqual([action.name for action in actions], [expected_action])

    def test_camera_only_failure_does_not_plan_disruptive_recovery(self):
        state = healthcheck_service.empty_state()
        state["components"]["camera"]["consecutive_failures"] = 20

        actions = healthcheck_service.plan_recovery(
            make_config(Path("/tmp/state.json")),
            state,
            checks(camera="camera TCP unavailable"),
            datetime(2026, 8, 5, tzinfo=UTC),
        )

        self.assertEqual(actions, [])

    def test_configured_reboot_threshold_applies_to_critical_components(self):
        now = datetime(2026, 8, 5, tzinfo=UTC)
        config = make_config(Path("/tmp/state.json"), reboot_threshold=3)

        for component in healthcheck_service.REBOOT_COMPONENTS:
            with self.subTest(component=component):
                state = healthcheck_service.empty_state()
                state["components"][component]["consecutive_failures"] = 3

                actions = healthcheck_service.plan_recovery(config, state, checks(**{component: "failed"}), now)

                self.assertEqual([action.name for action in actions], ["reboot_host"])

    def test_mqtt_failure_restarts_mqtt_and_hub(self):
        state = healthcheck_service.empty_state()
        state["components"]["mqtt"]["consecutive_failures"] = 3

        actions = healthcheck_service.plan_recovery(
            make_config(Path("/tmp/state.json")),
            state,
            checks(mqtt="readyz mqtt=False"),
            datetime(2026, 8, 5, tzinfo=UTC),
        )

        self.assertEqual([action.name for action in actions], ["restart_mqtt_hub"])

    def test_text_tunnel_readiness_response_is_accepted(self):
        with tempfile.TemporaryDirectory() as state_dir:
            service = healthcheck_service.HealthcheckService(
                make_config(Path(state_dir) / "state.json"),
                command_runner=Mock(return_value=subprocess.CompletedProcess([], 0, "", "")),
            )
            service._http_status = Mock(return_value=200)

            result = service.probe_tunnel()

        self.assertTrue(result.ok)

    def test_unsent_incident_is_preserved_and_recovery_is_notified(self):
        with tempfile.TemporaryDirectory() as state_dir:
            config = make_config(Path(state_dir) / "state.json")
            service = healthcheck_service.HealthcheckService(config)
            service.send_discord = Mock(side_effect=[False, True])
            state = healthcheck_service.empty_state()
            failed_checks = checks(network="DNS failed")
            state["components"]["network"]["consecutive_failures"] = 3
            started_at = datetime(2026, 8, 5, 1, 0, tzinfo=UTC)

            service.update_incident(state, failed_checks, [], started_at)
            self.assertIsNotNone(state["incident"])
            self.assertFalse(state["incident"]["notification_sent"])

            recovered_at = datetime(2026, 8, 5, 1, 10, tzinfo=UTC)
            recovered_checks = checks()
            healthcheck_service.update_component_state(state, recovered_checks, recovered_at)
            service.update_incident(state, recovered_checks, [], recovered_at)

        self.assertIsNone(state["incident"])
        self.assertEqual(service.send_discord.call_count, 2)

    def test_boot_confirmation_and_periodic_heartbeat_are_notified(self):
        config = make_config(Path("/tmp/state.json"), heartbeat_interval_seconds=21600)
        service = healthcheck_service.HealthcheckService(config)
        service.current_boot_id = Mock(return_value="boot-a")
        service.send_discord = Mock(return_value=True)
        state = healthcheck_service.empty_state()
        started_at = datetime(2026, 8, 5, 1, 0, tzinfo=UTC)

        service.update_status_notification(state, checks(), started_at)
        service.update_status_notification(state, checks(), started_at + timedelta(hours=1))
        service.update_status_notification(state, checks(), started_at + timedelta(hours=6))

        self.assertEqual(service.send_discord.call_count, 2)
        self.assertIn("起動後正常動作", service.send_discord.call_args_list[0].args[0])
        self.assertIn("定期正常確認", service.send_discord.call_args_list[1].args[0])

    def test_boot_grace_does_not_count_startup_failures(self):
        with tempfile.TemporaryDirectory() as state_dir:
            config = make_config(Path(state_dir) / "state.json", boot_grace_seconds=600)
            service = healthcheck_service.HealthcheckService(config, dry_run=True)
            service.collect_checks = Mock(return_value=checks(hub="starting", mqtt="starting"))
            service.current_boot_id = Mock(return_value="boot-a")
            service.system_uptime_seconds = Mock(return_value=120)

            _, actions = service.run_once(datetime(2026, 8, 5, 1, 0, tzinfo=UTC))
            state = healthcheck_service.load_state(config.state_file)

        self.assertEqual(actions, [])
        self.assertEqual(state["components"]["hub"]["consecutive_failures"], 0)
        self.assertEqual(state["components"]["mqtt"]["consecutive_failures"], 0)


if __name__ == "__main__":
    unittest.main()
