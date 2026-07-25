import getpass
import io
import json
import os
import re
import stat
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import boto3
import libsql
import paho.mqtt.client as mqtt
from dotenv import dotenv_values

from ina_device_hub.mqtt_contract import MQTT_KEEPALIVE_SECONDS, MQTT_PROTOCOL, MQTT_TRANSPORT

PROJECT_ROOT = Path.cwd() if (Path.cwd() / ".default.env").exists() else Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_ENV_TEMPLATE_PATH = PROJECT_ROOT / ".default.env"
ENV_LINE_PATTERN = re.compile(r"^([A-Z][A-Z0-9_]*)=")


@dataclass(frozen=True)
class ConfigurationField:
    name: str
    label: str
    section: str
    default: str = ""
    required: bool = False
    secret: bool = False


@dataclass(frozen=True)
class ConfigurationSection:
    key: str
    label: str
    checker: str = ""
    include_in_install: bool = True


SECTIONS = (
    ConfigurationSection("core", "Hub基本設定", "core"),
    ConfigurationSection("turso", "Turso / libSQL", "turso"),
    ConfigurationSection("storage", "R2 / S3ストレージ", "storage"),
    ConfigurationSection("mqtt", "MQTTブローカー", "mqtt"),
    ConfigurationSection("hierarchy", "上位Hub Sync", include_in_install=False),
    ConfigurationSection("temporary_storage", "一時R2 / S3ストレージ", include_in_install=False),
    ConfigurationSection("firmware", "OTA firmware配信", include_in_install=False),
    ConfigurationSection("instagram", "Instagram", include_in_install=False),
    ConfigurationSection("weather", "気象データ", include_in_install=False),
    ConfigurationSection("switchbot", "SwitchBot", include_in_install=False),
    ConfigurationSection("device", "デバイス・センサー既定値", include_in_install=False),
    ConfigurationSection("notification", "通知・ヘルス監視", include_in_install=False),
    ConfigurationSection("cloudflare", "Cloudflare hosted option", include_in_install=False),
)

