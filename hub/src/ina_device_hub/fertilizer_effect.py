from datetime import date, timedelta

NUTRIENT_KEYS = ("n", "p2o5", "k2o", "mgo")
NUTRIENT_LABELS = {"n": "N", "p2o5": "P₂O₅", "k2o": "K₂O", "mgo": "MgO（苦土）"}


def fertilizer_effect_summary(applications: list[dict], *, as_of: str | date | None = None, horizon_days: int = 365):
    reference_date = _as_date(as_of) if as_of else date.today()
    horizon_days = max(1, min(int(horizon_days), 3650))
    nutrients = {key: {"applied_kg": 0.0, "effective_total_kg": 0.0, "released_to_date_kg": 0.0, "remaining_kg": 0.0} for key in NUTRIENT_KEYS}
    forecast = []
    active_applications = []
    normalized_applications = [application for application in applications if isinstance(application, dict)]

    for application in normalized_applications:
        applied_on = _as_date(application.get("applied_on"))
        effect_start = applied_on + timedelta(days=int(application.get("start_delay_days") or 0))
        effect_years = max(1, int(application.get("effect_years") or 1))
        effect_end = effect_start + timedelta(days=365 * effect_years)
        duration_days = max(1, (effect_end - effect_start).days)
        annual_fraction = max(0.0, min(1.0, float(application.get("annual_available_percent") or 0) / 100))
        effective_fraction = min(1.0, annual_fraction * effect_years)
        progress = max(0.0, min(1.0, (reference_date - effect_start).days / duration_days))
        nutrient_percent = application.get("nutrient_percent") if isinstance(application.get("nutrient_percent"), dict) else {}
        application_nutrients = {}

        for key in NUTRIENT_KEYS:
            applied_nutrient = float(application.get("amount_kg") or 0) * float(nutrient_percent.get(key) or 0) / 100
            effective_total = applied_nutrient * effective_fraction
            released = effective_total * progress
            remaining = effective_total - released
            nutrients[key]["applied_kg"] += applied_nutrient
            nutrients[key]["effective_total_kg"] += effective_total
            nutrients[key]["released_to_date_kg"] += released
            nutrients[key]["remaining_kg"] += remaining
            application_nutrients[key] = {
                "applied_kg": _rounded(applied_nutrient),
                "effective_total_kg": _rounded(effective_total),
                "released_to_date_kg": _rounded(released),
                "remaining_kg": _rounded(remaining),
            }

        active_applications.append(
            {
                "id": str(application.get("id") or ""),
                "material_name": str(application.get("material_name") or ""),
                "amount_kg": float(application.get("amount_kg") or 0),
                "applied_on": applied_on.isoformat(),
                "effect_start": effect_start.isoformat(),
                "effect_end": effect_end.isoformat(),
                "state": "waiting" if reference_date < effect_start else "active" if reference_date < effect_end else "finished",
                "progress_percent": _rounded(progress * 100, 1),
                "nutrients": application_nutrients,
            }
        )

    for offset in range(0, horizon_days, 30):
        period_start = reference_date + timedelta(days=offset)
        period_end = min(reference_date + timedelta(days=horizon_days), period_start + timedelta(days=30))
        period_nutrients = {key: 0.0 for key in NUTRIENT_KEYS}
        for application in normalized_applications:
            applied_on = _as_date(application.get("applied_on"))
            effect_start = applied_on + timedelta(days=int(application.get("start_delay_days") or 0))
            effect_years = max(1, int(application.get("effect_years") or 1))
            effect_end = effect_start + timedelta(days=365 * effect_years)
            overlap_start = max(period_start, effect_start)
            overlap_end = min(period_end, effect_end)
            overlap_days = max(0, (overlap_end - overlap_start).days)
            if overlap_days == 0:
                continue
            annual_fraction = max(0.0, min(1.0, float(application.get("annual_available_percent") or 0) / 100))
            effective_fraction = min(1.0, annual_fraction * effect_years)
            nutrient_percent = application.get("nutrient_percent") if isinstance(application.get("nutrient_percent"), dict) else {}
            duration_days = max(1, (effect_end - effect_start).days)
            for key in NUTRIENT_KEYS:
                applied_nutrient = float(application.get("amount_kg") or 0) * float(nutrient_percent.get(key) or 0) / 100
                period_nutrients[key] += applied_nutrient * effective_fraction * overlap_days / duration_days
        forecast.append(
            {
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "nutrients_kg": {key: _rounded(value) for key, value in period_nutrients.items()},
            }
        )

    return {
        "as_of": reference_date.isoformat(),
        "model": "linear_estimate_from_user_inputs",
        "application_count": len(normalized_applications),
        "active_count": sum(1 for application in active_applications if application["state"] in {"waiting", "active"}),
        "nutrients": {key: {metric: _rounded(value) for metric, value in values.items()} for key, values in nutrients.items()},
        "applications": active_applications,
        "forecast": forecast,
        "caution": "製品分析値と入力した肥効率からの概算です。土壌分析、EC、作物の状態、地域の施肥基準を優先してください。",
    }


def _as_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value or ""))


def _rounded(value: float, digits: int = 4):
    return round(float(value), digits)
