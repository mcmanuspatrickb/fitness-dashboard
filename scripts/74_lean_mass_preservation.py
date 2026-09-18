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


def main() -> None:
    context = load_report_context()
    weekly = context.get("weekly", {})
    trend = context.get("trend_4w", {})
    strength_4w = context.get("strength_4w", [])
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

    protein_per_kg_lean = None
    protein_low = None
    protein_high = None
    if recent_lean is not None and not pd.isna(recent_lean) and float(recent_lean) > 0:
        protein_low = float(recent_lean) * PROTEIN_LOW_PER_KG_LEAN
        protein_high = float(recent_lean) * PROTEIN_HIGH_PER_KG_LEAN
        if recent_protein is not None and not pd.isna(recent_protein):
            protein_per_kg_lean = float(recent_protein) / float(recent_lean)

    weekly_weight_loss_pct = None
    if (
        recent_weight is not None
        and not pd.isna(recent_weight)
        and float(recent_weight) > 0
        and weight_delta_4w is not None
        and not pd.isna(weight_delta_4w)
    ):
        weekly_weight_loss_pct = abs(float(weight_delta_4w)) / float(recent_weight) / 4.0 * 100.0

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

    if weekly_weight_loss_pct is not None:
        if weekly_weight_loss_pct > 0.75:
            observations.append(
                f"Average four-week scale-loss pace is about {weekly_weight_loss_pct:.2f}% of body weight per week, which is relatively aggressive for a muscle-preservation goal."
            )
        elif weekly_weight_loss_pct >= 0.25:
            observations.append(
                f"Average four-week scale-loss pace is about {weekly_weight_loss_pct:.2f}% of body weight per week, a moderate pace; the main focus can stay on protein, recovery, and training quality rather than accelerating the deficit."
            )
        else:
            observations.append(
                f"Average four-week scale-loss pace is about {weekly_weight_loss_pct:.2f}% of body weight per week."
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

    if (
        calorie_vs_28_pct is not None
        and calorie_vs_28_pct <= -10.0
        and lean_delta_4w is not None
        and not pd.isna(lean_delta_4w)
        and float(lean_delta_4w) < -0.5
    ):
        suggestions.append(
            "Do not push calories lower right now. The current week is already materially below the 28-day calorie average while BIA lean mass is trending down; hold the deficit steady and watch the next 2-3 weeks of lean-mass, strength, sleep, and protein data together."
        )
    elif weekly_weight_loss_pct is not None and weekly_weight_loss_pct > 0.75:
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
