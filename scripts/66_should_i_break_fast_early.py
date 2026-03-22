from __future__ import annotations

from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = REPORTS_DIR / "should_i_break_fast_early.txt"


def fmt(x):
    if pd.isna(x):
        return "N/A"
    return f"{float(x):.2f}"


def main():
    con = duckdb.connect(str(DB_PATH))

    df = con.execute("""
        WITH recent AS (
            SELECT
                dm.date,
                i.fasting_state,
                dm.weight_kg,
                dm.fat_mass_kg,
                dm.lean_mass_kg,
                dm.steps,
                dm.sleep_hours,
                dm.resting_hr,
                dm.hrv,
                dm.hunger_score,
                dm.calories,
                dm.protein_g,
                ROW_NUMBER() OVER (ORDER BY dm.date DESC) AS rn_desc
            FROM analytics.daily_metrics dm
            LEFT JOIN clean.interventions_daily i
                ON dm.date = i.date
            WHERE dm.date >= CURRENT_DATE - 14
            ORDER BY dm.date DESC
        ),
        recent7 AS (
            SELECT * FROM recent WHERE rn_desc <= 7
        ),
        previous7 AS (
            SELECT * FROM recent WHERE rn_desc > 7 AND rn_desc <= 14
        )
        SELECT
            (SELECT MAX(date) FROM recent7) AS latest_date,
            (SELECT COUNT(*) FROM recent7) AS recent_days,

            (SELECT AVG(weight_kg) FROM recent7) AS recent_weight,
            (SELECT AVG(weight_kg) FROM previous7) AS prev_weight,

            (SELECT AVG(fat_mass_kg) FROM recent7) AS recent_fat,
            (SELECT AVG(fat_mass_kg) FROM previous7) AS prev_fat,

            (SELECT AVG(lean_mass_kg) FROM recent7) AS recent_lean,
            (SELECT AVG(lean_mass_kg) FROM previous7) AS prev_lean,

            (SELECT AVG(steps) FROM recent7) AS recent_steps,
            (SELECT AVG(sleep_hours) FROM recent7) AS recent_sleep,
            (SELECT AVG(resting_hr) FROM recent7) AS recent_rhr,
            (SELECT AVG(hrv) FROM recent7) AS recent_hrv,
            (SELECT AVG(hunger_score) FROM recent7) AS recent_hunger,
            (SELECT AVG(calories) FROM recent7) AS recent_calories,
            (SELECT AVG(protein_g) FROM recent7) AS recent_protein,

            (SELECT AVG(resting_hr) FROM previous7) AS prev_rhr,
            (SELECT AVG(hrv) FROM previous7) AS prev_hrv,
            (SELECT AVG(sleep_hours) FROM previous7) AS prev_sleep,
            (SELECT AVG(hunger_score) FROM previous7) AS prev_hunger
    """).fetchdf()

    con.close()

    if df.empty:
        print("No recent data found.")
        return

    row = df.iloc[0]

    weight_change = (
        row["recent_weight"] - row["prev_weight"]
        if pd.notna(row["recent_weight"]) and pd.notna(row["prev_weight"])
        else pd.NA
    )
    fat_change = (
        row["recent_fat"] - row["prev_fat"]
        if pd.notna(row["recent_fat"]) and pd.notna(row["prev_fat"])
        else pd.NA
    )
    lean_change = (
        row["recent_lean"] - row["prev_lean"]
        if pd.notna(row["recent_lean"]) and pd.notna(row["prev_lean"])
        else pd.NA
    )
    rhr_change = (
        row["recent_rhr"] - row["prev_rhr"]
        if pd.notna(row["recent_rhr"]) and pd.notna(row["prev_rhr"])
        else pd.NA
    )
    hrv_change = (
        row["recent_hrv"] - row["prev_hrv"]
        if pd.notna(row["recent_hrv"]) and pd.notna(row["prev_hrv"])
        else pd.NA
    )
    sleep_change = (
        row["recent_sleep"] - row["prev_sleep"]
        if pd.notna(row["recent_sleep"]) and pd.notna(row["prev_sleep"])
        else pd.NA
    )
    hunger_change = (
        row["recent_hunger"] - row["prev_hunger"]
        if pd.notna(row["recent_hunger"]) and pd.notna(row["prev_hunger"])
        else pd.NA
    )

    flags = []

    # Body comp risk
    if pd.notna(lean_change) and lean_change < -1.5:
        flags.append("lean_mass_drop")

    # Recovery / stress signals
    if pd.notna(rhr_change) and rhr_change > 3:
        flags.append("rhr_up")
    if pd.notna(hrv_change) and hrv_change < -3:
        flags.append("hrv_down")
    if pd.notna(sleep_change) and sleep_change < -1:
        flags.append("sleep_down")
    if pd.notna(hunger_change) and hunger_change > 1.5:
        flags.append("hunger_up")

    # Plateau-ish condition
    if pd.notna(weight_change) and abs(weight_change) < 0.2:
        flags.append("weight_plateau")

    # Decision
    if "lean_mass_drop" in flags and ("rhr_up" in flags or "hrv_down" in flags):
        decision = "🔴 BREAK FAST EARLY"
    elif len(flags) >= 3:
        decision = "🟠 STRONGLY CONSIDER BREAKING"
    elif len(flags) >= 1:
        decision = "🟡 MONITOR CLOSELY"
    else:
        decision = "🟢 CONTINUE IF GOAL IS STILL APPROPRIATE"

    lines = []
    lines.append("Should I Break My Fast Early?")
    lines.append("=============================")
    lines.append("")
    lines.append(f"Latest date: {row['latest_date']}")
    lines.append("")
    lines.append("Recent 7-day vs Previous 7-day")
    lines.append("------------------------------")
    lines.append(f"weight change:    {fmt(weight_change)}")
    lines.append(f"fat mass change:  {fmt(fat_change)}")
    lines.append(f"lean mass change: {fmt(lean_change)}")
    lines.append(f"RHR change:       {fmt(rhr_change)}")
    lines.append(f"HRV change:       {fmt(hrv_change)}")
    lines.append(f"sleep change:     {fmt(sleep_change)}")
    lines.append(f"hunger change:    {fmt(hunger_change)}")
    lines.append("")
    lines.append("Current 7-day averages")
    lines.append("----------------------")
    lines.append(f"steps:    {fmt(row['recent_steps'])}")
    lines.append(f"sleep:    {fmt(row['recent_sleep'])}")
    lines.append(f"RHR:      {fmt(row['recent_rhr'])}")
    lines.append(f"HRV:      {fmt(row['recent_hrv'])}")
    lines.append(f"hunger:   {fmt(row['recent_hunger'])}")
    lines.append(f"calories: {fmt(row['recent_calories'])}")
    lines.append(f"protein:  {fmt(row['recent_protein'])}")
    lines.append("")
    lines.append("Flags")
    lines.append("-----")
    if flags:
        for flag in flags:
            lines.append(f"- {flag}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("Decision")
    lines.append("--------")
    lines.append(decision)
    lines.append("")
    lines.append("Interpretation")
    lines.append("--------------")
    lines.append("Break early if lean mass appears to be dropping meaningfully and recovery/stress markers are worsening.")
    lines.append("Monitor closely if you see plateau, rising hunger, worse sleep, or autonomic stress.")
    lines.append("Continue when body comp trend is favorable and recovery markers are stable.")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")

    print(f"Saved: {OUT_PATH}")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()