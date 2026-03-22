from __future__ import annotations

from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_CSV = REPORTS_DIR / "fasting_effectiveness_analysis.csv"
OUT_TXT = REPORTS_DIR / "fasting_effectiveness_analysis.txt"


def main() -> None:
    con = duckdb.connect(str(DB_PATH))

    df = con.execute("""
    WITH base AS (
        SELECT
            dm.date,
            i.fasting_state,
            i.fasting_hours,
            dm.weight_kg,
            dm.fat_mass_kg,
            dm.lean_mass_kg,
            dm.steps,
            dm.sleep_hours,
            dm.resting_hr,
            dm.hrv,
            dm.calories,
            dm.protein_g,
            dm.hunger_score,
            dm.mounjaro_mg
        FROM analytics.daily_metrics dm
        LEFT JOIN clean.interventions_daily i
            ON dm.date = i.date
        WHERE i.fasting_state IS NOT NULL
    )
    SELECT
        fasting_state,
        COUNT(*) AS row_count,

        AVG(fasting_hours) AS avg_fasting_hours,

        AVG(weight_kg) AS avg_weight_kg,
        AVG(fat_mass_kg) AS avg_fat_mass_kg,
        AVG(lean_mass_kg) AS avg_lean_mass_kg,

        AVG(steps) AS avg_steps,
        AVG(sleep_hours) AS avg_sleep_hours,
        AVG(resting_hr) AS avg_resting_hr,
        AVG(hrv) AS avg_hrv,

        AVG(calories) AS avg_calories,
        AVG(protein_g) AS avg_protein_g,

        AVG(hunger_score) AS avg_hunger_score,
        AVG(mounjaro_mg) AS avg_mounjaro_mg,

        MIN(date) AS earliest_date,
        MAX(date) AS latest_date
    FROM base
    GROUP BY fasting_state
    ORDER BY row_count DESC, fasting_state
""").fetchdf()

    # Add coverage counts for each state
    coverage_df = con.execute("""
        WITH base AS (
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
                dm.calories,
                dm.protein_g,
                dm.hunger_score
            FROM analytics.daily_metrics dm
            LEFT JOIN clean.interventions_daily i
                ON dm.date = i.date
            WHERE i.fasting_state IS NOT NULL
        )
        SELECT
            fasting_state,
            COUNT(weight_kg) AS weight_days,
            COUNT(fat_mass_kg) AS fat_mass_days,
            COUNT(lean_mass_kg) AS lean_mass_days,
            COUNT(steps) AS step_days,
            COUNT(sleep_hours) AS sleep_days,
            COUNT(resting_hr) AS resting_hr_days,
            COUNT(hrv) AS hrv_days,
            COUNT(calories) AS calorie_days,
            COUNT(protein_g) AS protein_days,
            COUNT(hunger_score) AS hunger_days
        FROM base
        GROUP BY fasting_state
    """).fetchdf()

    con.close()

    if not df.empty and not coverage_df.empty:
        df = df.merge(coverage_df, on="fasting_state", how="left")

    df.to_csv(OUT_CSV, index=False)

    lines: list[str] = []
    lines.append("Fasting Effectiveness Analysis")
    lines.append("==============================")
    lines.append("")

    if df.empty:
        lines.append("No fasting/intervention data found.")
    else:
        lines.append("States analyzed")
        lines.append("--------------")
        for _, row in df.iterrows():
            lines.append(
                f"{row['fasting_state']}: "
                f"rows={int(row['row_count'])}, "
                f"range={row['earliest_date']}→{row['latest_date']}"
            )

        lines.append("")
        lines.append("Key Metrics by State")
        lines.append("--------------------")
        for _, row in df.iterrows():
            lines.append(
                f"{row['fasting_state']}: "
                f"avg_hours={fmt(row['avg_fasting_hours'])}, "
                f"avg_weight={fmt(row['avg_weight_kg'])}, "
                f"avg_fat_mass={fmt(row['avg_fat_mass_kg'])}, "
                f"avg_lean_mass={fmt(row['avg_lean_mass_kg'])}, "
                f"avg_steps={fmt(row['avg_steps'])}, "
                f"avg_sleep={fmt(row['avg_sleep_hours'])}, "
                f"avg_rhr={fmt(row['avg_resting_hr'])}, "
                f"avg_hrv={fmt(row['avg_hrv'])}, "
                f"avg_calories={fmt(row['avg_calories'])}, "
                f"avg_protein={fmt(row['avg_protein_g'])}, "
                f"avg_hunger={fmt(row['avg_hunger_score'])}"
            )

        lines.append("")
        lines.append("Coverage")
        lines.append("--------")
        for _, row in df.iterrows():
            lines.append(
                f"{row['fasting_state']}: "
                f"weight_days={int0(row.get('weight_days'))}, "
                f"fat_mass_days={int0(row.get('fat_mass_days'))}, "
                f"lean_mass_days={int0(row.get('lean_mass_days'))}, "
                f"step_days={int0(row.get('step_days'))}, "
                f"sleep_days={int0(row.get('sleep_days'))}, "
                f"rhr_days={int0(row.get('resting_hr_days'))}, "
                f"hrv_days={int0(row.get('hrv_days'))}, "
                f"calorie_days={int0(row.get('calorie_days'))}, "
                f"protein_days={int0(row.get('protein_days'))}, "
                f"hunger_days={int0(row.get('hunger_days'))}"
            )

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")

    print(f"Saved: {OUT_CSV}")
    print(f"Saved: {OUT_TXT}")
    print()
    print("\n".join(lines))


def fmt(value) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{float(value):.2f}"


def int0(value) -> int:
    if pd.isna(value):
        return 0
    return int(value)


if __name__ == "__main__":
    main()