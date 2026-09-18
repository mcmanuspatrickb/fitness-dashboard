from __future__ import annotations

from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = REPORTS_DIR / "adaptive_calorie_recommendation.txt"


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


def load_strength_snapshot() -> pd.DataFrame:
    path = REPORTS_DIR / "strength_progress_weekly.csv"
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path)
    if df.empty or "week_start" not in df.columns:
        return pd.DataFrame()

    latest_week = df["week_start"].max()
    return df[df["week_start"] == latest_week].copy()


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
                dm.carbs_g,
                dm.fat_g,
                fb.steps,
                fb.sleep_hours,
                fb.resting_hr,
                fb.hrv,
                ts.workout_count,
                ts.total_volume
            FROM dates d
            LEFT JOIN analytics.daily_metrics dm
                ON d.date = dm.date
            LEFT JOIN clean.fitbit_daily fb
                ON d.date = fb.date
            LEFT JOIN clean.training_summary ts
                ON d.date = ts.date
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

    con.close()

    if df.empty or pd.isna(df.iloc[0]["analysis_end_date"]):
        raise RuntimeError("No complete recent reporting window found.")

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

    strength_df = load_strength_snapshot()

    strength_up = 0
    strength_down = 0
    strength_flat = 0

    if not strength_df.empty and "target_lift" in strength_df.columns and "trend" in strength_df.columns:
        for lift in TARGET_LIFTS:
            sub = strength_df[strength_df["target_lift"] == lift]
            if sub.empty:
                continue
            trend = str(sub.iloc[0]["trend"])
            if trend == "up":
                strength_up += 1
            elif trend == "down":
                strength_down += 1
            else:
                strength_flat += 1

    current_calories = row["recent_calories"]
    recommendation = "HOLD"
    calorie_change = 0
    rationale: list[str] = []

    if (
        pd.notna(lean_delta) and lean_delta < -0.25
        and (
            (pd.notna(rhr_delta) and rhr_delta > 3)
            or strength_down >= 2
            or (pd.notna(current_calories) and current_calories < 1600)
        )
    ):
        recommendation = "INCREASE"
        calorie_change = 250
        rationale.append("Lean mass is slipping in a meaningful way.")
        if pd.notna(rhr_delta) and rhr_delta > 3:
            rationale.append("Resting HR is elevated, suggesting recovery stress.")
        if pd.notna(current_calories) and current_calories < 1600:
            rationale.append("Current calories are likely too low for a strength-focused phase.")
        if strength_down >= 2:
            rationale.append("Several lifts are slipping, which often signals under-recovery or under-fueling.")

    elif (
        pd.notna(fat_delta) and fat_delta < 0
        and pd.notna(lean_delta) and lean_delta < 0
        and strength_up >= 2
        and pd.notna(current_calories) and current_calories < 1700
    ):
        recommendation = "INCREASE"
        calorie_change = 150
        rationale.append("Fat loss is working, but some lean mass is being traded away.")
        rationale.append("Strength is still mostly holding, so a small calorie increase may improve quality without stopping progress.")

    elif (
        pd.notna(fat_delta) and fat_delta < 0
        and (pd.isna(lean_delta) or lean_delta >= -0.20)
        and (pd.isna(rhr_delta) or rhr_delta <= 3)
        and strength_up >= 2
    ):
        recommendation = "HOLD"
        calorie_change = 0
        rationale.append("You appear to be in the sweet spot: fat is down, performance is good, and recovery looks acceptable.")

    elif (
        pd.notna(fat_delta) and fat_delta >= -0.10
        and (pd.isna(lean_delta) or lean_delta >= -0.20)
        and (pd.isna(rhr_delta) or rhr_delta <= 2)
        and strength_up + strength_flat >= 3
        and pd.notna(current_calories) and current_calories > 1700
    ):
        recommendation = "DECREASE"
        calorie_change = -100
        rationale.append("Fat loss looks close to stalled while strength and recovery appear stable.")
        rationale.append("A small calorie reduction is more appropriate than a big cut or a fast.")

    else:
        recommendation = "HOLD"
        calorie_change = 0
        rationale.append("The signal mix is not strong enough to justify a major calorie change.")
        rationale.append("Keep the plan steady and reassess after another week of consistent training and nutrition.")

    macro_hint = ""
    if calorie_change > 0:
        macro_hint = (
            f"Add about {calorie_change} kcal/day, ideally with mostly carbs around training "
            f"plus a small amount of fat if needed."
        )
    elif calorie_change < 0:
        macro_hint = (
            f"Reduce by about {abs(calorie_change)} kcal/day, preferably from discretionary carbs/fats "
            f"rather than protein."
        )
    else:
        macro_hint = (
            "Hold current calories steady. Use the lean-mass preservation section "
            "to guide protein rather than assuming protein should stay unchanged."
        )

    lines: list[str] = []
    lines.append("Adaptive Calorie Recommendation")
    lines.append("==============================")
    lines.append("")
    lines.append(f"Reporting window ends: {row['analysis_end_date']}")
    lines.append("")
    lines.append("Current Trend")
    lines.append("-------------")
    lines.append(f"weight change vs prior 7d: {fmt(weight_delta)}")
    lines.append(f"fat mass change vs prior 7d: {fmt(fat_delta)}")
    lines.append(f"lean mass change vs prior 7d: {fmt(lean_delta)}")
    lines.append(f"current calories: {fmt(current_calories)}")
    lines.append(f"protein: {fmt(row['recent_protein'])}")
    lines.append(f"carbs: {fmt(row['recent_carbs'])}")
    lines.append(f"fat: {fmt(row['recent_fat_g'])}")
    lines.append(f"RHR: {fmt(row['recent_rhr'])} (delta {fmt(rhr_delta)})")
    lines.append(f"HRV: {fmt(row['recent_hrv'])} (delta {fmt(hrv_delta)})")
    lines.append(f"workouts (7d): {fmt(row['recent_workouts'])}")
    lines.append("")
    lines.append("Strength Context")
    lines.append("----------------")
    lines.append(f"lifts trending up: {strength_up}")
    lines.append(f"lifts flat: {strength_flat}")
    lines.append(f"lifts trending down: {strength_down}")
    lines.append("")
    lines.append("Recommendation")
    lines.append("--------------")
    lines.append(f"Action: {recommendation}")
    lines.append(f"Calorie adjustment: {calorie_change:+d} kcal/day")
    lines.append(macro_hint)
    lines.append("")
    lines.append("Why")
    lines.append("---")
    for item in rationale:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("Coach's View")
    lines.append("------------")
    lines.append("For your current goal, the right calorie move is the one that keeps fat loss going while stabilizing lean mass, keeping recovery under control, and preserving upward strength trends.")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")

    print(f"Saved: {OUT_PATH}")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()
