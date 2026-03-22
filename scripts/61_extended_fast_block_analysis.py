from __future__ import annotations

from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_CSV = REPORTS_DIR / "extended_fast_block_analysis.csv"
OUT_TXT = REPORTS_DIR / "extended_fast_block_analysis.txt"


def main() -> None:
    con = duckdb.connect(str(DB_PATH))

    df = con.execute("""
        WITH ef_days AS (
            SELECT
                i.date,
                i.fasting_state,
                i.fasting_hours,
                LAG(i.date) OVER (ORDER BY i.date) AS prev_date
            FROM clean.interventions_daily i
            WHERE i.fasting_state = 'extended_fast'
        ),
        flagged AS (
            SELECT
                date,
                fasting_hours,
                CASE
                    WHEN prev_date IS NULL THEN 1
                    WHEN date - prev_date = 1 THEN 0
                    ELSE 1
                END AS new_block
            FROM ef_days
        ),
        blocks AS (
            SELECT
                date,
                fasting_hours,
                SUM(new_block) OVER (
                    ORDER BY date
                    ROWS UNBOUNDED PRECEDING
                ) AS block_id
            FROM flagged
        ),
        block_ranges AS (
            SELECT
                block_id,
                MIN(date) AS start_date,
                MAX(date) AS end_date,
                COUNT(*) AS day_count,
                MAX(fasting_hours) AS block_hours
            FROM blocks
            GROUP BY block_id
        ),
        joined AS (
            SELECT
                br.block_id,
                br.start_date,
                br.end_date,
                br.day_count,
                br.block_hours,

                s.weight_kg AS start_weight_kg,
                e.weight_kg AS end_weight_kg,
                e.weight_kg - s.weight_kg AS weight_change_kg,

                s.fat_mass_kg AS start_fat_mass_kg,
                e.fat_mass_kg AS end_fat_mass_kg,
                e.fat_mass_kg - s.fat_mass_kg AS fat_mass_change_kg,

                s.lean_mass_kg AS start_lean_mass_kg,
                e.lean_mass_kg AS end_lean_mass_kg,
                e.lean_mass_kg - s.lean_mass_kg AS lean_mass_change_kg,

                (
                    SELECT AVG(dm.steps)
                    FROM analytics.daily_metrics dm
                    WHERE dm.date BETWEEN br.start_date AND br.end_date
                ) AS avg_steps,

                (
                    SELECT AVG(dm.sleep_hours)
                    FROM analytics.daily_metrics dm
                    WHERE dm.date BETWEEN br.start_date AND br.end_date
                ) AS avg_sleep_hours,

                (
                    SELECT AVG(dm.resting_hr)
                    FROM analytics.daily_metrics dm
                    WHERE dm.date BETWEEN br.start_date AND br.end_date
                ) AS avg_resting_hr,

                (
                    SELECT AVG(dm.hrv)
                    FROM analytics.daily_metrics dm
                    WHERE dm.date BETWEEN br.start_date AND br.end_date
                ) AS avg_hrv,

                (
                    SELECT AVG(dm.calories)
                    FROM analytics.daily_metrics dm
                    WHERE dm.date BETWEEN br.start_date AND br.end_date
                ) AS avg_calories,

                (
                    SELECT AVG(dm.protein_g)
                    FROM analytics.daily_metrics dm
                    WHERE dm.date BETWEEN br.start_date AND br.end_date
                ) AS avg_protein_g,

                (
                    SELECT AVG(dm.hunger_score)
                    FROM analytics.daily_metrics dm
                    WHERE dm.date BETWEEN br.start_date AND br.end_date
                ) AS avg_hunger_score
            FROM block_ranges br
            LEFT JOIN analytics.daily_metrics s
                ON br.start_date = s.date
            LEFT JOIN analytics.daily_metrics e
                ON br.end_date = e.date
        )
        SELECT
            *,
            CASE
                WHEN block_hours IS NOT NULL AND block_hours > 0
                     AND weight_change_kg IS NOT NULL
                THEN weight_change_kg / block_hours
                ELSE NULL
            END AS weight_change_per_hour,

            CASE
                WHEN block_hours IS NOT NULL AND block_hours > 0
                     AND fat_mass_change_kg IS NOT NULL
                THEN fat_mass_change_kg / block_hours
                ELSE NULL
            END AS fat_mass_change_per_hour
        FROM joined
        ORDER BY start_date
    """).fetchdf()

    con.close()

    df.to_csv(OUT_CSV, index=False)

    lines: list[str] = []
    lines.append("Extended Fast Block Analysis")
    lines.append("============================")
    lines.append("")

    if df.empty:
        lines.append("No extended_fast blocks found.")
    else:
        lines.append("Block Summary")
        lines.append("-------------")
        for _, row in df.iterrows():
            lines.append(
                f"block {int(row['block_id'])}: "
                f"{row['start_date']}→{row['end_date']} | "
                f"days={int(row['day_count'])} | "
                f"hours={fmt(row['block_hours'])} | "
                f"weight_change={fmt(row['weight_change_kg'])} | "
                f"fat_change={fmt(row['fat_mass_change_kg'])} | "
                f"lean_change={fmt(row['lean_mass_change_kg'])}"
            )

        lines.append("")
        lines.append("Detailed Metrics")
        lines.append("---------------")
        for _, row in df.iterrows():
            lines.append(
                f"block {int(row['block_id'])}: "
                f"avg_steps={fmt(row['avg_steps'])}, "
                f"avg_sleep={fmt(row['avg_sleep_hours'])}, "
                f"avg_rhr={fmt(row['avg_resting_hr'])}, "
                f"avg_hrv={fmt(row['avg_hrv'])}, "
                f"avg_calories={fmt(row['avg_calories'])}, "
                f"avg_protein={fmt(row['avg_protein_g'])}, "
                f"avg_hunger={fmt(row['avg_hunger_score'])}, "
                f"weight_per_hour={fmt(row['weight_change_per_hour'])}, "
                f"fat_per_hour={fmt(row['fat_mass_change_per_hour'])}"
            )

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")

    print(f"Saved: {OUT_CSV}")
    print(f"Saved: {OUT_TXT}")
    print()
    print("\n".join(lines))


def fmt(value) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{float(value):.3f}"


if __name__ == "__main__":
    main()