from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from report_context import load_report_context


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = REPORTS_DIR / "lean_mass_preservation.txt"

# Practical working range for a resistance-trained cut. This is deliberately
# framed as a coaching heuristic rather than a medical prescription.
PROTEIN_LOW_PER_KG_LEAN = 1.8
PROTEIN_HIGH_PER_KG_LEAN = 2.2
ENERGY_KCAL_PER_KG = 7700.0


def _num(value: Any, decimals: int = 1, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{decimals}f}{suffix}"


def _percent(value: Any, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{decimals}f}%"


def _strength_summary(strength_4w: list[dict[str, Any]]) -> tuple[int, int, int]:
    up = sum(1 for item in strength_4w if item.get("direction") == "up")
    flat = sum(1 for item in strength_4w if item.get("direction") == "flat")
    down = sum(1 for item in strength_4w if item.get("direction") == "down")
    return up, flat, down


def _rolling_energy_balance(frame: pd.DataFrame, recent_weight: float | None) -> dict[str, Any]:
    """Estimate recent maintenance from intake plus the 28-day weight trend.

    This deliberately uses the scale-weight trend rather than BIA fat/lean
    compartments. Short-term BIA changes are too hydration-sensitive to use as
    an energy accounting system. The estimate is therefore a planning signal,
    not a metabolic measurement.
    """
    result = {
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

    first_date = weights["date"].min()
    x = (weights["date"] - first_date).dt.total_seconds() / 86400.0
    y = weights["weight_kg"].astype(float)
    x_centered = x - x.mean()
    denominator = float((x_centered ** 2).sum())
    if denominator <= 0:
        return result

    slope = float((x_centered * (y - y.mean())).sum() / denominator)
    avg_calories = float(result["avg_calories"])
    estimated_tdee = avg_calories - slope * ENERGY_KCAL_PER_KG
    estimated_deficit = estimated_tdee - avg_calories

    # Reject obviously implausible outputs caused by water shifts or bad data.
    if not 1200 <= estimated_tdee <= 5000:
        result["weight_slope_kg_day"] = slope
        return result

    result["weight_slope_kg_day"] = slope
    result["estimated_tdee"] = estimated_tdee
    result["estimated_deficit"] = estimated_deficit
    if recent_weight is not None and not pd.isna(recent_weight) and float(recent_weight) > 0:
        result["weight_loss_pct_week"] = (
            -slope * 7.0 / float(recent_weight) * 100.0
        )
    return result


def _canonical_energy_from_report(fallback: dict[str, Any]) -> dict[str, Any]:
    """Overlay the canonical 28/42-day energy model onto this supporting report.

    The adaptive calorie model runs earlier in the weekly stack and is the
    authoritative energy model. This keeps the lean-mass report from publishing
    a second, competing maintenance estimate while retaining its local 28-day
    calculation only as a fallback if the upstream report is unavailable.
    """
    report_path = REPORTS_DIR / "adaptive_calorie_recommendation.txt"
    if not report_path.exists():
        result = dict(fallback)
        result["energy_source"] = "28-day fallback"
        return result

    lines = report_path.read_text(encoding="utf-8").splitlines()

    def number(label: str) -> float | None:
        prefix = label + ":"
        for line in lines:
            if line.startswith(prefix):
                token = line.split(":", 1)[1].strip().split()[0].replace(",", "")
                try:
                    return float(token)
                except ValueError:
                    return None
        return None

    result = dict(fallback)
    result["estimated_tdee"] = number("consensus planning maintenance") or fallback.get("estimated_tdee")
    result["estimated_deficit"] = number("consensus estimated deficit") or fallback.get("estimated_deficit")
    result["weight_loss_pct_week"] = number("rolling 28-day loss pace") or fallback.get("weight_loss_pct_week")
    result["tdee_28"] = number("rolling 28-day estimated maintenance")
    result["tdee_42"] = number("rolling 42-day estimated maintenance")
    result["energy_source"] = "canonical 28/42-day consensus"
    for line in lines:
        if line.startswith("28/42-day TDEE agreement:"):
            result["tdee_agreement"] = line.split(":", 1)[1].strip()
        elif line.startswith("energy-balance coverage (28d):"):
            result["coverage_summary"] = line.split(":", 1)[1].strip()
    return result


def main() -> None:
    context = load_report_context()
    weekly = context.get("weekly", {})
    trend = context.get("trend_4w", {})
    strength_4w = context.get("strength_4w", [])
    trailing_28 = context.get("trailing_28", pd.DataFrame())
    end_date = context.get("analysis_end_date")

    recent_weight = weekly.get("recent_weight")
    recent_lean = weekly.get("recent_lean")
    recent_protein = weekly.get("recent_protein")
    recent_calories = weekly.get("recent_calories")
    recent_sleep = weekly.get("recent_sleep")

    fat_delta_4w = trend.get("fat_delta")
    lean_delta_4w = trend.get("lean_delta")
    weight_delta_4w = trend.get("weight_delta")
    avg_calories_28 = trend.get("avg_calories")
    avg_protein_28 = trend.get("avg_protein")
    avg_sleep_28 = trend.get("avg_sleep")
    workouts_28 = trend.get("workouts")

    energy = _canonical_energy_from_report(_rolling_energy_balance(trailing_28, recent_weight))

    protein_per_kg_lean = None
    protein_low = None
    protein_high = None
    if recent_lean is not None and not pd.isna(recent_lean) and float(recent_lean) > 0:
        protein_low = float(recent_lean) * PROTEIN_LOW_PER_KG_LEAN
        protein_high = float(recent_lean) * PROTEIN_HIGH_PER_KG_LEAN
        if recent_protein is not None and not pd.isna(recent_protein):
            protein_per_kg_lean = float(recent_protein) / float(recent_lean)

    # The trend compares the mean of days 1-7 with the mean of days 22-28.
    # Their midpoints are 21 days apart, so this is a three-week trend interval,
    # not four full weeks. Use that interval when translating the change to a
    # weekly percentage.
    weekly_weight_loss_pct = None
    if (
        recent_weight is not None
        and not pd.isna(recent_weight)
        and float(recent_weight) > 0
        and weight_delta_4w is not None
        and not pd.isna(weight_delta_4w)
    ):
        weekly_weight_loss_pct = (
            -float(weight_delta_4w) / float(recent_weight) / 3.0 * 100.0
        )

    fat_share_of_loss = None
    if (
        weight_delta_4w is not None
        and fat_delta_4w is not None
        and not pd.isna(weight_delta_4w)
        and not pd.isna(fat_delta_4w)
        and float(weight_delta_4w) < -0.2
        and float(fat_delta_4w) < 0
    ):
        fat_share_of_loss = (
            abs(float(fat_delta_4w)) / abs(float(weight_delta_4w)) * 100.0
        )

    calorie_vs_28_pct = None
    if (
        recent_calories is not None
        and not pd.isna(recent_calories)
        and avg_calories_28 is not None
        and not pd.isna(avg_calories_28)
        and float(avg_calories_28) > 0
    ):
        calorie_vs_28_pct = (float(recent_calories) / float(avg_calories_28) - 1.0) * 100.0

    workouts_per_week = None
    if workouts_28 is not None and not pd.isna(workouts_28):
        workouts_per_week = float(workouts_28) / 4.0

    strength_up, strength_flat, strength_down = _strength_summary(strength_4w)

    observations: list[str] = []
    suggestions: list[str] = []

    if fat_delta_4w is not None and lean_delta_4w is not None:
        observations.append(
            f"Over the four-week comparison window, fat mass changed by {float(fat_delta_4w):+.2f} kg and BIA-estimated lean mass by {float(lean_delta_4w):+.2f} kg."
        )
        if fat_share_of_loss is not None:
            observations.append(
                f"BIA-estimated fat loss accounts for about {fat_share_of_loss:.0f}% of the scale-weight reduction across those smoothed comparison windows. Treat this as a trend indicator, not a tissue-balance measurement."
            )
        if float(fat_delta_4w) < 0 and float(lean_delta_4w) < -0.5:
            observations.append(
                "That is a lean-mass preservation watch signal. Withings body composition is BIA, so hydration and glycogen can move the lean-mass estimate; treat the multi-week trend together with strength rather than as direct proof of muscle loss."
            )

    if strength_4w:
        observations.append(
            f"Strength context is {strength_up} lift(s) up, {strength_flat} flat, and {strength_down} down versus the prior four-week window."
        )
        if strength_up > 0 and strength_down == 0:
            observations.append(
                "The positive strength trend is reassuring and argues against interpreting all of the BIA lean-mass decline as true contractile muscle loss."
            )

    pace = energy.get("weight_loss_pct_week")
    if pace is None:
        pace = weekly_weight_loss_pct
    if pace is not None:
        if pace > 0.75:
            observations.append(
                f"Recent scale-loss pace is about {pace:.2f}% of body weight per week, which is relatively aggressive for a muscle-preservation goal."
            )
        elif pace >= 0.25:
            observations.append(
                f"Recent scale-loss pace is about {pace:.2f}% of body weight per week, a moderate pace; the main focus can stay on protein, recovery, and training quality rather than accelerating the deficit."
            )
        elif pace > 0:
            observations.append(
                f"Recent scale-loss pace is about {pace:.2f}% of body weight per week."
            )
        else:
            observations.append(
                f"Recent 28-day weight trend is approximately {pace:.2f}% of body weight per week; the scale is not currently trending downward."
            )

    if energy.get("estimated_tdee") is not None:
        observations.append(
            "Canonical multi-window energy estimate: "
            f"planning maintenance about {energy['estimated_tdee']:.0f} kcal/day, "
            f"with an estimated current deficit of {energy['estimated_deficit']:.0f} kcal/day. "
            f"28/42-day agreement is {energy.get('tdee_agreement', 'n/a')}; "
            f"28-day coverage is {energy.get('coverage_summary', energy.get('coverage_confidence', 'n/a'))}."
        )

    if protein_per_kg_lean is not None:
        observations.append(
            f"Current 7-day protein averages {_num(recent_protein, 0, ' g/day')} ({protein_per_kg_lean:.2f} g per kg of current estimated lean mass)."
        )

    if calorie_vs_28_pct is not None:
        observations.append(
            f"Current 7-day calories are {_percent(calorie_vs_28_pct)} versus the 28-day average ({_num(recent_calories, 0)} vs {_num(avg_calories_28, 0)} kcal/day)."
        )

    if workouts_per_week is not None:
        observations.append(
            f"Training frequency over 28 days is about {workouts_per_week:.2f} resistance sessions per week."
        )

    if protein_low is not None and protein_high is not None:
        if recent_protein is None or pd.isna(recent_protein) or float(recent_protein) < protein_low:
            suggestions.append(
                f"Raise protein toward a practical working range of about {protein_low:.0f}-{protein_high:.0f} g/day (1.8-2.2 g/kg of current estimated lean mass). A simple way to get there is roughly 30-45 g of high-quality protein across 3-4 meals."
            )
        else:
            suggestions.append(
                f"Protein is within the current working range of about {protein_low:.0f}-{protein_high:.0f} g/day; keep it consistent across the week."
            )

    if workouts_per_week is not None and workouts_per_week < 2.0:
        suggestions.append(
            "Keep the planned two resistance-training sessions per week as consistent as possible and prioritize productive working sets/progressive overload rather than adding large amounts of extra volume."
        )
    else:
        suggestions.append(
            "Keep resistance training performance as the main functional check on muscle retention; preserve productive working sets and progressive overload while dieting."
        )

    sleep_reference = avg_sleep_28 if avg_sleep_28 is not None and not pd.isna(avg_sleep_28) else recent_sleep
    if sleep_reference is not None and not pd.isna(sleep_reference) and float(sleep_reference) < 7.0:
        suggestions.append(
            f"Sleep averages about {float(sleep_reference):.1f} h/night; getting closer to 7+ hours where practical is a useful recovery lever for preserving training quality."
        )

    estimated_deficit = energy.get("estimated_deficit")
    if (
        estimated_deficit is not None
        and estimated_deficit > 750
        and lean_delta_4w is not None
        and not pd.isna(lean_delta_4w)
        and float(lean_delta_4w) < -0.5
    ):
        suggestions.append(
            "Do not make the calorie deficit larger right now. The rolling energy-balance estimate is already substantial while BIA lean mass is trending down; first improve protein/recovery consistency and watch the next 2-3 weeks of lean-mass and strength data."
        )
    elif (
        calorie_vs_28_pct is not None
        and calorie_vs_28_pct <= -10.0
        and lean_delta_4w is not None
        and not pd.isna(lean_delta_4w)
        and float(lean_delta_4w) < -0.5
    ):
        suggestions.append(
            "Do not push calories lower right now. The current week is already materially below the 28-day calorie average while BIA lean mass is trending down; hold the deficit steady and watch the next 2-3 weeks of lean-mass, strength, sleep, and protein data together."
        )
    elif pace is not None and pace > 0.75:
        suggestions.append(
            "Consider easing the calorie deficit rather than increasing it further if the faster loss rate persists, especially if strength or recovery starts to decline."
        )

    lines = [
        "Lean-Mass Preservation",
        "======================",
        f"Reporting window ends: {end_date.isoformat() if end_date else 'n/a'}",
        "",
        "Personal Trend",
        "--------------",
        f"4-week weight change: {_num(weight_delta_4w, 2, ' kg')}",
        f"4-week fat-mass change: {_num(fat_delta_4w, 2, ' kg')}",
        f"4-week BIA lean-mass change: {_num(lean_delta_4w, 2, ' kg')}",
        f"BIA-estimated fat share of weight loss: {_num(fat_share_of_loss, 0, '%')}",
        f"Recent weight-loss pace: {_num(pace, 2, '% of body weight/week')}",
        f"Canonical planning maintenance: {_num(energy.get('estimated_tdee'), 0, ' kcal/day')}",
        f"Canonical estimated calorie deficit: {_num(energy.get('estimated_deficit'), 0, ' kcal/day')}",
        f"28/42-day TDEE agreement: {energy.get('tdee_agreement', 'n/a')}",
        f"Energy-model source: {energy.get('energy_source', 'n/a')}",
        f"Current estimated lean mass: {_num(recent_lean, 1, ' kg')}",
        f"Current 7-day protein: {_num(recent_protein, 0, ' g/day')}",
        f"28-day protein: {_num(avg_protein_28, 0, ' g/day')}",
        f"28-day sleep: {_num(avg_sleep_28, 1, ' h/night')}",
        f"28-day resistance workouts: {_num(workouts_28, 0)}",
        "",
        "Interpretation",
        "--------------",
    ]
    lines.extend(f"- {item}" for item in observations)
    lines.extend(["", "Suggestions", "-----------"])
    lines.extend(f"- {item}" for item in suggestions)
    lines.extend(
        [
            "",
            "Method Note",
            "-----------",
            "Lean mass here is the Withings BIA estimate, not a direct muscle measurement. The report therefore cross-checks it against multi-week strength, protein, calorie, sleep, and training trends before suggesting changes.",
            "Maintenance/TDEE comes from the canonical adaptive energy model, which compares 28- and 42-day scale-weight/intake estimates and reports their agreement. The local 28-day calculation is retained only as a fallback. Water/glycogen shifts and food-logging error can materially move the estimate, so use it as a multi-week planning signal rather than a metabolic measurement.",
            "The protein range is a practical coaching heuristic for a resistance-trained calorie deficit, not an individualized medical prescription.",
        ]
    )

    text = "\n".join(lines)
    OUT_PATH.write_text(text, encoding="utf-8")
    print(f"Saved: {OUT_PATH}")
    print()
    print(text.encode("cp1252", errors="replace").decode("cp1252"))


if __name__ == "__main__":
    main()
