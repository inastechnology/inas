#!/usr/bin/env python3
import copy
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

DEMO_FIELD_ID = "demo-strawberry-field"
DEMO_FIELD_NAME = "イチゴ実証圃場"
DEMO_GREENHOUSE_SPACE_ID = "space-demo-greenhouse-1"
DEMO_PRIMARY_RIDGE_ID = "placement-demo-ridge-1"


def _demo_layout_payload(current: dict):
    """Return an idempotent starter layout for an otherwise empty demo field."""
    if any(space.get("placements") for space in current.get("spaces", [])):
        return current

    seeded = copy.deepcopy(current)
    root = next(space for space in seeded["spaces"] if space["id"] == seeded["root_space_id"])
    root["name"] = DEMO_FIELD_NAME
    root["north_angle_deg"] = 8
    root["placements"] = [
        {
            "id": "placement-demo-greenhouse-1",
            "preset": "greenhouse",
            "name": "1号ハウス",
            "x": 2,
            "y": 2,
            "width": 24,
            "height": 15,
            "rotation": 0,
            "child_space_id": DEMO_GREENHOUSE_SPACE_ID,
            "memo": "イチゴ高設・土耕栽培の実証区画",
        },
        {
            "id": "placement-demo-source-tank",
            "preset": "tank",
            "name": "原水タンク",
            "x": 28,
            "y": 3,
            "width": 4,
            "height": 4,
            "rotation": 0,
            "memo": "自動潅水用の原水タンク",
        },
        {
            "id": "placement-demo-environment-sensor",
            "preset": "sensor",
            "name": "屋外環境センサー",
            "x": 34,
            "y": 3,
            "width": 2,
            "height": 2,
            "rotation": 0,
            "binding": {
                "device_id": "INADS-DEMO-ENV-002",
                "resource_type": "device",
                "resource_id": "",
                "target_placement_ids": ["placement-demo-greenhouse-1"],
            },
        },
    ]
    seeded["spaces"].append(
        {
            "id": DEMO_GREENHOUSE_SPACE_ID,
            "name": "1号ハウス 内部",
            "space_type": "greenhouse",
            "north_angle_deg": 8,
            "grid": {"columns": 40, "rows": 28, "cell_size_m": 0.5},
            "placements": [
                {
                    "id": DEMO_PRIMARY_RIDGE_ID,
                    "preset": "ridge",
                    "name": "イチゴ畝A",
                    "x": 4,
                    "y": 4,
                    "width": 27,
                    "height": 3,
                    "rotation": 0,
                    "memo": "紅ほっぺ 36株 / 点滴ラインA",
                },
                {
                    "id": "placement-demo-ridge-2",
                    "preset": "ridge",
                    "name": "イチゴ畝B",
                    "x": 4,
                    "y": 10,
                    "width": 27,
                    "height": 3,
                    "rotation": 0,
                    "memo": "比較栽培区 / 点滴ラインB",
                },
                {
                    "id": "placement-demo-ridge-3",
                    "preset": "ridge",
                    "name": "育苗ベッド",
                    "x": 4,
                    "y": 16,
                    "width": 18,
                    "height": 3,
                    "rotation": 0,
                },
                {
                    "id": "placement-demo-watering-device",
                    "preset": "watering_device",
                    "name": "点滴潅水コントローラー",
                    "x": 33,
                    "y": 5,
                    "width": 3,
                    "height": 3,
                    "rotation": 0,
                    "binding": {
                        "device_id": "INADS-DEMO-WTR-001",
                        "resource_type": "device",
                        "resource_id": "",
                        "target_placement_ids": [DEMO_PRIMARY_RIDGE_ID, "placement-demo-ridge-2"],
                    },
                },
                {
                    "id": "placement-demo-soil-sensor",
                    "preset": "sensor",
                    "name": "畝A 土壌センサー",
                    "x": 25,
                    "y": 4,
                    "width": 2,
                    "height": 2,
                    "rotation": 0,
                    "binding": {
                        "device_id": "INADS-DEMO-SOI-001",
                        "resource_type": "device",
                        "resource_id": "",
                        "target_placement_ids": [DEMO_PRIMARY_RIDGE_ID],
                    },
                },
                {
                    "id": "placement-demo-house-sensor",
                    "preset": "sensor",
                    "name": "ハウス温湿度・光センサー",
                    "x": 20,
                    "y": 20,
                    "width": 2,
                    "height": 2,
                    "rotation": 0,
                    "binding": {
                        "device_id": "INADS-DEMO-ENV-001",
                        "resource_type": "device",
                        "resource_id": "",
                        "target_placement_ids": [DEMO_PRIMARY_RIDGE_ID, "placement-demo-ridge-2"],
                    },
                },
                {
                    "id": "placement-demo-camera",
                    "preset": "camera",
                    "name": "生育記録カメラ",
                    "x": 32,
                    "y": 19,
                    "width": 2,
                    "height": 2,
                    "rotation": 0,
                    "binding": {
                        "device_id": "INADS-DEMO-CAM-001",
                        "resource_type": "device",
                        "resource_id": "",
                        "target_placement_ids": [DEMO_PRIMARY_RIDGE_ID, "placement-demo-ridge-2"],
                    },
                },
            ],
        }
    )
    return seeded