FIELDS = (
    ConfigurationField("WORK_DIR", "作業ディレクトリ", "core", "~/.ina-device-hub", True),
    ConfigurationField("LOCAL_STORAGE_BASE_DIR", "画像等のローカル保存先", "core", "~/.ina-device-hub/storage", True),
    ConfigurationField("HUB_HTTP_HOST", "HTTP bind address", "core", "0.0.0.0", True),
    ConfigurationField("HUB_HTTP_PORT", "HTTP port", "core", "39151", True),
    ConfigurationField("HUB_HTTP_SERVER", "HTTP server", "core", "waitress", True),
    ConfigurationField("HUB_HTTP_THREADS", "HTTP worker threads", "core", "8", True),
    ConfigurationField("HUB_AUTH_MODE", "認証モード", "core", "local", True),
    ConfigurationField("HUB_LOCAL_USER_EMAIL", "ローカル利用時のユーザーemail", "core", "local-user@ina.local", True),
    ConfigurationField("HUB_ADMIN_EMAILS", "アプリ設定を変更できるemail（カンマ区切り）", "core"),
    ConfigurationField("HUB_MAX_REQUEST_BYTES", "HTTPリクエスト上限（bytes）", "core", "67108864", True),
    ConfigurationField("FIRMWARE_MAX_UPLOAD_BYTES", "F/Wアップロード上限（bytes）", "core", "16777216", True),
    ConfigurationField("HUB_BACKUP_DIR", "バックアップ保存先", "core", "~/.ina-device-hub/backups", True),
    ConfigurationField("HUB_BACKUP_RETENTION", "バックアップ保持世代数", "core", "14", True),
    ConfigurationField("HUB_READINESS_TIMEOUT_SECONDS", "起動準備タイムアウト（秒）", "core", "30", True),
    ConfigurationField("TIMELAPSE_INTERVAL", "タイムラプス間隔（秒）", "core", "600", True),
    ConfigurationField("TURSO_DATABASE_URL", "Turso database URL", "turso", required=True),
    ConfigurationField("TURSO_AUTH_TOKEN", "Turso auth token", "turso", required=True, secret=True),
    ConfigurationField("TURSO_SYNC_INTERVAL", "同期間隔（秒）", "turso", "600", True),
    ConfigurationField("S3_ENDPOINT_URL", "S3互換 endpoint URL", "storage", required=True),
    ConfigurationField("S3_BUCKET_NAME", "バケット名", "storage", required=True),
    ConfigurationField("S3_BUCKET_REGION", "リージョン", "storage", "auto", True),
    ConfigurationField("S3_ACCESS_KEY", "アクセスキー", "storage", required=True, secret=True),
    ConfigurationField("S3_SECRET_KEY", "シークレットキー", "storage", required=True, secret=True),
    ConfigurationField("MQTT_BROKER_URL", "ブローカー host", "mqtt", "localhost", True),
    ConfigurationField("MQTT_BROKER_PORT", "ブローカー port", "mqtt", "1883", True),
    ConfigurationField("MQTT_BROKER_USERNAME", "ユーザー名（不要なら空欄）", "mqtt"),
    ConfigurationField("MQTT_BROKER_PASSWORD", "パスワード（不要なら空欄）", "mqtt", secret=True),
    ConfigurationField("HUB_SYNC_PARENT_BASE_URL", "上位Hub Base URL（standaloneなら空欄）", "hierarchy"),
    ConfigurationField("HUB_SYNC_PARENT_TOKEN_FILE", "node bearer token file（絶対path）", "hierarchy"),
    ConfigurationField("HUB_SYNC_PARENT_CA_FILE", "TLS CA bundle（絶対path）", "hierarchy"),
    ConfigurationField("HUB_SYNC_PARENT_CLIENT_CERT_FILE", "mTLS client certificate（絶対path）", "hierarchy"),
    ConfigurationField("HUB_SYNC_PARENT_CLIENT_KEY_FILE", "mTLS private key（絶対path）", "hierarchy"),
    ConfigurationField("HUB_SYNC_PARENT_TIMEOUT_SECONDS", "上位Sync timeout（秒）", "hierarchy", "20"),
    ConfigurationField(
        "HUB_SYNC_PARENT_ALLOW_INSECURE_LOOPBACK",
        "開発用loopback HTTPを許可",
        "hierarchy",
        "false",
    ),
    ConfigurationField("S3_TMP_ENDPOINT_URL", "一時ストレージ endpoint URL", "temporary_storage"),
    ConfigurationField("S3_TMP_BUCKET_NAME", "一時ストレージ bucket", "temporary_storage"),
    ConfigurationField("S3_TMP_BUCKET_REGION", "一時ストレージ region", "temporary_storage", "auto"),
    ConfigurationField("S3_TMP_ACCESS_KEY", "一時ストレージ access key", "temporary_storage", secret=True),
    ConfigurationField("S3_TMP_SECRET_KEY", "一時ストレージ secret key", "temporary_storage", secret=True),
    ConfigurationField("S3_TMP_BASE_URL", "一時ストレージ公開Base URL", "temporary_storage"),
    ConfigurationField("FIRMWARE_HOSTNAME", "firmware配信hostname", "firmware"),
    ConfigurationField("FIRMWARE_PORT", "firmware配信port", "firmware", "39151"),
    ConfigurationField("FIRMWARE_BASE_URL", "firmware配信Base URL", "firmware"),
    ConfigurationField("INSTAGRAM_USER_ID", "Instagram user ID", "instagram"),
    ConfigurationField("INSTAGRAM_ACCESS_TOKEN", "Instagram access token", "instagram", secret=True),
    ConfigurationField("INSTAGRAM_SENSOR_ID", "参照sensor ID", "instagram"),
    ConfigurationField("INSTAGRAM_WEATHER_FORECAST_URL", "Instagram用天気feed URL", "instagram"),
    ConfigurationField("INSTAGRAM_WEATHER_AREA_NAME", "Instagram用天気area", "instagram"),
    ConfigurationField("INSTAGRAM_WEATHER_OFFICE_NAME", "Instagram用気象台", "instagram"),
    ConfigurationField("INSTAGRAM_WEATHER_FORECAST_TITLE", "Instagram用予報title", "instagram"),
    ConfigurationField("WEATHER_RECORD_ENABLED", "気象記録を有効化", "weather", "true"),
    ConfigurationField("WEATHER_RECORD_INTERVAL_SECONDS", "気象記録間隔（秒）", "weather", "21600"),
    ConfigurationField("WEATHER_PROVIDER", "気象provider", "weather", "open_meteo"),
    ConfigurationField("WEATHER_LATITUDE", "緯度", "weather"),
    ConfigurationField("WEATHER_LONGITUDE", "経度", "weather"),
    ConfigurationField("WEATHER_TIMEZONE", "気象timezone", "weather", "Asia/Tokyo"),
    ConfigurationField("WEATHER_BACKFILL_DAYS", "気象backfill日数", "weather", "7"),
    ConfigurationField("WEATHER_OPEN_METEO_ARCHIVE_URL", "Open-Meteo archive URL", "weather"),
    ConfigurationField("WEATHER_FORECAST_URL", "天気feed URL", "weather"),
    ConfigurationField("WEATHER_AREA_NAME", "天気area", "weather"),
    ConfigurationField("WEATHER_OFFICE_NAME", "気象台", "weather"),
    ConfigurationField("WEATHER_FORECAST_TITLE", "予報title", "weather"),
    ConfigurationField("SWITCHBOT_OPEN_TOKEN", "SwitchBot open token", "switchbot", secret=True),
    ConfigurationField("SWITCHBOT_SECRET_KEY", "SwitchBot secret key", "switchbot", secret=True),
    ConfigurationField("SWITCHBOT_PLUG_MINI_DEVICE_ID", "Plug Mini device ID", "switchbot"),
    ConfigurationField("SWITCHBOT_BASE_URL", "SwitchBot Base URL", "switchbot", "https://api.switch-bot.com"),
    ConfigurationField("SWITCHBOT_TIMEOUT_SECONDS", "SwitchBot timeout（秒）", "switchbot", "20"),
    ConfigurationField("DEVICE_CONFIG_DEFAULT_NTP_SERVER", "device既定NTP server", "device", "pool.ntp.org"),
    ConfigurationField("DEVICE_CONFIG_DEFAULT_TIMEZONE_OFFSET_SEC", "device既定timezone offset", "device", "32400"),
    ConfigurationField("DEVICE_CONFIG_DEFAULT_MOISTURE_THRESHOLD", "device既定水分閾値", "device", "35"),
    ConfigurationField("SENSOR_SAVE_IMAGE", "sensor画像を保存", "device", "false"),
    ConfigurationField("SENSOR_SAVE_AUDIO", "sensor音声を保存", "device", "false"),
    ConfigurationField("DISCORD_WEBHOOK_URL", "Discord webhook URL", "notification", secret=True),
    ConfigurationField("DISCORD_ENABLED", "Discord通知を有効化", "notification", "true"),
    ConfigurationField("DISCORD_NOTIFY_MQTT_ACTIVITY", "MQTT activity通知", "notification", "false"),
    ConfigurationField("DISCORD_NOTIFY_OPERATIONS_SECURITY_ALERTS", "Operations API認証拒否通知", "notification", "true"),
    ConfigurationField("DISCORD_SECURITY_ALERT_COOLDOWN_SECONDS", "認証拒否通知の重複抑制（秒）", "notification", "300"),
    ConfigurationField("DISCORD_NOTIFY_NEW_DEVICE", "新規device通知", "notification", "true"),
    ConfigurationField("DISCORD_NOTIFY_DEVICE_OFFLINE", "device offline通知", "notification", "true"),
    ConfigurationField("DISCORD_NOTIFY_WATERING_MISSING", "潅水なし通知", "notification", "true"),
    ConfigurationField("DISCORD_NOTIFY_SOIL_CALIBRATION_SUGGESTED", "土壌水分計の調整候補通知", "notification", "true"),
    ConfigurationField("DISCORD_NOTIFY_PLANT_TASKS", "栽培作業の日次通知", "notification", "true"),
    ConfigurationField("DISCORD_PLANT_TASK_NOTIFY_NEW", "新規栽培作業通知", "notification", "true"),
    ConfigurationField("DISCORD_PLANT_TASK_REMINDER_DAYS_BEFORE", "栽培作業の事前通知日数", "notification", "7"),
    ConfigurationField("DISCORD_PLANT_TASK_NOTIFY_ON_START_DAY", "栽培作業の開始日通知", "notification", "true"),
    ConfigurationField("DISCORD_PLANT_TASK_NOTIFY_DURING_WINDOW", "栽培作業期間中の日次通知", "notification", "true"),
    ConfigurationField("HEALTH_MONITOR_ENABLED", "health monitor有効化", "notification", "false"),
    ConfigurationField("HEALTH_MONITOR_INTERVAL_SECONDS", "health monitor間隔（秒）", "notification", "1800"),
    ConfigurationField("HEALTH_DEVICE_OFFLINE_AFTER_HOURS", "offline判定時間", "notification", "12"),
    ConfigurationField("HEALTH_WATERING_MISSING_AFTER_DAYS", "潅水なし判定日数", "notification", "2"),
    ConfigurationField("CLOUDFLARE_ACCOUNT_ID", "Cloudflare account ID", "cloudflare"),
    ConfigurationField("CLOUDFLARE_ACCESS_API_TOKEN", "Cloudflare Access API token", "cloudflare", secret=True),
    ConfigurationField("CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME", "公開hostname", "cloudflare"),
    ConfigurationField("CLOUDFLARE_ACCESS_TEAM_DOMAIN", "Access team domain", "cloudflare"),
    ConfigurationField("CLOUDFLARE_ACCESS_POLICY_AUD", "Access policy AUD", "cloudflare"),
    ConfigurationField("CLOUDFLARE_ACCESS_GROUP_ID", "Access group ID", "cloudflare"),
    ConfigurationField("CLOUDFLARE_ACCESS_APP_ID", "Access app ID", "cloudflare"),
    ConfigurationField("CLOUDFLARE_ACCESS_POLICY_ID", "Access policy ID", "cloudflare"),
    ConfigurationField("CLOUDFLARE_ACCESS_APP_NAME", "Access app name", "cloudflare", "inas-hub-hosted"),
    ConfigurationField("CLOUDFLARE_ACCESS_GROUP_NAME", "Access group name", "cloudflare", "inas-hub-allowed-users"),
    ConfigurationField("CLOUDFLARE_ACCESS_POLICY_NAME", "Access policy name", "cloudflare", "inas-hub-allow-email-group"),
    ConfigurationField("CLOUDFLARE_ACCESS_SESSION_DURATION", "Access session duration", "cloudflare", "4h"),
    ConfigurationField("CLOUDFLARE_ACCESS_ALLOWED_EMAILS", "許可email", "cloudflare"),
    ConfigurationField("CLOUDFLARE_ACCESS_ALLOWED_EMAIL_DOMAINS", "許可email domain", "cloudflare"),
    ConfigurationField("HUB_OPERATIONS_SERVICE_IDS", "Operations API許可service ID", "cloudflare"),
    ConfigurationField("CLOUDFLARE_TUNNEL_NAME", "Tunnel name", "cloudflare"),
    ConfigurationField("CLOUDFLARE_TUNNEL_ID", "Tunnel ID", "cloudflare"),
    ConfigurationField("CLOUDFLARE_TUNNEL_HOSTNAME", "Tunnel hostname", "cloudflare"),
    ConfigurationField("CLOUDFLARE_TUNNEL_ORIGIN_URL", "Tunnel origin URL", "cloudflare"),
    ConfigurationField("CLOUDFLARE_TUNNEL_TOKEN_FILE", "Tunnel token file", "cloudflare", secret=True),
    ConfigurationField("CLOUDFLARE_TUNNEL_DNS_RECORD_ID", "Tunnel DNS record ID", "cloudflare"),
    ConfigurationField("CLOUDFLARE_ZONE_ID", "Cloudflare zone ID", "cloudflare"),
    ConfigurationField("CLOUDFLARE_ZONE_NAME", "Cloudflare zone name", "cloudflare"),
    ConfigurationField("CLOUDFLARE_CLOUDFLARED_BIN", "cloudflared binary path", "cloudflare"),
    ConfigurationField("CLOUDFLARE_HOSTED_HUB_STARTUP_WAIT_SECONDS", "Hub起動待機秒数", "cloudflare", "3"),
)

