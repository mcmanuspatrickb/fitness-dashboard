from __future__ import annotations

from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = REPORTS_DIR / "should_i_fast.txt"


def fmt(x) -> str:
    if pd.isna(x):
        return "N/A"
    return f"{float(x):.2f}"


def main() -> None:
    con = duckdb.connect(str(DB_PATH))

    df = con.execute("""
        WITH last_28 AS (
            SELECT
                dm.date,
                dm.weight_kg,
                dm.fat_mass_kg,
                dm.lean_mass_kg,
                dm.calories,
                dm.protein_g,
                f.steps,
                f.sleep_hours,
                f.resting_hr,
                f.hrv
            FROM analytics.daily_metrics dm
            LEFT JOIN clean.fitbit_daily f
                ON dm.date = f.date
            WHERE dm.date >= CURRENT_DATE - 28
            ORDER BY dm.date
        ),
        recent_14 AS (
            SELECT * FROM last_28 WHERE date >= CURRENT_DATE - 14
        ),
        prior_14 AS (
            SELECT * FROM last_28
            WHERE date < CURRENT_DATE - 14
              AND date >= CURRENT_DATE - 28
        ),
        training_recent AS (
            SELECT
                COUNT(*) AS workout_days_14,
                SUM(workout_count) AS workouts_14,
                AVG(total_volume) AS avg_training_volume_14
            FROM clean.training_summary
            WHERE date >= CURRENT_DATE - 14
        ),
        training_prior AS (
            SELECT
                COUNT(*) AS workout_days_prev14,
                SUM(workout_count) AS workouts_prev14,
                AVG(total_volume) AS avg_training_volume_prev14
            FROM clean.training_summary
            WHERE date < CURRENT_DATE - 14
              AND date >= CURRENT_DATE - 28
        )
        SELECT
            (SELECT AVG(weight_kg) FROM recent_14) AS recent_weight,
            (SELECT AVG(weight_kg) FROM prior_14) AS prior_weight,

            (SELECT AVG(fat_mass_kg) FROM recent_14) AS recent_fat,
            (SELECT AVG(fat_mass_kg) FROM prior_14) AS prior_fat,

            (SELECT AVG(lean_mass_kg) FROM recent_14) AS recent_lean,
            (SELECT AVG(lean_mass_kg) FROM prior_14) AS prior_lean,

            (SELECT AVG(calories) FROM recent_14) AS recent_calories,
            (SELECT AVG(protein_g) FROM recent_14) AS recent_protein,

            (SELECT AVG(steps) FROM recent_14) AS recent_steps,
            (SELECT AVG(sleep_hours) FROM recent_14) AS recent_sleep,
            (SELECT AVG(resting_hr) FROM recent_14) AS recent_rhr,
            (SELECT AVG(hrv) FROM recent_14) AS recent_hrv,

            (SELECT AVG(resting_hr) FROM prior_14) AS prior_rhr,
            (SELECT AVG(hrv) FROM prior_14) AS prior_hrv,

            tr.workout_days_14,
            tr.workouts_14,
            tr.avg_training_volume_14,

            tp.workout_days_prev14,
            tp.workouts_prev14,
            tp.avg_training_volume_prev14
        FROM training_recent tr
        CROSS JOIN training_prior tp
    """).fetchdf()

    con.close()

    if df.empty:
        print("No data found.")
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

    reasons_against = []
    reasons_for = []

    plateau_weight = pd.notna(weight_delta) and abs(weight_delta) < 0.30
    plateau_fat = pd.notna(fat_delta) and abs(fat_delta) < 0.20

    if plateau_weight and plateau_fat:
        reasons_for.append("Weight and fat mass both look plateaued over the last 14 days.")

    if pd.notna(lean_delta) and lean_delta < -0.30:
        reasons_against.append("Lean mass is drifting down, so fasting now may work against your strength/recomp goal.")

    if pd.notna(row["recent_calories"]) and row["recent_calories"] < 1600:
        reasons_against.append("Calories are already low; you are likely under-fueled rather than truly stuck.")

    if pd.isna(row["recent_protein"]) or row["recent_protein"] < 100:
        reasons_against.append("Protein is missing or low; fix protein consistency before using fasting as a tool.")

    if pd.notna(rhr_delta) and rhr_delta > 3:
        reasons_against.append("Resting HR is elevated versus the prior period, suggesting recovery stress.")

    if pd.notna(row["recent_sleep"]) and row["recent_sleep"] < 6.5:
        reasons_against.append("Sleep is not strong enough for an aggressive intervention.")

    if pd.notna(row["workouts_14"]) and row["workouts_14"] >= 4:
        reasons_against.append("Training is active enough that a fast may interfere with strength progress.")

    if pd.notna(row["recent_rhr"]) and row["recent_rhr"] <= 72:
        reasons_for.append("Resting HR looks reasonably calm.")
    if pd.notna(row["recent_sleep"]) and row["recent_sleep"] >= 7:
        reasons_for.append("Sleep looks supportive.")
    if pd.notna(row["recent_protein"]) and row["recent_protein"] >= 110:
        reasons_for.append("Protein looks adequate for a well-controlled prep state.")

    if reasons_against:
        decision = "NO — do not start a fast right now."
        focus = "Stay in recomposition mode: fuel training, fix recovery, and reassess later."
    elif plateau_weight and plateau_fat:
        decision = "MAYBE — a short fast could be reasonable, but only if strength is not the priority this week."
        focus = "You appear plateaued, but keep the intervention small and deliberate."
    else:
        decision = "NO — there is no strong case for fasting right now."
        focus = "You are better served by steady nutrition and training consistency."

    lines = []
    lines.append("Should I Fast?")
    lines.append("==============")
    lines.append("")
    lines.append("14-Day Trend Check")
    lines.append("------------------")
    lines.append(f"weight change: {fmt(weight_delta)}")
    lines.append(f"fat mass change: {fmt(fat_delta)}")
    lines.append(f"lean mass change: {fmt(lean_delta)}")
    lines.append("")
    lines.append("Readiness / Recovery")
    lines.append("--------------------")
    lines.append(f"calories: {fmt(row['recent_calories'])}")
    lines.append(f"protein: {fmt(row['recent_protein'])}")
    lines.append(f"steps: {fmt(row['recent_steps'])}")
    lines.append(f"sleep: {fmt(row['recent_sleep'])}")
    lines.append(f"RHR: {fmt(row['recent_rhr'])}")
    lines.append(f"HRV: {fmt(row['recent_hrv'])}")
    lines.append(f"RHR delta vs prior 14d: {fmt(rhr_delta)}")
    lines.append(f"HRV delta vs prior 14d: {fmt(hrv_delta)}")
    lines.append("")
    lines.append("Training")
    lines.append("--------")
    lines.append(f"workout days (14d): {fmt(row['workout_days_14'])}")
    lines.append(f"workouts (14d): {fmt(row['workouts_14'])}")
    lines.append(f"avg training volume (14d): {fmt(row['avg_training_volume_14'])}")
    lines.append("")
    lines.append("Decision")
    lines.append("--------")
    lines.append(decision)
    lines.append(focus)
    lines.append("")
    lines.append("Reasons For")
    lines.append("-----------")
    if reasons_for:
        lines.extend(f"- {x}" for x in reasons_for)
    else:
        lines.append("- none")
    lines.append("")
    lines.append("Reasons Against")
    lines.append("---------------")
    if reasons_against:
        lines.extend(f"- {x}" for x in reasons_against)
    else:
        lines.append("- none")
    lines.append("")
    lines.append("Coach's Take")
    lines.append("------------")
    lines.append("Because your current main goal is strength + slow fat loss, fasting should be a secondary tool, not the default move.")
    lines.append("Use fasting only when you are genuinely plateaued and your recovery/nutrition are solid.")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {OUT_PATH}")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()