def _demo_extra_calendar_actions(today: date):
    return [
        {
            "action_type": "watering",
            "title": "手動潅水の要否を確認",
            "priority": "recommended",
            "window_start": (today - timedelta(days=5)).isoformat(),
            "window_end": (today - timedelta(days=1)).isoformat(),
            "timing_label": "自動潅水の稼働確認後",
            "reason": "自動潅水で不足がないか、土壌水分と末端の吐出を確認するためです。",
            "instructions": "土壌水分が目標内なら手動潅水は行わず、見送り理由を記録します。",
            "tags": ["自動潅水", "土壌水分", "見送り判断"],
            "estimated_minutes": 15,
            "source": "demo",
        },
        {
            "action_type": "pollination",
            "title": "開花と受粉環境を整える",
            "priority": "recommended",
            "window_start": (today + timedelta(days=75)).isoformat(),
            "window_end": (today + timedelta(days=98)).isoformat(),
            "timing_label": "花房の開花が始まる頃",
            "reason": "開花状況、温湿度、訪花昆虫の動きを確認して着果を安定させるためです。",
            "instructions": "開花率と花粉の状態を確認し、必要な場合だけ受粉を補助します。",
            "tags": ["開花", "受粉", "着果"],
            "estimated_minutes": 25,
            "source": "demo",
        },
        {
            "action_type": "harvest",
            "title": "適熟果を選んで収穫・品質記録",
            "priority": "required",
            "window_start": (today + timedelta(days=105)).isoformat(),
            "window_end": (today + timedelta(days=300)).isoformat(),
            "timing_label": "収穫期を通して継続",
            "reason": "色、硬さ、糖度、収量を記録し、潅水と施肥の改善につなげるためです。",
            "instructions": "過熟果と傷んだ果実を分け、収穫量と品質を記録します。",
            "tags": ["収穫", "品質", "記録"],
            "estimated_minutes": 40,
            "source": "demo",
        },
    ]


def _prepare_demo_calendar_actions(actions: list, today: date):
    prepared = copy.deepcopy(actions)
    prepared[0]["window_start"] = (today - timedelta(days=10)).isoformat()
    prepared[0]["window_end"] = (today - timedelta(days=3)).isoformat()
    prepared[1]["window_start"] = (today - timedelta(days=1)).isoformat()
    prepared[1]["window_end"] = (today + timedelta(days=6)).isoformat()
    prepared[2]["window_start"] = (today + timedelta(days=2)).isoformat()
    prepared[2]["window_end"] = (today + timedelta(days=10)).isoformat()
    return prepared + _demo_extra_calendar_actions(today)