FIELDS_BY_SECTION = {section.key: tuple(field for field in FIELDS if field.section == section.key) for section in SECTIONS}


class EnvDocument:
    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.values = {key: value or "" for key, value in dotenv_values(stream=io.StringIO(text)).items()}

    @classmethod
    def load(cls, env_path: Path, template_path: Path = DEFAULT_ENV_TEMPLATE_PATH):
        source = env_path if env_path.exists() else template_path
        text = source.read_text() if source.exists() else ""
        return cls(text)

    def get(self, key: str, default: str = "") -> str:
        return str(self.values.get(key, default) or "")

    def set(self, key: str, value: str):
        encoded = json.dumps(str(value), ensure_ascii=False)
        replacement = f"{key}={encoded}"
        for index, line in enumerate(self.lines):
            match = ENV_LINE_PATTERN.match(line)
            if match and match.group(1) == key:
                self.lines[index] = replacement
                break
        else:
            if self.lines and self.lines[-1]:
                self.lines.append("")
            self.lines.append(replacement)
        self.values[key] = str(value)

    def save(self, env_path: Path):
        env_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = env_path.with_suffix(f"{env_path.suffix}.tmp")
        temporary_path.write_text("\n".join(self.lines).rstrip() + "\n")
        os.chmod(temporary_path, 0o600)
        temporary_path.replace(env_path)


