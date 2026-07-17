#!/usr/bin/env python3
"""Evaluate AI cultivation plans against repeatable user-value and safety checks."""

from __future__ import annotations

import argparse
import json
import os
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = REPO_ROOT / "data" / "plant_calendar_evaluation_cases.json"


def main():
    parser = argparse.ArgumentParser(description="AI栽培計画を日付、履歴、作業負荷、具体性、年間網羅性で評価します。")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="評価ケースJSON")
    parser.add_argument("--live", action="store_true", help="保存済みAI設定を使って実モデルを呼び出す")
    parser.add_argument("--output", help="詳細JSONレポートの保存先")
    parser.add_argument("--case", action="append", default=[], help="指定IDだけを評価。複数指定可")
    args = parser.parse_args()

    if not args.live:
        os.environ.setdefault("WORK_DIR", "/tmp/ina-device-hub-calendar-evaluation")
    from ina_device_hub.ai_content_service import AIContentService

    service = AIContentService()
    if not args.live:
        service.ai_settings = {**service.ai_settings, "enabled": False, "text_analyze_api_key": ""}
    cases = load_cases(Path(args.cases), selected=set(args.case))
    reports = [evaluate_case(service, case) for case in cases]
    for report in reports:
        status = "PASS" if report["quality"]["passed"] else "FAIL"
        source = report["generation_source"]
        print(f"[{status}] {report['id']}: {report['quality']['score']}/100 ({source})")
        for check in report["quality"]["checks"]:
            mark = "✓" if check["passed"] else "×"
            print(f"  {mark} {check['label']}: {check['details']}")

    summary = {
        "mode": "live" if args.live else "fallback",
        "evaluated_on": date.today().isoformat(),
        "passed": sum(1 for report in reports if report["quality"]["passed"]),
        "total": len(reports),
        "reports": reports,
    }
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"詳細レポート: {output_path}")
    if summary["passed"] != summary["total"]:
        raise SystemExit(1)


def load_cases(path: Path, *, selected: set[str] | None = None):
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(values, list):
        raise ValueError("evaluation case file must contain a cases array")
    cases = [value for value in values if isinstance(value, dict)]
    if selected:
        cases = [value for value in cases if str(value.get("id") or "") in selected]
    if not cases:
        raise ValueError("no evaluation cases selected")
    return cases


def evaluate_case(service, case: dict):
    from ina_device_hub.plant_calendar_quality import evaluate_plant_calendar

    context = build_context(case)
    calendar = service.generate_plant_calendar(context)
    quality = evaluate_plant_calendar(context, calendar, case.get("expectations"))
    return {
        "id": str(case.get("id") or "unnamed"),
        "description": str(case.get("description") or ""),
        "generation_source": str((calendar.get("generation") or {}).get("source") or "unknown"),
        "quality": quality,
        "actions": calendar.get("actions") or [],
    }


def build_context(case: dict):
    context = deepcopy(case.get("context") or {})
    planting = context.setdefault("planting", {})
    planning = context.setdefault("planning", {})
    current = date.today()
    planted_days_ago = max(0, int(case.get("planted_days_ago") or 0))
    planting["planted_on"] = (current - timedelta(days=planted_days_ago)).isoformat()
    planning["start_date"] = current.isoformat()
    planning["current_date"] = current.isoformat()
    planning["elapsed_days_since_planting"] = planted_days_ago
    planning["existing_planting"] = planted_days_ago > 0
    planning["exclude_past_actions"] = True
    return context


if __name__ == "__main__":
    main()
