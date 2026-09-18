from __future__ import annotations

from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = REPORTS_DIR / "weekly_coaching_report.txt"


def fmt(x) -> str:
    if pd.isna(x):
        return "N/A"
    return f"{float(x):.2f}"


def main() -> None:
    con = duckdb.connect(str(DB_PATH))

    df = con.execute("""
        WITH source_dates AS (
            SELECT
                (SELECT MAX(date)
                 FROM clean.body_composition
                 WHERE weight_kg IS NOT NULL) AS body_date,
                (SELECT MAX(date)
                 FROM clean.fitbit_daily
                 WHERE steps IS NOT NULL
                    OR sleep_hours IS NOT NULL
                    OR resting_hr IS NOT NULL
                    OR hrv IS NOT NULL) AS activity_date,
                (SELECT MAX(date)
                 FROM clean.nutrition_daily
                 WHERE calories IS NOT NULL
                    OR protein_g IS NOT NULL) AS nutrition_date
        ),
        cutoff AS (
            SELECT CASE
                WHEN body_date IS NULL
                  OR activity_date IS NULL
                  OR nutrition_date IS NULL
                THEN NULL
                ELSE LEAST(body_date, activity_date, nutrition_date)
            END AS analysis_end_date
            FROM source_dates
        ),
        dates AS (
            SELECT dm.date, c.analysis_end_date
            FROM analytics.daily_metrics dm
            CROSS JOIN cutoff c
            WHERE c.analysis_end_date IS NOT NULL
              AND dm.date BETWEEN c.analysis_end_date - INTERVAL 13 DAY
                              AND c.analysis_end_date
        ),
        joined AS (
            SELECT
                d.date,
                d.analysis_end_date,
                dm.weight_kg,
                dm.fat_mass_kg,
                dm.lean_mass_kg,
                dm.calories,
                dm.protein_g,
                n.carbs_g,
                n.fat_g,
                n.fiber_g,
                n.alcohol_g,
                f.steps,
                f.sleep_hours,
                f.resting_hr,
                f.hrv,
                t.workout_count,
                t.total_volume
            FROM dates d
            LEFT JOIN analytics.daily_metrics dm
                ON d.date = dm.date
            LEFT JOIN clean.nutrition_daily n
                ON d.date = n.date
            LEFT JOIN clean.fitbit_daily f
                ON d.date = f.date
            LEFT JOIN clean.training_summary t
                ON d.date = t.date
        ),
        recent_7 AS (
            SELECT * FROM joined
            WHERE date BETWEEN analysis_end_date - INTERVAL 6 DAY
                           AND analysis_end_date
        ),
        prior_7 AS (
            SELECT * FROM joined
            WHERE date BETWEEN analysis_end_date - INTERVAL 13 DAY
                           AND analysis_end_date - INTERVAL 7 DAY
        )
        SELECT
            (SELECT MAX(analysis_end_date) FROM joined) AS analysis_end_date,
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
            (SELECT AVG(fiber_g) FROM recent_7) AS recent_fiber,
            (SELECT AVG(alcohol_g) FROM recent_7) AS recent_alcohol,

            (SELECT AVG(steps) FROM recent_7) AS recent_steps,
            (SELECT AVG(sleep_hours) FROM recent_7) AS recent_sleep,
            (SELECT AVG(resting_hr) FROM recent_7) AS recent_rhr,
            (SELECT AVG(hrv) FROM recent_7) AS recent_hrv,

            (SELECT SUM(workout_count) FROM recent_7) AS recent_workouts,
            (SELECT AVG(total_volume) FROM recent_7 WHERE total_volume IS NOT NULL) AS recent_training_volume,

            (SELECT AVG(resting_hr) FROM prior_7) AS prior_rhr,
            (SELECT AVG(hrv) FROM prior_7) AS prior_hrv,
            (SELECT AVG(sleep_hours) FROM prior_7) AS prior_sleep
    """).fetchdf()

    con.close()

    if df.empty or pd.isna(df.iloc[0]["analysis_end_date"]):
        print("No complete reporting window found.")
        return

    row = df.iloc[0]

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

    score = 0
    notes = []
    next_week = []

    if pd.notna(fat_delta) and fat_delta < 0:
        score += 2
        notes.append("Fat mass moved in the right direction.")
    elif pd.notna(weight_delta) and weight_delta < 0:
        score += 1
        notes.append("Weight is down, though body composition trend matters more than scale alone.")

    if pd.notna(lean_delta) and lean_delta >= 0:
        score += 2
        notes.append("Lean mass held steady or improved.")
    elif pd.notna(lean_delta) and lean_delta < -0.25:
        score -= 2
        notes.append("Lean mass appears to be slipping.")
        next_week.append("Increase protein consistency and protect training quality.")

    if pd.notna(row["recent_protein"]) and row["recent_protein"] >= 110:
        score += 2
        notes.append("Protein intake looks supportive for recomp.")
    else:
        score -= 2
        notes.append("Protein is low or missing for a strength-focused phase.")
        next_week.append("Push protein toward 110–130 g/day.")

    if pd.notna(row["recent_sleep"]) and row["recent_sleep"] >= 7:
        score += 1
        notes.append("Sleep is supportive.")
    elif pd.notna(row["recent_sleep"]) and row["recent_sleep"] < 6.5:
        score -= 1
        notes.append("Sleep is limiting recovery.")
        next_week.append("Protect sleep; aim for 7+ hours.")

    if pd.notna(rhr_delta) and rhr_delta > 3:
        score -= 2
        notes.append("Resting HR is elevated versus the prior week.")
        next_week.append("Reduce overall stress load and avoid aggressive dieting.")
    elif pd.notna(row["recent_rhr"]) and row["recent_rhr"] <= 72:
        score += 1
        notes.append("Resting HR looks calm.")

    if pd.notna(hrv_delta) and hrv_delta > 1:
        score += 1
        notes.append("HRV improved versus the prior week.")
    elif pd.notna(hrv_delta) and hrv_delta < -2:
        score -= 1
        notes.append("HRV fell versus the prior week.")
        next_week.append("Watch recovery and avoid stacking too much stress.")

    # Updated for your real target: 2 lifting sessions/week
    if pd.notna(row["recent_workouts"]) and row["recent_workouts"] >= 2:
        score += 2
        notes.append("Training frequency matches your realistic 2x/week plan.")
    elif pd.notna(row["recent_workouts"]) and row["recent_workouts"] == 1:
        score -= 1
        notes.append("Training frequency fell below your normal 2x/week target.")
        next_week.append("Hit both planned lifting sessions this week.")
    else:
        score -= 2
        notes.append("No meaningful lifting sessions were captured this week.")
        next_week.append("Get back to your 2 planned lifting sessions.")

    if pd.notna(row["recent_steps"]) and row["recent_steps"] >= 7000:
        score += 1
        notes.append("Baseline activity is good.")
    else:
        next_week.append("Keep daily movement up; target 7k+ steps.")

    if pd.notna(row["recent_calories"]) and row["recent_calories"] < 1500:
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

    deduped = []
    seen = set()
    for item in next_week:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    next_week = deduped

    lines = []
    lines.append("Weekly Coaching Report")
    lines.append("=====================")
    lines.append("")
    lines.append(f"Reporting window ends: {row['analysis_end_date']}")
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
    lines.append(f"fiber: {fmt(row['recent_fiber'])}")
    lines.append(f"alcohol: {fmt(row['recent_alcohol'])}")
    lines.append("")
    lines.append("Training and Activity")
    lines.append("---------------------")
    lines.append(f"workouts (7d): {fmt(row['recent_workouts'])}")
    lines.append(f"avg training volume: {fmt(row['recent_training_volume'])}")
    lines.append(f"steps: {fmt(row['recent_steps'])}")
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
    lines.append("Because your current goal is strength + sustainable fat loss, the best week is not the one with the fastest scale drop; it is the one where fat trends down while lean mass, recovery, and training all stay supported within your real 2x/week lifting schedule.")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")

    safe_output = "\n".join(lines).encode("cp1252", errors="replace").decode("cp1252")
    print(f"Saved: {OUT_PATH}")
    print()
    print(safe_output)


if __name__ == "__main__":
    main()
