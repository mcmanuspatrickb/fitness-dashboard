from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from report_context import load_report_context


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = REPORTS_DIR / "adaptive_calorie_recommendation.txt"
PERSONAL_BLOCKS_PATH = REPORTS_DIR / "personal_response_blocks.csv"

ENERGY_KCAL_PER_KG = 7700.0
MIN_PERSONAL_BLOCKS = 8
MIN_PERSONAL_WORKOUTS = 2
DEFAULT_TARGET_DEFICIT = 500.0
MIN_TARGET_DEFICIT = 250.0
MAX_TARGET_DEFICIT = 650.0
MAX_WEEKLY_ADJUSTMENT = 150


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}"


def _strength_summary(strength_4w: list[dict[str, Any]]) -> tuple[int, int, int]:
    up = sum(1 for item in strength_4w if item.get("direction") == "up")
    flat = sum(1 for item in strength_4w if item.get("direction") == "flat")
    down = sum(1 for item in strength_4w if item.get("direction") == "down")
    return up, flat, down


def _rolling_energy_balance(
    frame: pd.DataFrame, recent_weight: float | None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "estimated_tdee": None,
        "estimated_deficit": None,
        "weight_slope_kg_day": None,
        "weight_loss_pct_week": None,
        "avg_calories": None,
        "calorie_days": 0,
        "weight_days": 0,
        "coverage_confidence": "LOW",
    }
    if frame is None or frame.empty:
        return result

    data = frame.copy()
    data["date"] = pd.to_datetime(data.get("date"), errors="coerce")
    data["weight_kg"] = pd.to_numeric(data.get("weight_kg"), errors="coerce")
    data["calories"] = pd.to_numeric(data.get("calories"), errors="coerce")

    calorie_values = data["calories"].dropna()
    weights = data[["date", "weight_kg"]].dropna().sort_values("date")
    result["calorie_days"] = int(calorie_values.count())
    result["weight_days"] = int(len(weights))
    result["avg_calories"] = (
        float(calorie_values.mean()) if not calorie_values.empty else None
    )

    if result["calorie_days"] >= 25 and result["weight_days"] >= 20:
        result["coverage_confidence"] = "HIGH"
    elif result["calorie_days"] >= 21 and result["weight_days"] >= 12:
        result["coverage_confidence"] = "MEDIUM"

    if result["calorie_days"] < 21 or result["weight_days"] < 12:
        return result

    x = (weights["date"] - weights["date"].min()).dt.total_seconds() / 86400.0
    y = weights["weight_kg"].astype(float)
    x_centered = x - x.mean()
    denominator = float((x_centered**2).sum())
    if denominator <= 0:
        return result

    slope = float((x_centered * (y - y.mean())).sum() / denominator)
    avg_calories = float(result["avg_calories"])
    estimated_tdee = avg_calories - slope * ENERGY_KCAL_PER_KG
    estimated_deficit = estimated_tdee - avg_calories

    result["weight_slope_kg_day"] = slope
    if recent_weight is not None and not pd.isna(recent_weight) and float(recent_weight) > 0:
        result["weight_loss_pct_week"] = -slope * 7.0 / float(recent_weight) * 100.0

    # Water shifts or logging errors can generate absurd maintenance estimates.
    if not 1200 <= estimated_tdee <= 5000:
        return result

    result["estimated_tdee"] = estimated_tdee
    result["estimated_deficit"] = estimated_deficit
    return result


