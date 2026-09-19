from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from report_context import load_report_context


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = REPORTS_DIR / "adaptive_calorie_recommendation.txt"
PERSONAL_BLOCKS_PATH = REPORTS_DIR / "personal_response_blocks.csv"
PHASE_JSON = REPORTS_DIR / "current_phase.json"
GUARDRAIL_JSON = REPORTS_DIR / "cut_stress_guardrail.json"

ENERGY_KCAL_PER_KG = 7700.0
MIN_PERSONAL_BLOCKS = 8
MIN_PERSONAL_WORKOUTS = 2
MAX_WEEKLY_ADJUSTMENT = 150


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}"


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default
    except Exception:
        return default


def _strength_summary(items: list[dict[str, Any]]) -> tuple[int, int, int]:
    return (
        sum(1 for item in items if item.get("direction") == "up"),
        sum(1 for item in items if item.get("direction") == "flat"),
        sum(1 for item in items if item.get("direction") == "down"),
    )


def _rolling_energy_balance(frame: pd.DataFrame, recent_weight: float | None) -> dict[str, Any]:
    result = {
        "estimated_tdee": None, "estimated_deficit": None,
        "weight_loss_pct_week": None, "avg_calories": None,
        "calorie_days": 0, "weight_days": 0, "coverage_confidence": "LOW",
    }
    if frame is None or frame.empty:
        return result

    data = frame.copy()
    data["date"] = pd.to_datetime(data.get("date"), errors="coerce")
    data["weight_kg"] = pd.to_numeric(data.get("weight_kg"), errors="coerce")
    data["calories"] = pd.to_numeric(data.get("calories"), errors="coerce")
    calories = data["calories"].dropna()
    weights = data[["date", "weight_kg"]].dropna().sort_values("date")
    result["calorie_days"] = int(len(calories))
    result["weight_days"] = int(len(weights))
    result["avg_calories"] = float(calories.mean()) if not calories.empty else None

    if len(calories) >= 25 and len(weights) >= 20:
        result["coverage_confidence"] = "HIGH"
    elif len(calories) >= 21 and len(weights) >= 12:
        result["coverage_confidence"] = "MEDIUM"
    if len(calories) < 21 or len(weights) < 12:
        return result

    x = (weights["date"] - weights["date"].min()).dt.total_seconds() / 86400.0
    y = weights["weight_kg"].astype(float)
    xc = x - x.mean()
    denominator = float((xc ** 2).sum())
    if denominator <= 0:
        return result
    slope = float((xc * (y - y.mean())).sum() / denominator)
    avg_calories = float(result["avg_calories"])
    tdee = avg_calories - slope * ENERGY_KCAL_PER_KG
    if not 1200 <= tdee <= 5000:
        return result

    result["estimated_tdee"] = tdee
    result["estimated_deficit"] = tdee - avg_calories
    if recent_weight is not None and float(recent_weight) > 0:
        result["weight_loss_pct_week"] = -slope * 7.0 / float(recent_weight) * 100.0
    return result


