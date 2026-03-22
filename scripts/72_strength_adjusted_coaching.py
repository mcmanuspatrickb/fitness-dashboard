from __future__ import annotations

from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = REPORTS_DIR / "strength_adjusted_coaching.txt"


TARGET_LIFTS = [
    "squat",
    "bench_press",
    "deadlift",
    "row",
    "pull_up",
    "overhead_press",
]


def fmt(x) -> str:
    if pd.isna(x):
        return "N/A"
    return f"{float(x):.2f}"


def safe_print(lines: list[str]) -> None:
    safe_output = "\n".join(lines).encode("cp1252", errors="replace").decode("cp1252")
    print(safe_output)


def main() -> None:
    con = duckdb.connect(str(DB_PATH))

    body_df = con.execute("""
        WITH dates AS (
            SELECT date
            FROM analytics.daily_metrics
            WHERE date >= CURRENT_DATE - 14
        ),
        joined AS (
            SELECT
                d.date,
                dm.weight_kg,
                dm.fat_mass_kg,
                dm.lean_mass_kg,
                dm.calories,
                dm.protein_g,
                dm.carbs_g,
                dm.fat_g,
                f.steps,
                f.sleep_hours,
                f.resting_hr,
                f.hrv,
                t.workout_count,
                t.total_volume
            FROM dates d
            LEFT JOIN analytics.daily_metrics dm
                ON d.date = dm.date
            LEFT JOIN clean.fitbit_daily f
                ON d.date = f.date
            LEFT JOIN clean.training_summary t
                ON d.date = t.date
        ),
        recent_7 AS (
            SELECT * FROM joined WHERE date >= CURRENT_DATE - 7
        ),
        prior_7 AS (
            SELECT * FROM joined
            WHERE date < CURRENT_DATE - 7
              AND date >= CURRENT_DATE - 14
        )
        SELECT
            (SELECT AVG(weight_kg) FROM recent_7) AS recent_weight,
            (SELECT AVG(weight_kg) FROM prior_7) AS prior_weight,

            (SELECT AVG(fat_mass_kg) FROM recent_7) AS recent_fat,
            (SELECT AVG(fat_mass_kg) FROM prior_7) AS prior_fat,

            (SELECT AVG(lean_mass_kg) FROM recent_7) AS recent_lean,
            (SELECT AVG(lean_mass_kg) FROM prior_7) AS prior_lean,

            (SELECT AVG(calories) FROM recent_7) AS recent_calories,
            (SELECT AVG(protein_g) FROM recent_7) AS recent_protein,
            (SELECT AVG(carbs_g) FROM recent_7) AS recent_carbs,
            (SELECT AVG(fat_g) FROM recent_7) AS recent_fat_g,

            (SELECT AVG(steps) FROM recent_7) AS recent_steps,
            (SELECT AVG(sleep_hours) FROM recent_7) AS recent_sleep,
            (SELECT AVG(resting_hr) FROM recent_7) AS recent_rhr,
            (SELECT AVG(hrv) FROM recent_7) AS recent_hrv,

            (SELECT AVG(resting_hr) FROM prior_7) AS prior_rhr,
            (SELECT AVG(hrv) FROM prior_7) AS prior_hrv,
            (SELECT AVG(sleep_hours) FROM prior_7) AS prior_sleep,

            (SELECT SUM(workout_count) FROM recent_7) AS recent_workouts,
            (SELECT AVG(total_volume) FROM recent_7 WHERE total_volume IS NOT NULL) AS recent_training_volume
    """).fetchdf()

    strength_df = con.execute("""
        SELECT
            week_start,
            target_lift,
            estimated_1rm,
            e1rm_change_vs_prev,
            trend
        FROM read_csv_auto(?)
    """, [str(REPORTS_DIR / "strength_progress_weekly.csv")]).fetchdf()

    con.close()

    if body_df.empty:
        print("No body/recovery data found.")
        return

    row = body_df.iloc[0]

    weight_delta = (
        row["recent_weight"] - row["prior_weight"]
        if pd.notna(row["recent_weight"]) and pd.notna(row["prior_weight"])
        else pd.NA
    )
    fat_delta = (
        row["recent_fat"] - row["prior_fat"]
        if pd.notna(row["recent_fat"]) and pd.notna(row["prior_fat"])
        else pd.NA
    )
    lean_delta = (
        row["recent_lean"] - row["prior_lean"]
        if pd.notna(row["recent_lean"]) and pd.notna(row["prior_lean"])
        else pd.NA
    )
    rhr_delta = (
        row["recent_rhr"] - row["prior_rhr"]
        if pd.notna(row["recent_rhr"]) and pd.notna(row["prior_rhr"])
        else pd.NA
    )
    hrv_delta = (
        row["recent_hrv"] - row["prior_hrv"]
        if pd.notna(row["recent_hrv"]) and pd.notna(row["prior_hrv"])
        else pd.NA
    )
    sleep_delta = (
        row["recent_sleep"] - row["prior_sleep"]
        if pd.notna(row["recent_sleep"]) and pd.notna(row["prior_sleep"])
        else pd.NA
    )

    latest_strength = pd.DataFrame()
    if not strength_df.empty:
        latest_week = strength_df["week_start"].max()
        latest_strength = strength_df[strength_df["week_start"] == latest_week].copy()

    strength_up = 0
    strength_flat = 0
    strength_down = 0
    strength_summary_lines: list[str] = []

    for lift in TARGET_LIFTS:
        sub = latest_strength[latest_strength["target_lift"] == lift]
        if sub.empty:
            strength_summary_lines.append(f"{lift}: no recent data")
            continue

        r = sub.iloc[0]
        trend = str(r["trend"])
        if trend == "up":
            strength_up += 1
        elif trend == "down":
            strength_down += 1
        else:
            strength_flat += 1

        strength_summary_lines.append(
            f"{lift}: e1RM={fmt(r['estimated_1rm'])}, trend={trend}, change={fmt(r['e1rm_change_vs_prev'])}"
        )

    notes: list[str] = []
    recommendations: list[str] = []

    if pd.notna(fat_delta) and fat_delta < 0:
        notes.append("Fat mass is moving in the right direction.")
    elif pd.notna(weight_delta) and weight_delta < 0:
        notes.append("Scale weight is down, though body composition is the more important signal here.")

    if pd.notna(lean_delta) and lean_delta < -0.25:
        notes.append("Lean mass is slipping enough to matter for a strength-focused phase.")
        recommendations.append("Increase calories slightly or reduce total fatigue so lean mass stabilizes.")

    if pd.notna(rhr_delta) and rhr_delta > 3:
        notes.append("Resting HR is elevated versus the prior week, suggesting recovery stress.")
        recommendations.append("Reduce overall stress load this week and avoid digging the deficit deeper.")

    if pd.notna(row["recent_sleep"]) and row["recent_sleep"] >= 7:
        notes.append("Sleep is supportive.")
    elif pd.notna(row["recent_sleep"]) and row["recent_sleep"] < 6.5:
        notes.append("Sleep is limiting progress.")
        recommendations.append("Protect sleep before changing training variables.")

    if pd.notna(row["recent_protein"]) and row["recent_protein"] >= 120:
        notes.append("Protein intake is supportive for muscle retention and performance.")
    elif pd.notna(row["recent_protein"]) and row["recent_protein"] < 110:
        notes.append("Protein is a little light for your current goal.")
        recommendations.append("Push protein toward 120–140 g/day.")

    if pd.notna(row["recent_calories"]) and row["recent_calories"] < 1600:
        notes.append("Calories may be too low for a strength-focused recomp phase.")
        recommendations.append("Consider adding roughly 150–300 kcal/day, especially around training.")

    if pd.notna(row["recent_workouts"]) and row["recent_workouts"] < 2:
        notes.append("Training frequency is below even your realistic minimum.")
        recommendations.append("Hit both planned lifting sessions this week.")
    elif pd.notna(row["recent_workouts"]) and row["recent_workouts"] < 3:
        notes.append("Training frequency is workable for your schedule, but session quality matters a lot.")
        recommendations.append("Make both lifting sessions count with high-quality top sets.")

    if strength_up >= 3:
        notes.append("Multiple lifts are trending up, so the program is still working.")
    if strength_down >= 2:
        notes.append("Several lifts are slipping, which usually means fatigue or under-fueling is accumulating.")
        recommendations.append("Bias toward recovery and slightly better fueling before changing the program.")
    elif strength_down == 1:
        notes.append("One lift is slipping; watch it, but do not overreact yet.")

    if (
        pd.notna(fat_delta) and fat_delta < 0
        and pd.notna(lean_delta) and lean_delta >= -0.25
        and (pd.isna(rhr_delta) or rhr_delta <= 3)
        and strength_up >= 2
    ):
        headline = "SWEET SPOT"
        summary = "You are losing fat while keeping performance and recovery in a workable range. Stay the course."
    elif (
        pd.notna(fat_delta) and fat_delta < 0
        and (
            (pd.notna(lean_delta) and lean_delta < -0.25)
            or (pd.notna(rhr_delta) and rhr_delta > 3)
            or strength_down >= 2
        )
    ):
        headline = "ADJUST, DON'T PANIC"
        summary = "Progress is happening, but you are likely a bit under-recovered or under-fueled for your strength goal."
    else:
        headline = "HOLD STEADY AND MONITOR"
        summary = "The picture is mixed. Avoid dramatic changes and watch the next 1–2 weeks."

    if not recommendations:
        recommendations.append("Stay steady this week and keep collecting consistent data.")

    lines: list[str] = []
    lines.append("Strength-Adjusted Coaching")
    lines.append("==========================")
    lines.append("")
    lines.append("Headline")
    lines.append("--------")
    lines.append(headline)
    lines.append(summary)
    lines.append("")
    lines.append("Body Composition")
    lines.append("----------------")
    lines.append(f"weight change vs prior 7d: {fmt(weight_delta)}")
    lines.append(f"fat mass change vs prior 7d: {fmt(fat_delta)}")
    lines.append(f"lean mass change vs prior 7d: {fmt(lean_delta)}")
    lines.append("")
    lines.append("Recovery")
    lines.append("--------")
    lines.append(f"sleep: {fmt(row['recent_sleep'])} (delta {fmt(sleep_delta)})")
    lines.append(f"RHR: {fmt(row['recent_rhr'])} (delta {fmt(rhr_delta)})")
    lines.append(f"HRV: {fmt(row['recent_hrv'])} (delta {fmt(hrv_delta)})")
    lines.append("")
    lines.append("Nutrition")
    lines.append("---------")
    lines.append(f"calories: {fmt(row['recent_calories'])}")
    lines.append(f"protein: {fmt(row['recent_protein'])}")
    lines.append(f"carbs: {fmt(row['recent_carbs'])}")
    lines.append(f"fat: {fmt(row['recent_fat_g'])}")
    lines.append("")
    lines.append("Training")
    lines.append("--------")
    lines.append(f"workouts (7d): {fmt(row['recent_workouts'])}")
    lines.append(f"avg training volume: {fmt(row['recent_training_volume'])}")
    lines.append(f"steps: {fmt(row['recent_steps'])}")
    lines.append("")
    lines.append("Strength Snapshot")
    lines.append("-----------------")
    lines.extend(strength_summary_lines)
    lines.append("")
    lines.append("What This Means")
    lines.append("---------------")
    for note in notes:
        lines.append(f"- {note}")
    lines.append("")
    lines.append("Next Week Recommendations")
    lines.append("-------------------------")
    for rec in recommendations[:5]:
        lines.append(f"- {rec}")
    lines.append("")
    lines.append("Coach's View")
    lines.append("------------")
    lines.append("With only 2 strength sessions per week, your goal is not to do more. It is to recover well enough that both sessions are productive and your main lifts trend upward while fat mass trends down.")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")

    print(f"Saved: {OUT_PATH}")
    print()
    safe_print(lines)


if __name__ == "__main__":
    main()