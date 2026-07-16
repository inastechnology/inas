#!/usr/bin/env python3
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

DEMO_LAYOUT_DEVICES = (
    {
        "id": "INADS-DEMO-WTR-001",
        "name": "デモ潅水機1",
        "kind": "WTR",
        "location": "イチゴ実証圃場",
        "status": {"last_soil_moisture": 42, "watering_started": False},
        "switches": (
            ("irr1", "潅水1系", "IRR1", 1, "デモ点滴ラインA"),
            ("irr2", "潅水2系", "IRR2", 2, "デモ点滴ラインB"),
        ),
    },
    {
        "id": "INADS-DEMO-WTR-002",
        "name": "育苗ベンチ潅水機",
        "kind": "WTR",
        "location": "未設置",
        "status": {"last_soil_moisture": 48, "watering_started": False},
        "switches": (
            ("irr1", "潅水1系", "IRR1", 1, "育苗ベンチ東側"),
            ("irr2", "潅水2系", "IRR2", 2, "育苗ベンチ西側"),
        ),
    },
    {
        "id": "INADS-DEMO-WTR-003",
        "name": "鉢エリア潅水機",
        "kind": "WTR",
        "location": "未設置",
        "status": {"last_soil_moisture": 37, "watering_started": False},
        "switches": (
            ("irr1", "潅水1系", "IRR1", 1, "ブルーベリー鉢列"),
            ("irr2", "潅水2系", "IRR2", 2, "果樹鉢列"),
        ),
    },
    {
        "id": "INADS-DEMO-WRS-001",
        "name": "ハウス統合潅水盤",
        "kind": "WRS",
        "location": "未設置",
        "status": {
            "soil_moisture_percent": 41.5,
            "soil_ec_us_cm": 760,
            "soil_ph": 6.2,
            "par_umol_m2_s": 980,
        },
        "switches": (
            ("irr1", "東側点滴ライン", "IRR1", 1, "1号ハウス東側電磁弁"),
            ("irr2", "西側点滴ライン", "IRR2", 2, "1号ハウス西側電磁弁"),
            ("sensor_power", "RS485センサー電源", "SENSOR_12V_SW", 0, "土壌・PARセンサー"),
        ),
    },
    {
        "id": "INADS-DEMO-WRS-002",
        "name": "露地統合潅水盤",
        "kind": "WRS",
        "location": "未設置",
        "status": {
            "soil_moisture_percent": 35.0,
            "soil_ec_us_cm": 610,
            "soil_ph": 6.5,
            "par_umol_m2_s": 1320,
        },
        "switches": (
            ("irr1", "露地A系統", "IRR1", 1, "露地A点滴ライン"),
            ("irr2", "露地B系統", "IRR2", 2, "露地B点滴ライン"),
            ("sensor_power", "RS485センサー電源", "SENSOR_12V_SW", 0, "土壌・PARセンサー"),
        ),
    },
    {
        "id": "INADS-DEMO-ENV-001",
        "name": "ハウス環境センサー",
        "kind": "ENV",
        "location": "未設置",
        "status": {"air_temperature_c": 24.6, "air_humidity_percent": 68.0, "par_umol_m2_s": 920},
        "switches": (),
    },
    {
        "id": "INADS-DEMO-ENV-002",
        "name": "屋外環境センサー",
        "kind": "ENV",
        "location": "未設置",
        "status": {"air_temperature_c": 27.1, "air_humidity_percent": 54.0, "par_umol_m2_s": 1450},
        "switches": (),
    },
    {
        "id": "INADS-DEMO-SOI-001",
        "name": "1番畝 土壌水分",
        "kind": "SOI",
        "location": "未設置",
        "status": {"soil_moisture_percent": 43.0},
        "switches": (),
    },
    {
        "id": "INADS-DEMO-SOI-002",
        "name": "2番畝 土壌水分",
        "kind": "SOI",
        "location": "未設置",
        "status": {"soil_moisture_percent": 39.0},
        "switches": (),
    },
    {
        "id": "INADS-DEMO-SOI-003",
        "name": "ブルーベリー鉢 土壌水分",
        "kind": "SOI",
        "location": "未設置",
        "status": {"soil_moisture_percent": 56.0},
        "switches": (),
    },
    {
        "id": "INADS-DEMO-PAR-001",
        "name": "SEN0641 PARセンサー",
        "kind": "PAR",
        "location": "未設置",
        "status": {"par_umol_m2_s": 1180, "par_ok": True},
        "switches": (),
    },
    {
        "id": "INADS-DEMO-CAM-001",
        "name": "ハウス定点カメラ",
        "kind": "CAM",
        "location": "未設置",
        "status": {"camera_ok": True},
        "switches": (),
    },
)


