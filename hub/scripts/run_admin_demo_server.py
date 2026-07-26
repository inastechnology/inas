#!/usr/bin/env python3
import copy
import os
import sys
from datetime import UTC, date, datetime, timedelta
from html import escape
from pathlib import Path

from dotenv import load_dotenv

DEMO_FIELD_ID = "demo-strawberry-field"
DEMO_FIELD_NAME = "イチゴ実証圃場"
DEMO_GREENHOUSE_SPACE_ID = "space-demo-greenhouse-1"
DEMO_PRIMARY_RIDGE_ID = "placement-demo-ridge-1"

DEMO_SETUP_REASONS = {
    "unconfigured": "Connection settings are not configured yet.",
    "button": "Setup mode was requested with the BOOT button.",
    "connection_reset": "Connection settings were cleared with the BOOT button.",
    "wifi_failure": "Wi-Fi connection failed before reaching the MQTT broker.",
    "mqtt_failure": "MQTT broker connection failed after Wi-Fi connected.",
}


def _demo_today():
    configured = os.environ.get("HUB_DEMO_TODAY", "").strip()
    if not configured:
        return date.today()
    try:
        return date.fromisoformat(configured)
    except ValueError as exc:
        raise RuntimeError("HUB_DEMO_TODAY must use YYYY-MM-DD") from exc