def _masked(value: str) -> str:
    if not value:
        return "未設定"
    if len(value) <= 6:
        return "設定済み"
    return f"{value[:2]}***{value[-2:]}"


def _ask_value(field, current, input_function=input, secret_input_function=getpass.getpass):
    shown_current = _masked(current) if field.secret else current
    prompt = f"{field.label} ({field.name})"
    if shown_current:
        prompt += f" [{shown_current}]"
    prompt += ": "
    while True:
        supplied = secret_input_function(prompt) if field.secret else input_function(prompt)
        value = supplied if supplied else current
        if value or not field.required:
            return value
        print("  必須項目です。値を入力してください。")


def _ask_yes_no(prompt: str, input_function=input, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    value = input_function(f"{prompt} {suffix}: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes"}


def _check_core(values):
    for key in ("WORK_DIR", "LOCAL_STORAGE_BASE_DIR"):
        path = Path(os.path.expanduser(values[key]))
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".ina-write-check-", delete=True):
            pass
    port = int(values["HUB_HTTP_PORT"])
    if not 1 <= port <= 65535:
        raise ValueError("HUB_HTTP_PORT must be between 1 and 65535")
    int(values["TIMELAPSE_INTERVAL"])
    if values["HUB_HTTP_SERVER"] not in {"waitress", "flask"}:
        raise ValueError("HUB_HTTP_SERVER must be waitress or flask")
    if values["HUB_AUTH_MODE"] not in {"local", "cloudflare_access"}:
        raise ValueError("HUB_AUTH_MODE must be local or cloudflare_access")
    for key in ("HUB_HTTP_THREADS", "HUB_MAX_REQUEST_BYTES", "FIRMWARE_MAX_UPLOAD_BYTES", "HUB_BACKUP_RETENTION", "HUB_READINESS_TIMEOUT_SECONDS"):
        if int(values[key]) <= 0:
            raise ValueError(f"{key} must be greater than zero")
    return "保存先への書き込みと数値設定を確認しました"