def _spearman(frame: pd.DataFrame, x: str, y: str) -> tuple[float | None, int]:
    if frame.empty or x not in frame.columns or y not in frame.columns:
        return None, 0
    pair = frame[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
    n = len(pair)
    if n < MIN_PERSONAL_BLOCKS or pair[x].nunique() < 3 or pair[y].nunique() < 3:
        return None, n
    value = pair[x].rank(method="average").corr(pair[y].rank(method="average"))
    return (None if pd.isna(value) else float(value)), n


def _load_personal_response() -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "UNAVAILABLE",
        "active_blocks": 0,
        "compatible_blocks": 0,
        "needed": MIN_PERSONAL_BLOCKS,
        "median_active_calories": None,
        "median_active_protein": None,
        "median_active_sleep": None,
        "median_active_steps": None,
        "median_active_workouts": None,
        "associations": {},
    }
    if not PERSONAL_BLOCKS_PATH.exists():
        return result

    try:
        blocks = pd.read_csv(PERSONAL_BLOCKS_PATH)
    except Exception:
        return result
    if blocks.empty:
        return result

    for column in [
        "workouts",
        "fasting_days",
        "fat_change_kg",
        "lean_change_kg",
        "fat_loss_kg",
        "lean_retention_kg",
        "avg_calories",
        "avg_protein_g",
        "avg_steps",
        "avg_sleep_h",
        "avg_rhr",
        "avg_hrv",
    ]:
        if column in blocks.columns:
            blocks[column] = pd.to_numeric(blocks[column], errors="coerce")

    if "workouts" not in blocks.columns:
        return result

    workout_mask = blocks["workouts"].fillna(0) >= MIN_PERSONAL_WORKOUTS
    if "fasting_days" in blocks.columns:
        normal_diet_mask = blocks["fasting_days"].fillna(0) == 0
    else:
        normal_diet_mask = pd.Series(True, index=blocks.index)

    active = blocks[workout_mask & normal_diet_mask].copy()
    active = active.dropna(subset=["fat_change_kg", "lean_change_kg"])
    compatible = active[
        (active["fat_change_kg"] < 0) & (active["lean_change_kg"] >= -0.30)
    ].copy()

    result["active_blocks"] = int(len(active))
    result["compatible_blocks"] = int(len(compatible))
    result["needed"] = max(0, MIN_PERSONAL_BLOCKS - len(active))
    result["status"] = "READY" if len(active) >= MIN_PERSONAL_BLOCKS else "BUILDING"

    def median(column: str) -> float | None:
        if active.empty or column not in active.columns:
            return None
        values = pd.to_numeric(active[column], errors="coerce").dropna()
        return None if values.empty else float(values.median())

    result["median_active_calories"] = median("avg_calories")
    result["median_active_protein"] = median("avg_protein_g")
    result["median_active_sleep"] = median("avg_sleep_h")
    result["median_active_steps"] = median("avg_steps")
    result["median_active_workouts"] = median("workouts")

    associations: dict[str, dict[str, Any]] = {}
    predictors = {
        "calories": "avg_calories",
        "protein": "avg_protein_g",
        "steps": "avg_steps",
        "sleep": "avg_sleep_h",
        "workouts": "workouts",
    }
    for label, column in predictors.items():
        fat_r, fat_n = _spearman(active, column, "fat_loss_kg")
        lean_r, lean_n = _spearman(active, column, "lean_retention_kg")
        associations[label] = {
            "fat_r": fat_r,
            "fat_n": fat_n,
            "lean_r": lean_r,
            "lean_n": lean_n,
        }
    result["associations"] = associations
    return result


def _round_to_25(value: float) -> int:
    return int(round(value / 25.0) * 25)


def _bounded_step(gap: float) -> int:
    if abs(gap) < 75:
        return 0
    rounded = int(round(abs(gap) / 50.0) * 50)
    return min(MAX_WEEKLY_ADJUSTMENT, max(50, rounded)) * (1 if gap > 0 else -1)


