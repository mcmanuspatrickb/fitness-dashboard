from __future__ import annotations

from pathlib import Path

import pandas as pd

from report_context import load_report_context


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = REPORTS_DIR / "weekly_coaching_report.txt"


def fmt(x) -> str:
    if x is None or pd.isna(x):
        return "N/A"
    return f"{float(x):.2f}"


def fmt0(x) -> str:
    if x is None or pd.isna(x):
        return "N/A"
    return f"{float(x):.0f}"


def main() -> None:
    context = load_report_context()
    analysis_end_date = context.get("analysis_end_date")
    row = context.get("weekly", {})
    coverage = context.get("coverage", {})
    trend_4w = context.get("trend_4w", {})
    strength_4w = context.get("strength_4w", [])

    if analysis_end_date is None or not row:
        print("No complete reporting window found.")
        return

    weight_delta = row.get("weight_delta")
    fat_delta = row.get("fat_delta")
    lean_delta = row.get("lean_delta")
    rhr_delta = row.get("rhr_delta")
    hrv_delta = row.get("hrv_delta")
    sleep_delta = row.get("sleep_delta")

    score = 0
    notes: list[str] = []
    next_week: list[str] = []

    if fat_delta is not None and fat_delta < 0:
        score += 2
        notes.append("Fat mass moved in the right direction.")
    elif weight_delta is not None and weight_delta < 0:
        score += 1
        notes.append("Weight is down, though body composition trend matters more than scale alone.")

    if lean_delta is not None and lean_delta >= 0:
        score += 2
        notes.append("Lean mass held steady or improved.")
    elif lean_delta is not None and lean_delta < -0.25:
        score -= 2
        notes.append("BIA-estimated lean mass appears to be slipping; cross-check the multi-week trend against strength before treating it as muscle loss.")
        next_week.append("Prioritize the lean-mass preservation protein target and protect training quality.")

    recent_protein = row.get("recent_protein")
    recent_lean = row.get("recent_lean")
    protein_target_low = None
    if recent_lean is not None and not pd.isna(recent_lean) and float(recent_lean) > 0:
        protein_target_low = float(recent_lean) * 1.8

    if (
        recent_protein is not None
        and protein_target_low is not None
        and float(recent_protein) >= protein_target_low
    ):
        score += 2
        notes.append("Protein is within the current lean-mass preservation working range.")
    elif recent_protein is not None and recent_protein >= 110:
        score += 1
        notes.append("Protein is a reasonable baseline, but it is below the current lean-mass preservation working range.")
        next_week.append("Use the lean-mass preservation section for the personalized protein target.")
    elif recent_protein is not None:
        score -= 2
        notes.append("Protein is low for a strength-focused fat-loss phase.")
        next_week.append("Use the lean-mass preservation section for the personalized protein target.")
    else:
        notes.append("Protein data is unavailable for this reporting window.")

    recent_sleep = row.get("recent_sleep")
    if recent_sleep is not None and recent_sleep >= 7:
        score += 1
        notes.append("Sleep is supportive.")
    elif recent_sleep is not None and recent_sleep < 6.5:
        score -= 1
        notes.append("Sleep is limiting recovery.")
        next_week.append("Protect sleep; aim for 7+ hours.")

    if rhr_delta is not None and rhr_delta > 3:
        score -= 2
        notes.append("Resting HR is elevated versus the prior week.")
        next_week.append("Reduce overall stress load and avoid aggressive dieting.")
    elif row.get("recent_rhr") is not None and row["recent_rhr"] <= 72:
        score += 1
        notes.append("Resting HR looks calm.")

    if hrv_delta is not None and hrv_delta > 1:
        score += 1
        notes.append("HRV improved versus the prior week.")
    elif hrv_delta is not None and hrv_delta < -2:
        score -= 1
        notes.append("HRV fell versus the prior week.")
        next_week.append("Watch recovery and avoid stacking too much stress.")

    recent_workouts = row.get("recent_workouts")
    if recent_workouts is not None and recent_workouts >= 2:
        score += 2
        notes.append("Training frequency matches your realistic 2x/week plan.")
    elif recent_workouts is not None and recent_workouts == 1:
        score -= 1
        notes.append("Training frequency fell below your normal 2x/week target.")
        next_week.append("Hit both planned lifting sessions this week.")
    elif recent_workouts is not None:
        score -= 2
        notes.append("No meaningful lifting sessions were captured this week.")
        next_week.append("Get back to your 2 planned lifting sessions.")
    else:
        notes.append("Training data is unavailable for this reporting window.")

    recent_steps = row.get("recent_steps")
    if recent_steps is not None and recent_steps >= 7000:
        score += 1
        notes.append("Baseline activity is good.")
    elif recent_steps is not None:
        next_week.append("Keep daily movement up; target 7k+ steps.")

    recent_calories = row.get("recent_calories")
    if recent_calories is not None and recent_calories < 1500:
        score -= 1
        notes.append("Calories may be too low for a strength-focused recomposition phase.")
        next_week.append("Do not under-fuel the week if strength is the priority.")

    if score >= 6:
        grade = "A"
    elif score >= 3:
        grade = "B"
    elif score >= 0:
        grade = "C"
    else:
        grade = "D"

    if not next_week:
        next_week.append("Stay steady. You do not need a dramatic change next week.")

    deduped: list[str] = []
    seen: set[str] = set()
    for item in next_week:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    next_week = deduped

    lines: list[str] = []
    lines.append("Weekly Coaching Report")
    lines.append("=====================")
    lines.append("")
    lines.append(f"Reporting window ends: {analysis_end_date}")
    lines.append("")

    lines.append("Data Quality")
    lines.append("------------")
    lines.append(
        f"coverage confidence: {coverage.get('confidence', 'UNKNOWN')} "
        "(coverage-based; not device measurement accuracy)"
    )
    lines.append(f"body composition: {coverage.get('body_composition_days', 0)}/7 days")
    lines.append(f"nutrition: {coverage.get('nutrition_days', 0)}/7 days")
    lines.append(f"steps: {coverage.get('steps_days', 0)}/7 days")
    lines.append(f"sleep: {coverage.get('sleep_days', 0)}/7 days")
    lines.append(f"recovery (RHR + HRV): {coverage.get('recovery_days', 0)}/7 days")
    lines.append(f"workouts captured: {coverage.get('workouts', 0)}")
    lines.append("")

    lines.append("Body Composition")
    lines.append("----------------")
    lines.append(f"weight change vs prior 7d: {fmt(weight_delta)}")
    lines.append(f"fat mass change vs prior 7d: {fmt(fat_delta)}")
    lines.append(f"lean mass change vs prior 7d: {fmt(lean_delta)}")
    lines.append("")

    lines.append("Recovery")
    lines.append("--------")
    lines.append(f"sleep: {fmt(row.get('recent_sleep'))} (delta {fmt(sleep_delta)})")
    lines.append(f"RHR: {fmt(row.get('recent_rhr'))} (delta {fmt(rhr_delta)})")
    lines.append(f"HRV: {fmt(row.get('recent_hrv'))} (delta {fmt(hrv_delta)})")
    lines.append("")

    lines.append("Nutrition")
    lines.append("---------")
    lines.append(f"calories: {fmt(row.get('recent_calories'))}")
    lines.append(f"protein: {fmt(row.get('recent_protein'))}")
    lines.append(f"carbs: {fmt(row.get('recent_carbs'))}")
    lines.append(f"fat: {fmt(row.get('recent_fat_g'))}")
    lines.append(f"fiber: {fmt(row.get('recent_fiber'))}")
    lines.append(f"alcohol: {fmt(row.get('recent_alcohol'))}")
    lines.append("")

    lines.append("Training and Activity")
    lines.append("---------------------")
    lines.append(f"workouts (7d): {fmt(row.get('recent_workouts'))}")
    lines.append(f"avg training volume: {fmt(row.get('recent_training_volume'))}")
    lines.append(f"steps: {fmt(row.get('recent_steps'))}")
    lines.append("")

    lines.append("4-Week Context")
    lines.append("--------------")
    lines.append(
        f"weight change (latest 7d avg vs first 7d avg): {fmt(trend_4w.get('weight_delta'))} kg"
    )
    lines.append(
        f"fat mass change (latest 7d avg vs first 7d avg): {fmt(trend_4w.get('fat_delta'))} kg"
    )
    lines.append(
        f"lean mass change (latest 7d avg vs first 7d avg): {fmt(trend_4w.get('lean_delta'))} kg"
    )
    lines.append(f"28d avg calories: {fmt0(trend_4w.get('avg_calories'))} kcal/day")
    lines.append(f"28d avg protein: {fmt0(trend_4w.get('avg_protein'))} g/day")
    lines.append(f"28d avg steps: {fmt0(trend_4w.get('avg_steps'))}/day")
    lines.append(f"28d avg sleep: {fmt(trend_4w.get('avg_sleep'))} h/night")
    lines.append(f"28d workouts: {fmt0(trend_4w.get('workouts'))}")
    lines.append("")

    lines.append("4-Week Strength Context")
    lines.append("-----------------------")
    lines.append("Compares the best e1RM in the latest four weeks with the best e1RM in the prior four weeks.")
    if strength_4w:
        for item in strength_4w:
            lines.append(
                f"{item['label']}: current 4w best {item['current_best_e1rm']:.1f} kg vs "
                f"prior 4w best {item['prior_best_e1rm']:.1f} kg e1RM; "
                f"change {item['change_e1rm']:+.1f} kg ({item['direction']}; "
                f"{item['current_observations']} current / {item['prior_observations']} prior weekly observations)"
            )
    else:
        lines.append("Not enough comparable lift observations across the latest and prior four-week windows.")
    lines.append("")

    lines.append("Overall Grade")
    lines.append("-------------")
    lines.append(f"{grade} (score {score})")
    lines.append("")

    lines.append("What Went Well / What Needs Work")
    lines.append("--------------------------------")
    for note in notes:
        lines.append(f"- {note}")
    lines.append("")

    lines.append("Next Week Focus")
    lines.append("---------------")
    for item in next_week[:4]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("Coach's View")
    lines.append("------------")
    lines.append(
        "Because your current goal is strength + sustainable fat loss, the best week is not the one with the fastest scale drop; "
        "it is the one where fat trends down while lean mass, recovery, and training all stay supported within your real 2x/week lifting schedule."
    )

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")

    safe_output = "\n".join(lines).encode("cp1252", errors="replace").decode("cp1252")
    print(f"Saved: {OUT_PATH}")
    print()
    print(safe_output)


if __name__ == "__main__":
    main()