def _check_turso(values):
    work_dir = Path(os.path.expanduser(values["WORK_DIR"]))
    work_dir.mkdir(parents=True, exist_ok=True)
    # libSQL creates metadata, WAL, and shared-memory sidecars. Keep the probe
    # in its own directory so a failed or interrupted check cannot poison the
    # next run with only part of the replica state left behind.
    with tempfile.TemporaryDirectory(prefix=".turso-connection-check-", dir=work_dir) as temporary_directory:
        check_path = Path(temporary_directory) / "replica.db"
        connection = libsql.connect(
            str(check_path),
            sync_url=values["TURSO_DATABASE_URL"],
            auth_token=values["TURSO_AUTH_TOKEN"],
            sync_interval=max(1, int(values.get("TURSO_SYNC_INTERVAL") or 600)),
        )
        try:
            connection.sync()
            connection.execute("SELECT 1").fetchone()
        finally:
            connection.close()
    return "Tursoへの接続と同期を確認しました"


def _check_storage(values):
    client = boto3.client(
        "s3",
        endpoint_url=values["S3_ENDPOINT_URL"],
        region_name=values["S3_BUCKET_REGION"],
        aws_access_key_id=values["S3_ACCESS_KEY"],
        aws_secret_access_key=values["S3_SECRET_KEY"],
    )
    client.head_bucket(Bucket=values["S3_BUCKET_NAME"])
    return "バケットへの接続を確認しました"


