#!/usr/bin/env python3
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _prepare_env():
    load_dotenv()
    os.environ["WORK_DIR"] = os.environ.get("HUB_DEMO_WORK_DIR", "/tmp/ina-device-hub-demo/work")
    os.environ["LOCAL_STORAGE_BASE_DIR"] = os.environ.get("HUB_DEMO_LOCAL_STORAGE_BASE_DIR", "/tmp/ina-device-hub-demo/storage")
    os.environ.setdefault("TURSO_DATABASE_URL", "demo")
    os.environ.setdefault("TURSO_AUTH_TOKEN", "demo")
    os.environ.setdefault("S3_ENDPOINT_URL", "demo")
    os.environ.setdefault("S3_BUCKET_NAME", "demo")
    os.environ.setdefault("S3_BUCKET_REGION", "auto")
    os.environ.setdefault("S3_ACCESS_KEY", "demo")
    os.environ.setdefault("S3_SECRET_KEY", "demo")
    os.environ.setdefault("MQTT_BROKER_URL", "localhost")
    os.environ.setdefault("MQTT_BROKER_PORT", "1883")
    os.environ.setdefault("MQTT_BROKER_USERNAME", "")
    os.environ.setdefault("MQTT_BROKER_PASSWORD", "")
    os.environ.setdefault("TIMELAPSE_INTERVAL", "600")
    os.environ.setdefault("FIRMWARE_BASE_URL", "http://demo-hub.local:39151")


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    _prepare_env()

    from ina_device_hub.web_server import app

    host = os.environ.get("HUB_DEMO_HOST", "127.0.0.1")
    port = int(os.environ.get("HUB_DEMO_PORT", "39251"))
    print(f"Admin UI demo: http://{host}:{port}/demo/mqtt-devices")
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