def _docs_demo_device_setup_page(reason: str, *, populated: bool = False):
    """Render the setup portal from app_initial_setting.cpp with safe demo values."""
    reason = reason if reason in DEMO_SETUP_REASONS else "unconfigured"
    ssid = "INAS-Demo-2G" if populated else ""
    broker = "192.0.2.10" if populated else ""
    username = "demo-device" if populated else ""
    return f"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>INA Water Controller Setup</title>
    <style>
      body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f6f7f9;color:#1f2933}}
      main{{max-width:520px;margin:0 auto;padding:28px 18px}}
      h1{{font-size:24px;margin:0 0 8px}}p{{margin:0 0 20px;color:#52606d;line-height:1.5}}
      form{{background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:18px;box-shadow:0 1px 2px rgba(15,23,42,.06)}}
      label{{display:block;font-weight:600;margin:14px 0 6px}}
      input{{box-sizing:border-box;width:100%;font:inherit;padding:10px 12px;border:1px solid #bcccdc;border-radius:6px;background:#fff}}
      input:focus{{outline:2px solid #2f80ed33;border-color:#2f80ed}}
      .row{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}.hint{{font-size:13px;color:#627d98;margin-top:6px}}
      .reason{{background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:12px 14px;margin:14px 0 16px;color:#7c2d12}}
      .reason strong{{display:block;margin-bottom:4px}}.reason code{{font-size:12px;color:#9a3412}}
      button{{width:100%;margin-top:20px;padding:12px 14px;border:0;border-radius:6px;background:#1f6feb;color:#fff;font-weight:700;font:inherit}}
      @media(max-width:520px){{.row{{grid-template-columns:1fr}}}}
    </style>
  </head>
  <body>
    <main>
      <h1>INA Water Controller Setup</h1>
      <p>Wi-Fi and MQTT settings are saved on the device. It will restart after saving.</p>
      <section class="reason">
        <strong>AP mode reason</strong>
        {escape(DEMO_SETUP_REASONS[reason])}<br>
        <code>{escape(reason)}</code>
      </section>
      <form method="post" action="/save">
        <label for="ssid">Wi-Fi SSID</label>
        <input id="ssid" name="ssid" required maxlength="255" value="{escape(ssid)}">
        <label for="password">Wi-Fi Password</label>
        <input id="password" name="password" type="password" maxlength="255" autocomplete="new-password">
        <div class="hint">Leave blank to keep the current Wi-Fi password.</div>
        <label for="mqtt_broker">MQTT Broker</label>
        <input id="mqtt_broker" name="mqtt_broker" required maxlength="255" value="{escape(broker)}">
        <div class="row">
          <div>
            <label for="mqtt_port">MQTT Port</label>
            <input id="mqtt_port" name="mqtt_port" type="number" min="1" max="65535" required value="1883">
          </div>
          <div>
            <label for="mqtt_username">MQTT Username</label>
            <input id="mqtt_username" name="mqtt_username" maxlength="255" value="{escape(username)}">
          </div>
        </div>
        <label for="mqtt_password">MQTT Password</label>
        <input id="mqtt_password" name="mqtt_password" type="password" maxlength="255" autocomplete="new-password">
        <div class="hint">Leave blank to keep the current MQTT password. Leave MQTT username and password both blank when authentication is not used.</div>
        <button type="submit">Save and Restart</button>
      </form>
    </main>
  </body>
</html>"""


def _docs_demo_index_page():
    links = (
        ("デバイス初回設定", "/docs-demo/device-setup?reason=unconfigured", "ESP32 setup AP / 未設定"),
        ("Wi-Fi 接続失敗からの再設定", "/docs-demo/device-setup?reason=wifi_failure&populated=1", "ESP32 setup AP / 再設定"),
        ("圃場一覧", "/fields", "登録済み圃場"),
        ("圃場ダッシュボード", f"/fields/{DEMO_FIELD_ID}", "環境値・作業・設置状況"),
        ("設置ビュー", f"/fields/{DEMO_FIELD_ID}/layout?space={DEMO_GREENHOUSE_SPACE_ID}", "ハウス内の機器配置"),
        ("機器一覧", "/mqtt-devices", "登録済み機器"),
        ("潅水機の概要", "/mqtt-devices/INADS-DEMO-WTR-001", "動作確認"),
        ("潅水設定", "/mqtt-devices/INADS-DEMO-WTR-001?tab=settings", "Runtime Config"),
        ("機器ソフトウェア更新", "/mqtt-devices/INADS-DEMO-WTR-001?tab=firmware", "F/W・OTA"),
        ("保守・管理", "/mqtt-devices/INADS-DEMO-WTR-003?tab=maintenance", "承認待ち・接続履歴"),
        ("圃場の作業", f"/fields/{DEMO_FIELD_ID}/calendar?view=work", "AI提案後の作業ボード"),
        ("作物別の栽培計画", f"/fields/{DEMO_FIELD_ID}/calendar?view=crop", "栽培基準・施肥・AI計画"),
        ("AI変更案の比較", f"/fields/{DEMO_FIELD_ID}/calendar?view=crop&review=ai", "現在案とAI案"),
    )
    cards = "".join(
        f'<a class="card" href="{escape(href)}"><strong>{escape(title)}</strong><span>{escape(description)}</span><code>{escape(href)}</code></a>'
        for title, href, description in links
    )
    return f"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>INAS documentation demo states</title>
    <style>
      *{{box-sizing:border-box}}body{{margin:0;color:#203129;background:#eef3ef;font-family:system-ui,-apple-system,sans-serif}}
      main{{width:min(1080px,calc(100% - 32px));margin:32px auto 64px}}
      h1{{margin-bottom:6px;font-size:28px}}p{{margin:0 0 24px;color:#5a6d63}}
      .notice{{margin:0 0 22px;padding:13px 15px;border:1px solid #9fc6ae;border-radius:8px;color:#20553b;background:#e5f5eb}}
      .grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}
      .card{{display:grid;gap:7px;min-height:132px;padding:16px;border:1px solid #c8d4cc;border-radius:9px;color:inherit;background:#fff;text-decoration:none;box-shadow:0 3px 12px #1f44321a}}
      .card:hover{{border-color:#438263;transform:translateY(-1px)}}.card span{{color:#607168;font-size:14px}}.card code{{margin-top:auto;overflow-wrap:anywhere;color:#2c6a4d;font-size:11px}}
      @media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}
    </style>
  </head>
  <body>
    <main>
      <h1>ドキュメント撮影用デモ状態</h1>
      <p>画面を切り替えて、各ガイドに対応する状態を確認できます。</p>
      <div class="notice"><strong>運用データとは分離されています。</strong> この一覧は <code>run_admin_demo_server.py</code> で起動した一時デモだけに存在します。</div>
      <div class="grid">{cards}</div>
    </main>
  </body>
</html>"""


def _register_docs_demo_routes(app):
    from flask import request

    def docs_demo_index():
        return _docs_demo_index_page()

    def docs_demo_device_setup():
        populated = request.args.get("populated") == "1"
        return _docs_demo_device_setup_page(request.args.get("reason", ""), populated=populated)

    app.add_url_rule("/docs-demo", endpoint="docs_demo_index", view_func=docs_demo_index, methods=["GET"])
    app.add_url_rule("/docs-demo/device-setup", endpoint="docs_demo_device_setup", view_func=docs_demo_device_setup, methods=["GET"])


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
                        "resource_type": "camera",
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
    custom_material = next(
        (item for item in repository.list_fertilizer_materials() if item.get("scope") == "user" and item.get("label") == "瀬戸内いちご有機配合"), None
    )
    if custom_material is None:
        custom_material = repository.create_fertilizer_material(
            {
                "label": "瀬戸内いちご有機配合",
                "summary": "デモ圃場で元肥と追肥に使う登録済み製品",
                "material_kind": "organic_fertilizer",
                "material_name": "瀬戸内いちご有機配合 6-4-3",
                "nutrient_percent": {"n": 6, "p2o5": 4, "k2o": 3, "mgo": 1},
                "annual_available_percent": 50,
                "effect_years": 1,
                "start_delay_days": 7,
                "analysis_source": "製品ラベルを想定したデモ値",
            }
        )
    if repository.fertilizer_applications_for_planting(planting["id"]):
        return
    repository.create_fertilizer_application(
        planting["id"],
        {
            "material_id": custom_material["id"],
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
    valid_placement_ids = {placement.get("id") for space in layout.get("spaces", []) for placement in space.get("placements", [])}
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
                    "air_temperature_c": {"min": 12, "max": 30},
                    "air_humidity_percent": {"min": 50, "max": 75},
                    "soil_moisture_percent": {"min": 35, "max": 60},
                    "soil_temperature_c": {"min": 12, "max": 26},
                    "soil_ec_us_cm": {"min": 500, "max": 1200},
                    "soil_ph": {"min": 5.5, "max": 6.5},
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
        "recent_work_logs": [
            {
                "performed_on": (today - timedelta(days=7)).isoformat(),
                "action_type": "observation",
                "title": "葉色と新葉を定点確認",
                "note": "葉色と展開中の新葉を確認し、生育は安定していました。",
                "rating": 4,
                "execution": {"target": "イチゴ畝A", "method_label": "定点観察"},
                "attachment_count": 1,
            }
        ],
        "recent_questions": [
            {
                "created_at": (today - timedelta(days=5)).isoformat(),
                "question": "葉色が薄いときは何を先に確認しますか？",
                "previous_answer": "EC、pH、根域の水分、直近の施肥を順に確認します。",
            }
        ],
        "crop_knowledge": {
            "status": "available",
            "provider": "demo_fixture",
            "cache_hit": False,
            "summary": [
                "施肥量は都道府県の施肥基準、土壌分析、土壌診断基準を照合して調整します。",
                "イチゴの株姿と葉・花・果実の変化を定点観察し、作業判断を記録します。",
            ],
            "assumptions": ["デモでは公的資料の表示とリンク動作を確認できる要約を使用しています。"],
            "fetched_at": today.isoformat(),
            "sources": [
                {
                    "title": "都道府県施肥基準等",
                    "url": "https://www.maff.go.jp/j/seisan/kankyo/hozen_type/h_sehi_kizyun/index.html",
                    "publisher": "農林水産省",
                    "applicable_region": "都道府県別",
                    "published_at": "",
                    "fetched_at": today.isoformat(),
                },
                {
                    "title": "種苗管理センターが作成した特性調査マニュアル（イチゴ属）",
                    "url": "https://www.naro.go.jp/laboratory/ncss/saibaishiken/manual/index.html",
                    "publisher": "農研機構",
                    "applicable_region": "日本",
                    "published_at": "",
                    "fetched_at": today.isoformat(),
                },
            ],
        },
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
    plant_repository.update_action(
        active["id"],
        completed["id"],
        {"status": "in_progress", "assigned_to": "demo-operator@ina.local"},
    )
    plant_repository.complete_action(
        active["id"],
        completed["id"],
        today.isoformat(),
        "葉色・新葉・土壌水分を確認。生育は安定しており、写真記録も保存しました。",
        rating=4,
        performed_by="demo-operator@ina.local",
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
    approved = calendar["actions"][2]
    plant_repository.update_action(
        active["id"],
        approved["id"],
        {"status": "in_progress", "assigned_to": "demo-worker@ina.local"},
    )
    plant_repository.complete_action(
        active["id"],
        approved["id"],
        (today - timedelta(days=1)).isoformat(),
        "作業手順どおりに実施し、対象箇所の状態と写真を提出しました。",
        rating=5,
        performed_by="demo-worker@ina.local",
        work_details={
            "execution": {
                "method_id": "follow-work-guide",
                "method_label": "作業ガイドに沿って実施",
                "method_type": "field_work",
                "follow_up_days": 3,
            }
        },
    )
    plant_repository.review_action_completion(
        active["id"],
        approved["id"],
        "approved",
        reviewed_by="demo-manager@ina.local",
        note="写真と作業内容を確認しました。",
    )
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


def _demo_ai_review_payload(calendar: dict, planting: dict, *, today: date):
    current_actions = [
        copy.deepcopy(action)
        for action in calendar.get("actions", [])
        if action.get("status") in {"planned", "in_progress"} and str(action.get("window_end") or "") >= today.isoformat()
    ]
    planned = next((action for action in current_actions if action.get("status") == "planned"), None)
    if planned is not None:
        planned["reason"] = "直近の生育記録と土壌水分が安定しているため、果実の肥大と着色を同じ巡回で確認する提案です。"
        planned["instructions"] = "代表株を同じ位置から撮影し、果実径、着色、葉色、土壌水分を記録します。異常がなければ現在の潅水条件を維持します。"
        planned["tags"] = list(dict.fromkeys([*(planned.get("tags") or []), "AI見直し", "定点記録"]))
        planned["source"] = "ai_replanned"

    current_actions.append(
        {
            "action_type": "observation",
            "title": "果実肥大と着色を定点確認",
            "priority": "recommended",
            "window_start": (today + timedelta(days=7)).isoformat(),
            "window_end": (today + timedelta(days=12)).isoformat(),
            "timing_label": "次回の圃場巡回時",
            "reason": "収穫期へ向けて潅水条件を変える前に、果実と株姿の変化を同じ条件で比較するためです。",
            "instructions": "イチゴ畝Aの代表株3株を撮影し、果実径、着色、葉色を記録します。土壌水分と前回写真も並べて確認します。",
            "tags": ["AI提案", "果実肥大", "定点観察"],
            "estimated_minutes": 20,
            "source": "ai_replanned",
            "work_plan": {
                "targets": ["イチゴ畝Aの代表株3株"],
                "checkpoints": ["同じ撮影位置を使う", "果実径と着色を記録", "土壌水分を併記"],
                "start_conditions": ["圃場へ安全に立ち入れる"],
                "skip_conditions": ["強風・豪雨で定点撮影ができない"],
                "completion_criteria": ["写真と観察値を作業記録へ保存"],
            },
        }
    )
    return {
        "actions": current_actions,
        "growth_targets": copy.deepcopy(planting.get("growth_targets") or {}),
        "care_profile": copy.deepcopy(calendar.get("care_profile") or {}),
        "task_rules": copy.deepcopy(calendar.get("task_rules") or []),
        "generation": {
            "source": "demo_fixture",
            "model": "documentation-review",
            "generated_at": today.isoformat(),
            "context_snapshot": {"scenario": "documentation"},
        },
    }


def _ensure_demo_ai_review(plant_repository, planting: dict, *, today: date):
    if planting is None:
        return None
    bundle = plant_repository.field_bundle(DEMO_FIELD_ID)
    active = next(
        (
            task
            for task in bundle.get("generation_tasks", [])
            if task.get("planting_id") == planting["id"] and task.get("status") in {"queued", "running", "awaiting_review"}
        ),
        None,
    )
    if active is not None:
        return active

    calendar = plant_repository.get_calendar(planting["id"])
    if not calendar:
        return None
    queued = plant_repository.enqueue_calendar_generation(
        planting["id"],
        kind="regenerate",
        start_date=today.isoformat(),
        planning_notes="収穫期へ向けた定点観察を追加し、現在の作業と比較できる変更案を作るデモです。",
        mode="review",
    )
    claimed = plant_repository.claim_next_calendar_generation()
    if claimed is None or claimed.get("id") != queued["id"]:
        raise RuntimeError("documentation demo could not claim its AI review task")
    result = plant_repository.complete_calendar_generation(
        claimed["id"],
        _demo_ai_review_payload(calendar, planting, today=today),
    )
    return result["task"]


DEMO_LAYOUT_DEVICES = (
    {
        "id": "INADS-DEMO-WTR-001",
        "name": "デモ潅水機1",
        "kind": "WTR",
        "location": "イチゴ実証圃場",
        "status": {
            "last_soil_moisture": 42,
            "watering_started": False,
            "next_sleep_sec": 7200,
            "config_received": True,
            "time_synced": True,
        },
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
        "status": {"last_soil_moisture": 37, "watering_started": False, "next_sleep_sec": 7200},
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
    # Every connector and credential is replaced after loading .env. A value can
    # enter the demo only through an explicit HUB_DEMO_* override.
    demo_work_dir = os.environ.get("HUB_DEMO_WORK_DIR", "/tmp/ina-device-hub-demo/work")
    defaults = {
        "HUB_AUTH_MODE": "local",
        "HUB_LOCAL_USER_EMAIL": "demo-operator@ina.local",
        "HUB_ADMIN_EMAILS": "",
        "HUB_OPERATIONS_SERVICE_IDS": "",
        "HUB_BACKUP_DIR": str(Path(demo_work_dir) / "backups"),
        "HUB_HTTP_HOST": "127.0.0.1",
        "HUB_HTTP_PORT": "39151",
        "HUB_HTTP_SERVER": "flask",
        "HUB_SYNC_PARENT_ALLOW_INSECURE_LOOPBACK": "false",
        "HUB_SYNC_PARENT_BASE_URL": "",
        "HUB_SYNC_PARENT_TOKEN_FILE": "",
        "HUB_SYNC_PARENT_CA_FILE": "",
        "HUB_SYNC_PARENT_CLIENT_CERT_FILE": "",
        "HUB_SYNC_PARENT_CLIENT_KEY_FILE": "",
        "WORK_DIR": demo_work_dir,
        "LOCAL_STORAGE_BASE_DIR": str(Path(demo_work_dir) / "storage"),
        # A non-URL value makes InaDBConnector use SQLite under WORK_DIR.
        "TURSO_DATABASE_URL": "local-demo",
        "TURSO_AUTH_TOKEN": "local-demo",
        "S3_ENDPOINT_URL": "http://127.0.0.1:9",
        "S3_BUCKET_NAME": "demo",
        "S3_BUCKET_REGION": "auto",
        "S3_ACCESS_KEY": "demo",
        "S3_SECRET_KEY": "demo",
        "S3_TMP_ENDPOINT_URL": "",
        "S3_TMP_BUCKET_NAME": "",
        "S3_TMP_BUCKET_REGION": "auto",
        "S3_TMP_ACCESS_KEY": "",
        "S3_TMP_SECRET_KEY": "",
        "S3_TMP_BASE_URL": "",
        "MQTT_BROKER_URL": "localhost",
        "MQTT_BROKER_PORT": "1883",
        "MQTT_BROKER_USERNAME": "",
        "MQTT_BROKER_PASSWORD": "",
        "TIMELAPSE_INTERVAL": "600",
        "SENSOR_SAVE_IMAGE": "false",
        "SENSOR_SAVE_AUDIO": "false",
        "FIRMWARE_BASE_URL": "http://demo-hub.local:39151",
        "FIRMWARE_HOSTNAME": "demo-hub.local",
        "DEVICE_CONFIG_DEFAULT_NTP_SERVER": "192.0.2.10",
        "DEVICE_CONFIG_DEFAULT_TIMEZONE_OFFSET_SEC": "32400",
        "DEVICE_CONFIG_DEFAULT_MOISTURE_THRESHOLD": "35",
        "INSTAGRAM_USER_ID": "",
        "INSTAGRAM_ACCESS_TOKEN": "",
        "INSTAGRAM_SENSOR_ID": "",
        "INSTAGRAM_CAMERA_ID": "",
        "INSTAGRAM_ADMIN_USERNAME": "",
        "INSTAGRAM_PLANT_POSITION_PROMPT": "",
        "INSTAGRAM_WEATHER_FORECAST_URL": "https://www.data.jma.go.jp/developer/xml/feed/regular.xml",
        "INSTAGRAM_WEATHER_AREA_NAME": "長野県",
        "INSTAGRAM_WEATHER_OFFICE_NAME": "ドキュメント用",
        "INSTAGRAM_WEATHER_FORECAST_TITLE": "デモ天気予報",
        "SWITCHBOT_BASE_URL": "https://api.switch-bot.com/v1.1",
        "SWITCHBOT_OPEN_TOKEN": "",
        "SWITCHBOT_SECRET_KEY": "",
        "SWITCHBOT_PLUG_MINI_DEVICE_ID": "",
        "AI_ENABLED": "false",
        "AI_IMAGE_ANALYZE_API_KEY": "",
        "AI_IMAGE_ANALYZE_BASE_URL": "",
        "AI_IMAGE_ANALYZE_MODEL": "",
        "AI_TEXT_ANALYZE_API_KEY": "",
        "AI_TEXT_ANALYZE_BASE_URL": "",
        "AI_TEXT_ANALYZE_MODEL": "",
        "AI_PLANT_CALENDAR_WEB_KNOWLEDGE_ENABLED": "false",
        "DISCORD_ENABLED": "false",
        "DISCORD_WEBHOOK_URL": "",
        "DISCORD_NOTIFY_MQTT_ACTIVITY": "false",
        "DISCORD_NOTIFY_OPERATIONS_SECURITY_ALERTS": "false",
        "DISCORD_NOTIFY_NEW_DEVICE": "false",
        "DISCORD_NOTIFY_DEVICE_OFFLINE": "false",
        "DISCORD_NOTIFY_WATERING_MISSING": "false",
        "DISCORD_NOTIFY_SOIL_CALIBRATION_SUGGESTED": "false",
        "DISCORD_NOTIFY_PLANT_TASKS": "false",
        "DISCORD_PLANT_TASK_NOTIFY_NEW": "false",
        "DISCORD_PLANT_TASK_NOTIFY_ON_START_DAY": "false",
        "DISCORD_PLANT_TASK_NOTIFY_DURING_WINDOW": "false",
        "WEATHER_RECORD_ENABLED": "false",
        "WEATHER_PROVIDER": "open_meteo",
        "WEATHER_LATITUDE": "36.0",
        "WEATHER_LONGITUDE": "138.0",
        "WEATHER_TIMEZONE": "Asia/Tokyo",
        "WEATHER_OPEN_METEO_ARCHIVE_URL": "https://archive-api.open-meteo.com/v1/archive",
        "WEATHER_FORECAST_URL": "https://www.data.jma.go.jp/developer/xml/feed/regular.xml",
        "WEATHER_AREA_NAME": "長野県",
        "WEATHER_OFFICE_NAME": "ドキュメント用",
        "WEATHER_FORECAST_TITLE": "デモ天気予報",
        "HEALTH_MONITOR_ENABLED": "false",
        "CLOUDFLARE_ACCOUNT_ID": "",
        "CLOUDFLARE_ACCESS_API_TOKEN": "",
        "CLOUDFLARE_ACCESS_ALLOWED_EMAILS": "",
        "CLOUDFLARE_ACCESS_ALLOWED_EMAIL_DOMAINS": "",
        "CLOUDFLARE_ACCESS_APP_ID": "",
        "CLOUDFLARE_ACCESS_APP_NAME": "",
        "CLOUDFLARE_ACCESS_GROUP_ID": "",
        "CLOUDFLARE_ACCESS_GROUP_NAME": "",
        "CLOUDFLARE_ACCESS_POLICY_ID": "",
        "CLOUDFLARE_ACCESS_POLICY_NAME": "",
        "CLOUDFLARE_ACCESS_TEAM_DOMAIN": "",
        "CLOUDFLARE_ACCESS_POLICY_AUD": "",
        "CLOUDFLARE_TUNNEL_ID": "",
        "CLOUDFLARE_TUNNEL_NAME": "",
        "CLOUDFLARE_TUNNEL_HOSTNAME": "",
        "CLOUDFLARE_TUNNEL_ORIGIN_URL": "",
        "CLOUDFLARE_TUNNEL_DNS_RECORD_ID": "",
        "CLOUDFLARE_TUNNEL_TOKEN_FILE": "",
        "CLOUDFLARE_ZONE_ID": "",
        "CLOUDFLARE_ZONE_NAME": "",
    }
    for name, default in defaults.items():
        os.environ[name] = os.environ.get(f"HUB_DEMO_{name}", default)
    os.environ["CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME"] = os.environ.get(
        "HUB_DEMO_PUBLIC_HOSTNAME",
        "hub-demo.inas-technologies.com",
    )


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


def _seed_demo_connection_history(event_writer, *, now=None):
    now = now or datetime.now(UTC)
    device_id = "INADS-DEMO-WTR-003"
    event_writer(
        "mqtt_client_connected",
        "broker",
        device_id,
        topic="$SYS/broker/log/N",
        action="connect",
        occurred_at=(now - timedelta(minutes=12)).isoformat(),
        payload={"client_id": device_id, "remote_address": "192.0.2.24:51411"},
    )
    event_writer(
        "mqtt_client_disconnected",
        "broker",
        device_id,
        topic="$SYS/broker/log/N",
        action="disconnect",
        occurred_at=(now - timedelta(minutes=10)).isoformat(),
        payload={"client_id": device_id, "reason": "disconnect"},
    )


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    _prepare_env()

    from ina_device_hub.ai_content_service import ai_content_service
    from ina_device_hub.camera_management_service import camera_management_service
    from ina_device_hub.device_config_service import device_config_service
    from ina_device_hub.device_event_log import append_device_event
    from ina_device_hub.field_layout_repository import field_layout_repository
    from ina_device_hub.field_repository import field_repository
    from ina_device_hub.plant_calendar_generation_task import plant_calendar_generation_task
    from ina_device_hub.plant_management_repository import plant_management_repository
    from ina_device_hub.plant_task_notification_task import plant_task_notification_task
    from ina_device_hub.timelapse_media_service import timelapse_media_service
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
            "camera_device_ids": ["INADS-DEMO-CAM-001"],
            "memo": "設置ビュー操作確認用のデモ圃場",
        },
    )

    config_service = device_config_service()
    # Legacy human-readable demo IDs are intentionally not sync identities.
    # The documentation demo is local-only, so it must not populate or consult
    # the hierarchical runtime-config cache.
    config_service.runtime_config_cache = None
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
        if device["kind"] == "FGT":
            config["fgt"] = {
                "enabled": True,
                "recipe": {
                    "total_water_ml": 5000,
                    "initial_water_ml": 1250,
                    "nutrient_a_ml": 10,
                    "nutrient_b_ml": 10,
                    "final_mix_sec": 180,
                    "rinse_water_ml": 500,
                },
            }
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
    demo_today = _demo_today()
    camera_service = camera_management_service()
    camera_service.repository.upsert(
        "INADS-DEMO-CAM-001",
        {
            "id": "INADS-DEMO-CAM-001",
            "name": "ハウス定点カメラ",
            "camera_type": "reolink",
            "ip_address": "192.168.1.84",
            "port": 554,
            "channel": 1,
            "stream": "main",
            "rtsp_path": "",
            "timelapse": True,
            "created_at": f"{demo_today.isoformat()}T06:00:00+00:00",
            "updated_at": f"{demo_today.isoformat()}T10:00:00+00:00",
        },
    )
    camera_service.credential_repository.set(
        "INADS-DEMO-CAM-001",
        username="demo-camera",
        password="demo-camera-password",
    )
    demo_camera_image = (root / "doc" / "jp" / "assets" / "inas-app-demo-poster.jpg").read_bytes()
    media_service = timelapse_media_service()
    for hour in (6, 7, 8, 9, 10):
        media_service.save_frame(
            "INADS-DEMO-CAM-001",
            demo_camera_image,
            captured_at=datetime(demo_today.year, demo_today.month, demo_today.day, hour, 0),
        )
    demo_planting = _ensure_demo_cultivation(layout, plant_repository, content_service, today=demo_today)
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
    if os.environ.get("HUB_DEMO_SCENARIO", "").strip().lower() == "documentation":
        _ensure_demo_ai_review(plant_repository, demo_planting, today=demo_today)
        _seed_demo_connection_history(append_device_event)

    host = os.environ.get("HUB_DEMO_HOST", "127.0.0.1")
    port = int(os.environ.get("HUB_DEMO_PORT", "39251"))
    _register_docs_demo_routes(app)
    initialize_web_server()
    plant_calendar_generation_task().start()
    plant_task_notification_task().start()
    print(f"Documentation demo states: http://{host}:{port}/docs-demo")
    print(f"Field selector: http://{host}:{port}/")
    print(f"Admin UI demo: http://{host}:{port}/demo/mqtt-devices")
    print(f"Cultivation calendar: http://{host}:{port}/fields/{DEMO_FIELD_ID}/calendar")
    print(f"Installation layout: http://{host}:{port}/fields/{DEMO_FIELD_ID}/layout")
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