def _check_mqtt(values):
    connected = threading.Event()
    result = {"error": "MQTT broker did not respond"}

    def on_connect(_client, _userdata, _flags, reason_code, _properties):
        if reason_code.is_failure:
            result["error"] = f"MQTT connection rejected: {reason_code}"
        else:
            result["error"] = ""
        connected.set()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="ina-hub-configuration-check",
        protocol=MQTT_PROTOCOL,
        transport=MQTT_TRANSPORT,
    )
    if values.get("MQTT_BROKER_USERNAME"):
        client.username_pw_set(values.get("MQTT_BROKER_USERNAME", ""), values.get("MQTT_BROKER_PASSWORD", ""))
    client.on_connect = on_connect
    client.connect(values["MQTT_BROKER_URL"], int(values["MQTT_BROKER_PORT"]), keepalive=MQTT_KEEPALIVE_SECONDS)
    client.loop_start()
    try:
        if not connected.wait(timeout=7) or result["error"]:
            raise RuntimeError(result["error"])
    finally:
        client.disconnect()
        client.loop_stop()
    return "MQTTブローカーへの接続を確認しました"


CHECKERS = {
    "core": _check_core,
    "turso": _check_turso,
    "storage": _check_storage,
    "mqtt": _check_mqtt,
}


def check_section(section: ConfigurationSection, values: dict) -> bool:
    checker = CHECKERS.get(section.checker)
    if not checker:
        return True
    try:
        print(f"  OK: {checker(values)}")
        return True
    except Exception as exc:  # Connection libraries expose provider-specific exception types.
        print(f"  NG: {exc}")
        return False


def check_configuration(env_path=DEFAULT_ENV_PATH, *, production=False, skip_connections=False) -> int:
    env_path = Path(env_path)
    if not env_path.is_file():
        print(f"NG: .env がありません: {env_path}")
        return 2
    document = EnvDocument.load(env_path)
    values = _effective_values(document)
    required_fields = [field for field in FIELDS if field.required and field.section in {"core", "turso", "storage", "mqtt"}]
    missing = [field.name for field in required_fields if not values.get(field.name)]
    if missing:
        print(f"NG: 必須設定が未入力です: {', '.join(missing)}")
        return 1

    sections = [section for section in SECTIONS if section.key in {"core", "turso", "storage", "mqtt"}]
    results = []
    for section in sections:
        if skip_connections and section.key != "core":
            continue
        print(f"[{section.label}]")
        results.append(check_section(section, values))
    if production:
        results.append(_check_production_settings(env_path, values))
    return 0 if all(results) else 1


def _effective_values(document: EnvDocument) -> dict:
    values = dict(document.values)
    for field in FIELDS:
        values.setdefault(field.name, field.default)
    # Existing deployments did not have these keys. Preserve their behavior
    # when a pulled revision reads the old .env for the first time.
    if "HUB_HTTP_HOST" not in document.values:
        values["HUB_HTTP_HOST"] = "0.0.0.0"
    if "HUB_HTTP_SERVER" not in document.values:
        values["HUB_HTTP_SERVER"] = "flask"
    if "HUB_AUTH_MODE" not in document.values:
        values["HUB_AUTH_MODE"] = "local"
    if "LOCAL_STORAGE_BASE_DIR" not in document.values:
        values["LOCAL_STORAGE_BASE_DIR"] = "./.data/storage"
    return values


