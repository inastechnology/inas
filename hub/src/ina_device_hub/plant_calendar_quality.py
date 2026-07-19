from datetime import date, timedelta


def evaluate_plant_calendar(context: dict, calendar: dict, expectations: dict | None = None):
    expectations = expectations or {}
    actions = calendar.get("actions") if isinstance(calendar.get("actions"), list) else []
    task_rules = calendar.get("task_rules") if isinstance(calendar.get("task_rules"), list) else []
    planning = context.get("planning") if isinstance(context.get("planning"), dict) else {}
    planting = context.get("planting") if isinstance(context.get("planting"), dict) else context
    current = _parse_date(planning.get("current_date")) or date.today()
    requested = _parse_date(planning.get("start_date")) or _parse_date(planting.get("planted_on")) or current
    plan_start = max(current, requested)
    dated_actions = []
    invalid_ranges = []
    for action in actions:
        start = _parse_date(action.get("window_start")) if isinstance(action, dict) else None
        end = _parse_date(action.get("window_end")) if isinstance(action, dict) else None
        if start is not None and end is not None:
            dated_actions.append((start, end, action))
            if end < start:
                invalid_ranges.append(str(action.get("title") or "名称なし"))

    checks = []
    _check(checks, "actions_present", "作業候補がある", bool(actions), 5, f"{len(actions)}件")
    past_titles = [str(action.get("title") or "名称なし") for start, _end, action in dated_actions if start < plan_start]
    dates_complete = len(dated_actions) == len(actions)
    _check(
        checks,
        "future_only",
        "計画開始日以降だけを提案する",
        dates_complete and not past_titles,
        20,
        "過去日: " + ", ".join(past_titles) if past_titles else f"下限 {plan_start.isoformat()}",
    )
    _check(checks, "valid_windows", "作業期間が有効", dates_complete and not invalid_ranges, 5, ", ".join(invalid_ranges) or "有効")

    notes = str(planning.get("notes") or "")
    normalized_notes = notes.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    monthly_requested = any(token in normalized_notes for token in ("1か月に1回", "1ヶ月に1回", "月1回", "月に1回"))
    max_per_30_days = int(expectations.get("max_actions_per_30_days") or (1 if monthly_requested else 0))
    workload_ok = True
    workload_detail = "頻度指定なし"
    if max_per_30_days:
        starts = sorted(start for start, _end, _action in dated_actions)
        busiest = max((sum(1 for other in starts if start <= other < start + timedelta(days=30)) for start in starts), default=0)
        workload_ok = busiest <= max_per_30_days
        workload_detail = f"30日内最大{busiest}件 / 上限{max_per_30_days}件"
    _check(checks, "workload", "利用者の手作業頻度を守る", workload_ok, 15, workload_detail)

    forbidden_types = {str(value) for value in expectations.get("forbidden_action_types", [])}
    automated_watering = "自動潅水" in notes or "自動灌水" in notes
    if automated_watering:
        forbidden_types.add("watering")
    forbidden_actions = [str(action.get("title") or "名称なし") for action in actions if str(action.get("action_type") or "") in forbidden_types]
    _check(
        checks,
        "automation_boundary",
        "自動化済み作業を手作業化しない",
        not forbidden_actions,
        10,
        ", ".join(forbidden_actions) or "違反なし",
    )

    planted_on = _parse_date(planting.get("planted_on"))
    established = planted_on is not None and (plan_start - planted_on).days > 30
    forbidden_title_terms = [str(value) for value in expectations.get("forbidden_title_terms", [])]
    if established:
        forbidden_title_terms.extend(("定植後の活着", "定植直後"))
    history_duplicates = [
        str(action.get("title") or "名称なし") for action in actions if any(term and term in str(action.get("title") or "") for term in forbidden_title_terms)
    ]
    _check(checks, "history_aware", "実施済み履歴を重複提案しない", not history_duplicates, 10, ", ".join(history_duplicates) or "違反なし")

    complete_work_plans = sum(1 for action in actions if _work_plan_is_actionable(action))
    work_plan_ratio = complete_work_plans / len(actions) if actions else 0
    _check(
        checks,
        "actionable_work_plans",
        "開始・見送り・手順・完了判断が具体的",
        work_plan_ratio >= 0.8,
        15,
        f"{complete_work_plans}/{len(actions)}件",
    )
    described = sum(1 for action in actions if len(str(action.get("reason") or "").strip()) >= 12 and len(str(action.get("instructions") or "").strip()) >= 12)
    description_ratio = described / len(actions) if actions else 0
    _check(checks, "decision_support", "理由と判断方法を説明する", description_ratio >= 0.8, 10, f"{described}/{len(actions)}件")

    min_horizon_days = int(expectations.get("min_horizon_days") or 270)
    last_start = max((start for start, _end, _action in dated_actions), default=plan_start)
    horizon_days = (last_start - plan_start).days
    recurring_rules = [
        rule
        for rule in task_rules
        if isinstance(rule, dict) and rule.get("recurrence_type") in {"interval_after_completion", "seasonal", "continuous_review"}
    ]
    horizon_covered = horizon_days >= min_horizon_days or bool(recurring_rules)
    horizon_detail = (
        f"直近{horizon_days}日＋継続規則{len(recurring_rules)}件（完了時に次回生成）"
        if recurring_rules and horizon_days < min_horizon_days
        else f"{horizon_days}日 / 目標{min_horizon_days}日"
    )
    _check(checks, "horizon_coverage", "季節変化まで計画する", horizon_covered, 5, horizon_detail)
    action_types = {str(action.get("action_type") or "") for action in actions}
    min_action_types = int(expectations.get("min_action_types") or 3)
    _check(checks, "action_diversity", "観察以外の重要作業も扱う", len(action_types) >= min_action_types, 5, f"{len(action_types)}種類")

    score = sum(item["earned"] for item in checks)
    return {
        "score": score,
        "max_score": 100,
        "passed": score >= int(expectations.get("minimum_score") or 80)
        and all(item["passed"] for item in checks if item["id"] in {"future_only", "valid_windows", "automation_boundary", "history_aware"}),
        "checks": checks,
    }


def _work_plan_is_actionable(action: dict):
    plan = action.get("work_plan") if isinstance(action, dict) and isinstance(action.get("work_plan"), dict) else {}
    required_lists = ("targets", "start_conditions", "skip_conditions", "checkpoints", "completion_criteria")
    if not all(isinstance(plan.get(key), list) and plan[key] for key in required_lists):
        return False
    methods = plan.get("method_options") if isinstance(plan.get("method_options"), list) else []
    return any(
        isinstance(method, dict)
        and isinstance(method.get("procedure_steps"), list)
        and method["procedure_steps"]
        and isinstance(method.get("completion_checks"), list)
        and method["completion_checks"]
        for method in methods
    )


def _check(checks: list, check_id: str, label: str, passed: bool, weight: int, details: str):
    checks.append(
        {
            "id": check_id,
            "label": label,
            "passed": bool(passed),
            "earned": weight if passed else 0,
            "weight": weight,
            "details": details,
        }
    )


def _parse_date(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