def main() -> None:
    context = load_report_context()
    weekly = context.get("weekly", {})
    trend = context.get("trend_4w", {})
    trailing_28 = context.get("trailing_28", pd.DataFrame())
    strength_4w = context.get("strength_4w", [])
    end_date = context.get("analysis_end_date")

    if end_date is None:
        raise RuntimeError("No complete recent reporting window found.")

    recent_weight = weekly.get("recent_weight")
    current_calories = weekly.get("recent_calories")
    recent_protein = weekly.get("recent_protein")
    recent_sleep = weekly.get("recent_sleep")
    recent_steps = weekly.get("recent_steps")
    rhr_delta = weekly.get("rhr_delta")
    hrv_delta = weekly.get("hrv_delta")
    fat_delta_7d = weekly.get("fat_delta")
    lean_delta_7d = weekly.get("lean_delta")

    weight_delta_4w = trend.get("weight_delta")
    fat_delta_4w = trend.get("fat_delta")
    lean_delta_4w = trend.get("lean_delta")
    avg_calories_28 = trend.get("avg_calories")
    avg_sleep_28 = trend.get("avg_sleep")

    strength_up, strength_flat, strength_down = _strength_summary(strength_4w)
    energy = _rolling_energy_balance(trailing_28, recent_weight)
    personal = _load_personal_response()

    pace = energy.get("weight_loss_pct_week")
    estimated_tdee = energy.get("estimated_tdee")
    estimated_deficit = energy.get("estimated_deficit")

    # Start from a moderate deficit and adjust the target deficit based on the
    # multi-week outcome signal. This avoids treating one noisy BIA reading or
    # one unusually low-calorie week as enough reason for a large change.
    target_deficit = DEFAULT_TARGET_DEFICIT
    decision_notes: list[str] = []

    lean_watch = (
        lean_delta_4w is not None
        and not pd.isna(lean_delta_4w)
        and float(lean_delta_4w) <= -0.75
    )
    fast_loss = pace is not None and float(pace) > 0.75
    stalled_loss = pace is not None and float(pace) < 0.15
    fat_not_moving = (
        fat_delta_4w is not None
        and not pd.isna(fat_delta_4w)
        and float(fat_delta_4w) >= -0.20
    )
    strength_concern = strength_down >= 2
    strength_stable = strength_down == 0 and (strength_up + strength_flat) >= 2

    if fast_loss or strength_concern:
        target_deficit = 300.0
        if fast_loss:
            decision_notes.append("The 28-day loss rate is fast enough that a smaller deficit is safer for muscle preservation.")
        if strength_concern:
            decision_notes.append("Multiple four-week strength trends are down, so the calorie target is biased toward recovery rather than faster loss.")
    elif lean_watch:
        target_deficit = 350.0
        decision_notes.append("The four-week BIA lean-mass trend is a watch signal, so the target deficit is intentionally conservative.")
    elif stalled_loss and fat_not_moving and strength_stable:
        target_deficit = 600.0
        decision_notes.append("The 28-day trend is close to stalled while strength is stable, so a modestly larger deficit is reasonable.")
    else:
        decision_notes.append("The multi-week trend supports a moderate deficit rather than an aggressive calorie change.")

    # Personal-response evidence is a soft modifier only after enough comparable
    # normal-diet, resistance-training blocks exist. Until then, it is displayed
    # but deliberately does not alter the calorie target.
    personal_bias = 0.0
    associations = personal.get("associations", {})
    if personal.get("status") == "READY":
        calorie_assoc = associations.get("calories", {})
        protein_assoc = associations.get("protein", {})
        sleep_assoc = associations.get("sleep", {})
        steps_assoc = associations.get("steps", {})

        calorie_lean_r = calorie_assoc.get("lean_r")
        calorie_fat_r = calorie_assoc.get("fat_r")
        protein_lean_r = protein_assoc.get("lean_r")
        sleep_lean_r = sleep_assoc.get("lean_r")
        steps_fat_r = steps_assoc.get("fat_r")

        if lean_watch or strength_concern:
            if calorie_lean_r is not None and calorie_lean_r >= 0.35:
                personal_bias += 100.0
                decision_notes.append("Your comparable history shows a moderate positive association between higher calories and better BIA lean retention, so the target is nudged upward.")
            elif protein_lean_r is not None and protein_lean_r >= 0.35:
                decision_notes.append("Your comparable history points more strongly toward protein than calories for lean retention, so the calorie target is not raised solely because BIA lean mass is down.")
            elif sleep_lean_r is not None and sleep_lean_r >= 0.35:
                decision_notes.append("Your comparable history points more strongly toward sleep than calories for lean retention, so recovery remains the first lever.")

        if stalled_loss and fat_not_moving and strength_stable:
            if calorie_fat_r is not None and calorie_fat_r <= -0.35:
                personal_bias -= 75.0
                decision_notes.append("Your comparable history shows a moderate inverse association between calories and fat loss, supporting a small additional downward calorie bias during a true stall.")
            elif steps_fat_r is not None and steps_fat_r >= 0.35:
                decision_notes.append("Your comparable history links higher steps with better fat-loss outcomes, so the model avoids making calories do all of the work.")
    else:
        decision_notes.append(
            f"Personal-response evidence is still building ({personal.get('active_blocks', 0)}/{MIN_PERSONAL_BLOCKS} comparable blocks), so it is not allowed to change the calorie target yet."
        )

    target_deficit = min(
        MAX_TARGET_DEFICIT,
        max(MIN_TARGET_DEFICIT, target_deficit - personal_bias),
    )

    target_calories = None
    calorie_gap = None
    recommendation = "HOLD"
    calorie_change = 0

    if estimated_tdee is not None:
        target_calories = _round_to_25(float(estimated_tdee) - target_deficit)
        if current_calories is not None and not pd.isna(current_calories):
            calorie_gap = float(target_calories) - float(current_calories)
            proposed_step = _bounded_step(calorie_gap)

            if proposed_step > 0:
                # Raise calories when the current week sits materially below the
                # rolling target and there is either a preservation signal or a
                # clear recent undershoot versus the 28-day intake baseline.
                current_vs_28 = None
                if avg_calories_28 is not None and not pd.isna(avg_calories_28) and float(avg_calories_28) > 0:
                    current_vs_28 = (
                        float(current_calories) / float(avg_calories_28) - 1.0
                    ) * 100.0
                if lean_watch or fast_loss or strength_concern or (
                    current_vs_28 is not None and current_vs_28 <= -10.0
                ):
                    recommendation = "INCREASE"
                    calorie_change = proposed_step
                else:
                    recommendation = "HOLD"
                    calorie_change = 0
            elif proposed_step < 0:
                # Do not cut just because the arithmetic target is lower. Require
                # an actual multi-week stall and stable performance/recovery.
                if stalled_loss and fat_not_moving and strength_stable:
                    recommendation = "DECREASE"
                    calorie_change = proposed_step
                else:
                    recommendation = "HOLD"
                    calorie_change = 0
    else:
        decision_notes.append("Rolling TDEE could not be estimated with sufficient coverage, so no calorie adjustment is made from energy-balance math this week.")

    if recommendation == "INCREASE":
        macro_hint = (
            f"Add about {calorie_change} kcal/day for the next week, preferably while keeping protein in the lean-mass-preservation range and using much of the added energy around training."
        )
    elif recommendation == "DECREASE":
        macro_hint = (
            f"Reduce by about {abs(calorie_change)} kcal/day for the next week, preferably from discretionary carbs/fats rather than protein."
        )
    else:
        macro_hint = (
            "Hold calories steady for the next week. Use the lean-mass-preservation section for protein and reassess from the next multi-week trend rather than reacting to a single day."
        )

    lines: list[str] = [
        "Adaptive Calorie Recommendation",
        "==============================",
        "",
        f"Reporting window ends: {end_date}",
        "",
        "Energy-Balance Model",
        "--------------------",
        f"rolling 28-day estimated maintenance: {_fmt(estimated_tdee, 0)} kcal/day",
        f"rolling 28-day estimated deficit: {_fmt(estimated_deficit, 0)} kcal/day",
        f"rolling 28-day loss pace: {_fmt(pace, 2)}% body weight/week",
        f"energy-balance coverage: {energy.get('coverage_confidence', 'LOW')} ({energy.get('calorie_days', 0)} nutrition days; {energy.get('weight_days', 0)} weight days)",
        f"model target deficit: {_fmt(target_deficit, 0)} kcal/day",
        f"model target intake: {_fmt(target_calories, 0)} kcal/day",
        "",
        "Current Trend",
        "-------------",
        f"7-day calories: {_fmt(current_calories, 0)} kcal/day",
        f"28-day calories: {_fmt(avg_calories_28, 0)} kcal/day",
        f"7-day protein: {_fmt(recent_protein, 0)} g/day",
        f"7-day steps: {_fmt(recent_steps, 0)} /day",
        f"7-day sleep: {_fmt(recent_sleep, 2)} h/night",
        f"7-day fat-mass change vs prior 7d: {_fmt(fat_delta_7d)} kg",
        f"7-day lean-mass change vs prior 7d: {_fmt(lean_delta_7d)} kg",
        f"4-week weight change: {_fmt(weight_delta_4w)} kg",
        f"4-week fat-mass change: {_fmt(fat_delta_4w)} kg",
        f"4-week BIA lean-mass change: {_fmt(lean_delta_4w)} kg",
        f"RHR change vs prior 7d: {_fmt(rhr_delta)} bpm",
        f"HRV change vs prior 7d: {_fmt(hrv_delta)} ms",
        "",
        "Strength Context",
        "----------------",
        f"4-week lifts up: {strength_up}",
        f"4-week lifts flat: {strength_flat}",
        f"4-week lifts down: {strength_down}",
        "",
        "Personal-Response Evidence",
        "--------------------------",
        f"status: {personal.get('status', 'UNAVAILABLE')}",
        f"training-active normal-diet blocks: {personal.get('active_blocks', 0)}",
        f"minimum before personalized adjustment: {MIN_PERSONAL_BLOCKS}",
        f"additional comparable blocks needed: {personal.get('needed', MIN_PERSONAL_BLOCKS)}",
    ]

    if personal.get("status") == "READY":
        lines.extend(
            [
                f"historical active-block median calories: {_fmt(personal.get('median_active_calories'), 0)} kcal/day",
                f"historical active-block median protein: {_fmt(personal.get('median_active_protein'), 0)} g/day",
                f"historical active-block median sleep: {_fmt(personal.get('median_active_sleep'), 1)} h/night",
                f"historical active-block median steps: {_fmt(personal.get('median_active_steps'), 0)} /day",
                "Personal associations are used only as small directional modifiers, not as proof of causation.",
            ]
        )
    else:
        lines.append("Personal associations are withheld from the calorie decision until the evidence threshold is reached.")

    lines.extend(
        [
            "",
            "Recommendation",
            "--------------",
            f"Action: {recommendation}",
            f"Calorie adjustment: {calorie_change:+d} kcal/day",
            f"Current-to-model gap: {_fmt(calorie_gap, 0)} kcal/day",
            macro_hint,
            "",
            "Why",
            "---",
        ]
    )
    for item in decision_notes:
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "Method Note",
            "-----------",
            "Maintenance/TDEE is inferred from the 28-day scale-weight trend plus logged calorie intake using 7,700 kcal per kg as an energy-balance approximation. Water/glycogen shifts and food-logging error can materially move the estimate, so it is a planning signal rather than a metabolic measurement.",
            "Weekly calorie changes are capped at 150 kcal/day. Downward changes require a multi-week stall plus stable strength; upward changes require a meaningful under-fueling or preservation signal rather than a single noisy BIA reading.",
            "Personal-response correlations are used only after at least eight comparable resistance-training, normal-diet 14-day blocks exist. Even then, they are treated as hypothesis-level directional evidence rather than causal effects.",
        ]
    )

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {OUT_PATH}")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()