def _check_production_settings(env_path: Path, values: dict) -> bool:
    failures = []
    mode = stat.S_IMODE(env_path.stat().st_mode)
    if mode & 0o077:
        failures.append(f".env permission must not allow group/other access (current: {mode:04o})")
    if values.get("HUB_HTTP_SERVER") != "waitress":
        failures.append("HUB_HTTP_SERVER must be waitress")
    if values.get("HUB_AUTH_MODE") != "cloudflare_access":
        failures.append("HUB_AUTH_MODE must be cloudflare_access")
    for key in ("HUB_ADMIN_EMAILS", "CLOUDFLARE_ACCESS_TEAM_DOMAIN", "CLOUDFLARE_ACCESS_POLICY_AUD"):
        if not str(values.get(key) or "").strip():
            failures.append(f"{key} must be configured")
    origin_url = str(values.get("CLOUDFLARE_TUNNEL_ORIGIN_URL") or "")
    if origin_url and not _is_loopback_host(urlsplit(origin_url).hostname or ""):
        failures.append("CLOUDFLARE_TUNNEL_ORIGIN_URL must target a loopback address")

    if failures:
        for failure in failures:
            print(f"  NG: {failure}")
        return False
    print("  OK: 本番公開設定と秘密情報権限を確認しました")
    return True


def _is_loopback_host(value: str) -> bool:
    return str(value or "").strip().lower() in {"127.0.0.1", "::1", "localhost"}


def install(env_path=DEFAULT_ENV_PATH, skip_checks=False, input_function=input, secret_input_function=getpass.getpass):
    env_path = Path(env_path)
    document = EnvDocument.load(env_path)
    print(f"INA Device Hub 初期設定: {env_path}")
    if env_path.exists():
        print("既存値はEnterで維持します。")

    for section in (item for item in SECTIONS if item.include_in_install):
        print(f"\n[{section.label}]")
        for field in FIELDS_BY_SECTION[section.key]:
            current = document.get(field.name, field.default)
            document.set(field.name, _ask_value(field, current, input_function, secret_input_function))
        if section.checker and not skip_checks and _ask_yes_no("この接続・設定を確認しますか", input_function):
            check_section(section, document.values)

    document.save(env_path)
    print(f"\n.env を保存しました: {env_path}")
    print("AI APIキー、Base URL、モデルは「アプリ設定」、日時表示は「個人設定」で設定してください。")
    return 0


def _select(prompt: str, choices: tuple, input_function=input):
    while True:
        for index, choice in enumerate(choices, start=1):
            print(f"  {index}. {choice.label}")
        value = input_function(f"{prompt} [1-{len(choices)}]: ").strip()
        if value.isdigit() and 1 <= int(value) <= len(choices):
            return choices[int(value) - 1]
        print("  番号を選択してください。")


def configure(env_path=DEFAULT_ENV_PATH, skip_checks=False, input_function=input, secret_input_function=getpass.getpass):
    env_path = Path(env_path)
    if not env_path.exists():
        print(f".env がありません。先に `uv run ina-hub install` を実行してください: {env_path}")
        return 2
    document = EnvDocument.load(env_path)
    print(f"INA Device Hub 再設定: {env_path}")

    while True:
        section = _select("変更するカテゴリ", SECTIONS, input_function)
        field = _select("変更する設定", FIELDS_BY_SECTION[section.key], input_function)
        current = document.get(field.name, field.default)
        document.set(field.name, _ask_value(field, current, input_function, secret_input_function))
        document.save(env_path)
        print(f"  {field.name} を保存しました。")
        if section.checker and not skip_checks and _ask_yes_no("関連する接続・設定を確認しますか", input_function):
            check_section(section, document.values)
        if not _ask_yes_no("続けて別の設定を変更しますか", input_function, default=False):
            break
    print("起動中のHubへ反映するにはプロセスを再起動してください。")
    return 0