def _prepare_env():
    load_dotenv()
    os.environ["WORK_DIR"] = os.environ.get("HUB_DEMO_WORK_DIR", "/tmp/ina-device-hub-demo/work")
    os.environ["LOCAL_STORAGE_BASE_DIR"] = os.environ.get("HUB_DEMO_LOCAL_STORAGE_BASE_DIR", "/tmp/ina-device-hub-demo/storage")
    # Never inherit the production Turso replica in the UI demo. A non-URL
    # value makes InaDBConnector use the SQLite file under HUB_DEMO_WORK_DIR.
    os.environ["TURSO_DATABASE_URL"] = os.environ.get("HUB_DEMO_TURSO_DATABASE_URL", "local-demo")
    os.environ["TURSO_AUTH_TOKEN"] = os.environ.get("HUB_DEMO_TURSO_AUTH_TOKEN", "local-demo")
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
    os.environ["AI_ENABLED"] = "false"
    os.environ["AI_IMAGE_ANALYZE_API_KEY"] = os.environ.get("HUB_DEMO_AI_IMAGE_ANALYZE_API_KEY", "")
    os.environ["AI_TEXT_ANALYZE_API_KEY"] = os.environ.get("HUB_DEMO_AI_TEXT_ANALYZE_API_KEY", "")


def _seed_demo_device_state(config_service, device_id: str, desired_state: str):
    repository = config_service.repository
    current_state = config_service.get_record(device_id)["state"]
    if current_state == desired_state:
        return
    if desired_state == "active" and current_state in {"pending", "disabled"}:
        config_service.set_state(device_id, "active", approved_by="demo")
        return

    # The demo is a deterministic fixture. Reset states that cannot be reached
    # through the production lifecycle so every restart exposes all UI states.
    record = repository.device_configs[device_id]
    record["state"] = desired_state
    if desired_state == "pending":
        record["approved_at"] = None
        record["approved_by"] = None
    repository.save()


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    _prepare_env()

    from ina_device_hub.device_config_service import device_config_service
    from ina_device_hub.ai_content_service import ai_content_service
    from ina_device_hub.field_layout_repository import field_layout_repository
    from ina_device_hub.field_repository import field_repository
    from ina_device_hub.plant_management_repository import plant_management_repository
    from ina_device_hub.web_server import app, initialize_web_server

    field_repository().upsert(
        "demo-strawberry-field",
        {
            "name": "イチゴ実証圃場",
            "location": {
                "prefecture": "長野県",
                "municipality": "伊那市",
                "locality": "西箕輪",
                "environment_type": "greenhouse",
            },
            "crop": "イチゴ",
            "stage": "栽培中",
            "cultivation_context": {"cultivation_method": "ハウス・露地", "irrigation_method": "点滴"},
            "device_ids": ["INADS-DEMO-WTR-001", "INADS-DEMO-WTR-002", "INADS-DEMO-WTR-003"],
            "memo": "設置ビュー操作確認用のデモ圃場",
        },
    )

    config_service = device_config_service()
    for index, device in enumerate(DEMO_LAYOUT_DEVICES, start=1):
        device_id = device["id"]
        config_service.get_record(device_id)
        desired_state = "pending" if device_id == "INADS-DEMO-WTR-003" else "active"
        _seed_demo_device_state(config_service, device_id, desired_state)
        config = config_service.get_config(device_id)
        config["mosfet_switches"] = [
            {
                "switch_id": switch_id,
                "name": name,
                "enabled": True,
                "role": "sensor_power" if channel_mask == 0 else "irrigation",
                "terminal": terminal,
                "channel_mask": channel_mask,
                "controlled_load": controlled_load,
                "notes": "デモ用",
            }
            for switch_id, name, terminal, channel_mask, controlled_load in device["switches"]
        ]
        config_service.update_config(device_id, config)
        config_service.update_metadata(device_id, {"name": device["name"], "location": device["location"]})
        config_service.repository.record_status(
            device_id,
            {
                "device_kind": device["kind"],
                "firmware_version": "demo",
                "seq": index,
                **device["status"],
            },
        )

    layout = field_layout_repository().get("demo-strawberry-field", field_name="イチゴ実証圃場")
    valid_placement_ids = {
        placement.get("id")
        for space in layout.get("spaces", [])
        for placement in space.get("placements", [])
    }
    plant_repository = plant_management_repository()
    for planting in plant_repository.field_bundle("demo-strawberry-field")["plantings"]:
        if planting.get("status") == "active" and planting.get("placement_id") not in valid_placement_ids:
            plant_repository.update_planting(planting["id"], {"status": "removed"})
            continue
        calendar = plant_repository.get_calendar(planting["id"])
        if planting.get("status") != "active" or not calendar or calendar.get("task_rules"):
            continue
        generated = ai_content_service().generate_plant_calendar(
            {
                "planting": planting,
                "planning": {"start_date": planting.get("planted_on"), "horizon_months": 12, "notes": "デモ移行"},
            }
        )
        plant_repository.update_planting(planting["id"], {"growth_targets": generated["growth_targets"]})
        plant_repository.replace_calendar(
            planting["id"],
            generated["actions"],
            generated["generation"],
            care_profile=generated["care_profile"],
            task_rules=generated["task_rules"],
        )

    host = os.environ.get("HUB_DEMO_HOST", "127.0.0.1")
    port = int(os.environ.get("HUB_DEMO_PORT", "39251"))
    initialize_web_server()
    print(f"Field selector: http://{host}:{port}/")
    print(f"Admin UI demo: http://{host}:{port}/demo/mqtt-devices")
    print(f"Installation layout: http://{host}:{port}/fields/demo-strawberry-field/layout")
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