def _ensure_demo_layout(repository):
    current = repository.get(DEMO_FIELD_ID, field_name=DEMO_FIELD_NAME)
    payload = _demo_layout_payload(current)
    if payload is current:
        return current
    return repository.upsert(DEMO_FIELD_ID, payload, field_name=DEMO_FIELD_NAME, updated_by="demo-fixture")


def _ensure_demo_fertilizer(repository, planting: dict, today: date):
    if repository.fertilizer_applications_for_planting(planting["id"]):
        return
    repository.create_fertilizer_application(
        planting["id"],
        {
            "applied_on": (today - timedelta(days=45)).isoformat(),
            "material_kind": "cattle_manure",
            "material_name": "完熟牛ふん堆肥（デモ）",
            "amount_kg": 20,
            "nutrient_percent": {"n": 2, "p2o5": 1, "k2o": 1.5, "mgo": 0.5},
            "annual_available_percent": 10,
            "effect_years": 3,
            "start_delay_days": 7,
            "analysis_source": "製品表示を想定したデモ値",
            "notes": "残存肥効と追肥判断の画面確認用。実際の施肥量は土壌分析と製品表示から決めます。",
        },
    )


def _ensure_demo_cultivation(layout: dict, plant_repository, ai_service, *, today: date):
    valid_placement_ids = {
        placement.get("id")
        for space in layout.get("spaces", [])
        for placement in space.get("placements", [])
    }
    bundle = plant_repository.field_bundle(DEMO_FIELD_ID)
    for planting in bundle["plantings"]:
        if planting.get("status") == "active" and planting.get("placement_id") not in valid_placement_ids:
            plant_repository.update_planting(planting["id"], {"status": "removed"})

    if DEMO_PRIMARY_RIDGE_ID not in valid_placement_ids:
        return None
    active = next(
        (
            planting
            for planting in plant_repository.field_bundle(DEMO_FIELD_ID)["plantings"]
            if planting.get("status") == "active" and planting.get("placement_id") == DEMO_PRIMARY_RIDGE_ID
        ),
        None,
    )
    if active is None:
        active = plant_repository.create_planting(
            DEMO_FIELD_ID,
            {
                "space_id": DEMO_GREENHOUSE_SPACE_ID,
                "placement_id": DEMO_PRIMARY_RIDGE_ID,
                "placement_name": "イチゴ畝A",
                "crop_name": "イチゴ",
                "cultivar": "紅ほっぺ",
                "crop_category": "vegetable",
                "planted_on": (today - timedelta(days=42)).isoformat(),
                "plant_count": 36,
                "cultivation_method": "ridge_mulch",
                "conditions": {
                    "environment": "1号ハウス・点滴潅水",
                    "soil_or_substrate": "畑土・高畝・黒マルチ",
                    "region": "長野県伊那市",
                    "sunlight": "日なた（直射6時間以上）",
                    "notes": "自動潅水とカメラ記録を併用。作業は週1回を基本とするデモ栽培です。",
                },
                "growth_targets": {
                    "soil_moisture_percent": {"min": 35, "max": 60},
                    "soil_ec_us_cm": {"min": 500, "max": 1200},
                    "soil_ph": {"min": 5.5, "max": 6.5},
                    "air_humidity_percent": {"min": 50, "max": 75},
                    "par_umol_m2_s": {"min": 300, "max": 1000},
                },
                "memo": "年間栽培カレンダーの操作確認用データ",
            },
        )

    _ensure_demo_fertilizer(plant_repository, active, today)
    if plant_repository.get_calendar(active["id"]):
        return active

    context = {
        "planting": active,
        "planning": {
            "start_date": today.isoformat(),
            "horizon_months": 12,
            "notes": "1か月に1回の定期作業。それ以外は自動潅水とカメラで監視。",
        },
        "fertilizer_history": plant_repository.fertilizer_effect_context(active["id"], as_of=today),
    }
    generated = ai_service.generate_plant_calendar(context)
    actions = _prepare_demo_calendar_actions(generated["actions"], today)
    ai_service._ensure_action_work_plans(actions)
    plant_repository.update_planting(active["id"], {"growth_targets": generated["growth_targets"]})
    calendar = plant_repository.create_calendar(
        active["id"],
        actions,
        generated["generation"],
        care_profile=generated["care_profile"],
        task_rules=generated["task_rules"],
    )

    completed = calendar["actions"][0]
    plant_repository.update_action(active["id"], completed["id"], {"status": "in_progress"})
    plant_repository.complete_action(
        active["id"],
        completed["id"],
        today.isoformat(),
        "葉色・新葉・土壌水分を確認。生育は安定しており、写真記録も保存しました。",
        rating=4,
        work_details={
            "execution": {
                "method_id": "observe-and-record",
                "method_label": "観察して記録",
                "method_type": "observation",
                "follow_up_days": 7,
            }
        },
    )
    plant_repository.update_action(active["id"], calendar["actions"][1]["id"], {"status": "in_progress"})
    skipped = calendar["actions"][-3]
    plant_repository.skip_action(
        active["id"],
        skipped["id"],
        today.isoformat(),
        "already_satisfied",
        "土壌水分42%で目標範囲内。点滴ライン末端まで正常に吐出していることを確認しました。",
        "自動潅水で必要量を供給できているため、手動潅水は見送ります。",
        next_review_on=(today + timedelta(days=1)).isoformat(),
        decided_by="デモ担当者",
        use_as_guidance=False,
    )
    return active


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
        "id": "INADS-DEMO-FGT-001",
        "name": "イチゴ液肥ステーション",
        "kind": "FGT",
        "location": "未設置",
        "status": {
            "fgt_phase": "idle",
            "fgt_fault": "none",
            "batch_completed": True,
            "inlet_water_ml": 5020,
            "nutrient_batch_water_target_ml": 5000,
            "soil_rs485_ok": True,
            "soil_moisture_percent": 44.0,
            "soil_temperature_c": 21.6,
            "soil_ec_us_cm": 740,
            "soil_ph": 6.1,
            "soil_n_mg_kg": 82,
            "soil_p_mg_kg": 41,
            "soil_k_mg_kg": 96,
            "par_ok": False,
        },
        "switches": (),
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
    # The confirmation demo must remain reachable even when .env is configured
    # for the Cloudflare Access protected production server.
    os.environ["HUB_AUTH_MODE"] = "local"
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

    from ina_device_hub.ai_content_service import ai_content_service
    from ina_device_hub.device_config_service import device_config_service
    from ina_device_hub.field_layout_repository import field_layout_repository
    from ina_device_hub.field_repository import field_repository
    from ina_device_hub.plant_calendar_generation_task import plant_calendar_generation_task
    from ina_device_hub.plant_management_repository import plant_management_repository
    from ina_device_hub.plant_task_notification_task import plant_task_notification_task
    from ina_device_hub.web_server import app, initialize_web_server

    field_repository().upsert(
        DEMO_FIELD_ID,
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
            "device_ids": ["INADS-DEMO-WTR-001", "INADS-DEMO-WTR-002", "INADS-DEMO-WTR-003", "INADS-DEMO-ENV-001"],
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

    layout_repository = field_layout_repository()
    layout = _ensure_demo_layout(layout_repository)
    plant_repository = plant_management_repository()
    content_service = ai_content_service()
    _ensure_demo_cultivation(layout, plant_repository, content_service, today=date.today())
    for planting in plant_repository.field_bundle(DEMO_FIELD_ID)["plantings"]:
        calendar = plant_repository.get_calendar(planting["id"])
        if planting.get("status") != "active" or not calendar or calendar.get("task_rules"):
            continue
        generated = content_service.generate_plant_calendar(
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
    plant_calendar_generation_task().start()
    plant_task_notification_task().start()
    print(f"Field selector: http://{host}:{port}/")
    print(f"Admin UI demo: http://{host}:{port}/demo/mqtt-devices")
    print(f"Cultivation calendar: http://{host}:{port}/fields/{DEMO_FIELD_ID}/calendar")
    print(f"Installation layout: http://{host}:{port}/fields/{DEMO_FIELD_ID}/layout")
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