def _spearman(frame: pd.DataFrame, x: str, y: str) -> float | None:
    if frame.empty or x not in frame.columns or y not in frame.columns:
        return None
    pair = frame[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(pair) < MIN_PERSONAL_BLOCKS or pair[x].nunique() < 3 or pair[y].nunique() < 3:
        return None
    value = pair[x].rank(method="average").corr(pair[y].rank(method="average"))
    return None if pd.isna(value) else float(value)


def _load_personal_response() -> dict[str, Any]:
    result = {"status": "UNAVAILABLE", "active_blocks": 0, "needed": MIN_PERSONAL_BLOCKS, "associations": {}}
    if not PERSONAL_BLOCKS_PATH.exists():
        return result
    try:
        blocks = pd.read_csv(PERSONAL_BLOCKS_PATH)
    except Exception:
        return result
    if blocks.empty or "workouts" not in blocks.columns:
        return result

    for column in ["workouts", "fasting_days", "fat_loss_kg", "lean_retention_kg", "avg_calories", "avg_protein_g", "avg_steps", "avg_sleep_h"]:
        if column in blocks.columns:
            blocks[column] = pd.to_numeric(blocks[column], errors="coerce")
    active = blocks[blocks["workouts"].fillna(0) >= MIN_PERSONAL_WORKOUTS].copy()
    if "fasting_days" in active.columns:
        active = active[active["fasting_days"].fillna(0) == 0]
    active = active.dropna(subset=["fat_loss_kg", "lean_retention_kg"])
    result["active_blocks"] = int(len(active))
    result["needed"] = max(0, MIN_PERSONAL_BLOCKS - len(active))
    result["status"] = "READY" if len(active) >= MIN_PERSONAL_BLOCKS else "BUILDING"
    if result["status"] == "READY":
        result["associations"] = {
            "calories_lean": _spearman(active, "avg_calories", "lean_retention_kg"),
            "calories_fat": _spearman(active, "avg_calories", "fat_loss_kg"),
            "protein_lean": _spearman(active, "avg_protein_g", "lean_retention_kg"),
            "sleep_lean": _spearman(active, "avg_sleep_h", "lean_retention_kg"),
            "steps_fat": _spearman(active, "avg_steps", "fat_loss_kg"),
        }
    return result


def _round_to_25(value: float) -> int:
    return int(round(value / 25.0) * 25)


def _bounded_step(gap: float) -> int:
    if abs(gap) < 75:
        return 0
    magnitude = min(MAX_WEEKLY_ADJUSTMENT, max(50, int(round(abs(gap) / 50.0) * 50)))
    return magnitude if gap > 0 else -magnitude


def main() -> None:
    context = load_report_context()
    weekly = context.get("weekly", {})
    trend = context.get("trend_4w", {})
    trailing_28 = context.get("trailing_28", pd.DataFrame())
    strength = context.get("strength_4w", [])
    end_date = context.get("analysis_end_date")
    if end_date is None:
        raise RuntimeError("No complete recent reporting window found.")

    phase_info = _load_json(PHASE_JSON, {"current_phase": "cut", "lean_gain_surplus_kcal": 150})
    guardrail = _load_json(GUARDRAIL_JSON, {"status": "STABLE"})
    phase = str(phase_info.get("current_phase", "cut"))
    guardrail_status = str(guardrail.get("status", "STABLE"))

    current_calories = weekly.get("recent_calories")
    recent_weight = weekly.get("recent_weight")
    energy = _rolling_energy_balance(trailing_28, recent_weight)
    estimated_tdee = energy.get("estimated_tdee")
    estimated_deficit = energy.get("estimated_deficit")
    pace = energy.get("weight_loss_pct_week")
    strength_up, strength_flat, strength_down = _strength_summary(strength)
    personal = _load_personal_response()

    lean_delta_4w = trend.get("lean_delta")
    fat_delta_4w = trend.get("fat_delta")
    avg_calories_28 = trend.get("avg_calories")
    lean_watch = lean_delta_4w is not None and float(lean_delta_4w) <= -0.75
    fast_loss = pace is not None and float(pace) > 0.75
    stalled_loss = pace is not None and float(pace) < 0.15
    fat_not_moving = fat_delta_4w is not None and float(fat_delta_4w) >= -0.20
    strength_concern = strength_down >= 2
    strength_stable = strength_down == 0 and (strength_up + strength_flat) >= 2

    notes: list[str] = []
    if phase == "maintenance":
        target_deficit = 0.0
        notes.append("The configured coaching phase is maintenance, so the model targets estimated maintenance rather than a deficit.")
    elif phase == "lean_gain":
        surplus = float(phase_info.get("lean_gain_surplus_kcal", 150) or 150)
        target_deficit = -abs(surplus)
        notes.append(f"The configured coaching phase is lean gain, so the model uses a small ~{abs(surplus):.0f} kcal/day surplus.")
    else:
        target_deficit = 500.0
        if fast_loss or strength_concern:
            target_deficit = 300.0
        elif lean_watch:
            target_deficit = 350.0
        elif stalled_loss and fat_not_moving and strength_stable:
            target_deficit = 600.0

        if guardrail_status == "RECOVERY_CONCERN":
            target_deficit = min(target_deficit, 250.0)
            notes.append("The recovery guardrail is in RECOVERY_CONCERN, so the deficit is capped conservatively and cannot be deepened this week.")
        elif guardrail_status == "WATCH":
            target_deficit = min(target_deficit, 350.0)
            notes.append("The recovery guardrail is on WATCH, so the model avoids an aggressive deficit.")
        else:
            notes.append("The recovery guardrail is stable, so the normal cut logic can operate.")

        if personal.get("status") == "READY":
            assoc = personal.get("associations", {})
            if (lean_watch or strength_concern) and assoc.get("calories_lean") is not None and assoc["calories_lean"] >= 0.35:
                target_deficit = max(250.0, target_deficit - 100.0)
                notes.append("Comparable personal history links higher calories with better lean retention, so the target deficit is nudged smaller.")
            elif (lean_watch or strength_concern) and assoc.get("protein_lean") is not None and assoc["protein_lean"] >= 0.35:
                notes.append("Comparable personal history points more strongly toward protein than calories for lean retention.")
        else:
            notes.append(f"Personal-response evidence is still building ({personal.get('active_blocks', 0)}/{MIN_PERSONAL_BLOCKS} comparable blocks), so it does not change the target yet.")

    target_calories = _round_to_25(float(estimated_tdee) - target_deficit) if estimated_tdee is not None else None
    calorie_gap = None
    recommendation = "HOLD"
    calorie_change = 0

    if estimated_tdee is not None and current_calories is not None:
        calorie_gap = float(target_calories) - float(current_calories)
        proposed = _bounded_step(calorie_gap)
        if phase in {"maintenance", "lean_gain"}:
            if proposed > 0:
                recommendation, calorie_change = "INCREASE", proposed
            elif proposed < 0:
                recommendation, calorie_change = "DECREASE", proposed
        else:
            if proposed > 0:
                current_vs_28 = None
                if avg_calories_28 is not None and float(avg_calories_28) > 0:
                    current_vs_28 = (float(current_calories) / float(avg_calories_28) - 1.0) * 100.0
                if lean_watch or fast_loss or strength_concern or guardrail_status != "STABLE" or (current_vs_28 is not None and current_vs_28 <= -10.0):
                    recommendation, calorie_change = "INCREASE", proposed
            elif proposed < 0 and stalled_loss and fat_not_moving and strength_stable and guardrail_status == "STABLE":
                recommendation, calorie_change = "DECREASE", proposed
    else:
        notes.append("Rolling TDEE could not be estimated with sufficient coverage, so no calorie adjustment is made from energy-balance math this week.")

    if recommendation == "INCREASE":
        macro_hint = f"Add about {calorie_change} kcal/day for the next week while protecting the protein target and training quality."
    elif recommendation == "DECREASE":
        macro_hint = f"Reduce by about {abs(calorie_change)} kcal/day for the next week, preferably from discretionary carbs/fats rather than protein."
    else:
        macro_hint = "Hold calories steady for the next week and reassess from the next multi-week trend."

    lines = [
        "Adaptive Calorie Recommendation", "==============================", "",
        f"Reporting window ends: {end_date}", "",
        "Phase Context", "-------------",
        f"current phase: {phase}",
        f"phase suggestion: {phase_info.get('suggestion', 'n/a')}",
        f"recovery guardrail: {guardrail_status}", "",
        "Energy-Balance Model", "--------------------",
        f"rolling 28-day estimated maintenance: {_fmt(estimated_tdee, 0)} kcal/day",
        f"rolling 28-day estimated deficit: {_fmt(estimated_deficit, 0)} kcal/day",
        f"rolling 28-day loss pace: {_fmt(pace, 2)}% body weight/week",
        f"energy-balance coverage: {energy.get('coverage_confidence', 'LOW')} ({energy.get('calorie_days', 0)} nutrition days; {energy.get('weight_days', 0)} weight days)",
        f"model target deficit: {_fmt(target_deficit, 0)} kcal/day",
        f"model target intake: {_fmt(target_calories, 0)} kcal/day", "",
        "Current Trend", "-------------",
        f"7-day calories: {_fmt(current_calories, 0)} kcal/day",
        f"28-day calories: {_fmt(avg_calories_28, 0)} kcal/day",
        f"7-day protein: {_fmt(weekly.get('recent_protein'), 0)} g/day",
        f"7-day steps: {_fmt(weekly.get('recent_steps'), 0)} /day",
        f"7-day sleep: {_fmt(weekly.get('recent_sleep'), 2)} h/night",
        f"4-week fat-mass change: {_fmt(fat_delta_4w)} kg",
        f"4-week BIA lean-mass change: {_fmt(lean_delta_4w)} kg", "",
        "Strength Context", "----------------",
        f"4-week lifts up: {strength_up}", f"4-week lifts flat: {strength_flat}", f"4-week lifts down: {strength_down}", "",
        "Personal-Response Evidence", "--------------------------",
        f"status: {personal.get('status', 'UNAVAILABLE')}",
        f"training-active normal-diet blocks: {personal.get('active_blocks', 0)}",
        f"minimum before personalized adjustment: {MIN_PERSONAL_BLOCKS}",
        f"additional comparable blocks needed: {personal.get('needed', MIN_PERSONAL_BLOCKS)}", "",
        "Recommendation", "--------------",
        f"Action: {recommendation}",
        f"Calorie adjustment: {calorie_change:+d} kcal/day",
        f"Current-to-model gap: {_fmt(calorie_gap, 0)} kcal/day",
        macro_hint, "", "Why", "---",
    ]
    lines.extend(f"- {item}" for item in notes)
    lines.extend([
        "", "Method Note", "-----------",
        "Maintenance/TDEE is inferred from the 28-day scale-weight trend plus logged calorie intake using 7,700 kcal per kg as an energy-balance approximation. Water/glycogen shifts and food-logging error can materially move the estimate.",
        "Weekly calorie changes are capped at 150 kcal/day. During a cut, downward changes require a multi-week stall, stable performance, and a stable recovery guardrail.",
        "Phase changes are explicit: the detector can suggest a transition, but it does not silently switch the coaching phase.",
    ])
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {OUT_PATH}")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()
