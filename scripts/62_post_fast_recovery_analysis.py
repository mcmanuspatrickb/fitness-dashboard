from __future__ import annotations

from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_CSV = REPORTS_DIR / "post_fast_recovery_analysis.csv"
OUT_TXT = REPORTS_DIR / "post_fast_recovery_analysis.txt"


def main() -> None:
    con = duckdb.connect(str(DB_PATH))

    df = con.execute("""
        WITH ef_days AS (
            SELECT
                date,
                LAG(date) OVER (ORDER BY date) AS prev_date
            FROM clean.interventions_daily
            WHERE fasting_state = 'extended_fast'
        ),
        flagged AS (
            SELECT
                date,
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
                MAX(date) AS end_date
            FROM blocks
            GROUP BY block_id
        ),

        joined AS (
            SELECT
                br.block_id,
                br.start_date,
                br.end_date,

                -- END OF FAST
                end_dm.weight_kg AS end_weight,
                end_dm.fat_mass_kg AS end_fat,
                end_dm.lean_mass_kg AS end_lean,

                -- +7 DAYS
                dm7.weight_kg AS weight_7d,
                dm7.fat_mass_kg AS fat_7d,
                dm7.lean_mass_kg AS lean_7d,

                -- +14 DAYS
                dm14.weight_kg AS weight_14d,
                dm14.fat_mass_kg AS fat_14d,
                dm14.lean_mass_kg AS lean_14d,

                -- RECOVERY METRICS (0–7 days)
                (
                    SELECT AVG(calories)
                    FROM analytics.daily_metrics dm
                    WHERE dm.date BETWEEN br.end_date + 1 AND br.end_date + 7
                ) AS avg_calories_7d,

                (
                    SELECT AVG(steps)
                    FROM analytics.daily_metrics dm
                    WHERE dm.date BETWEEN br.end_date + 1 AND br.end_date + 7
                ) AS avg_steps_7d,

                (
                    SELECT AVG(sleep_hours)
                    FROM analytics.daily_metrics dm
                    WHERE dm.date BETWEEN br.end_date + 1 AND br.end_date + 7
                ) AS avg_sleep_7d,

                (
                    SELECT AVG(resting_hr)
                    FROM analytics.daily_metrics dm
                    WHERE dm.date BETWEEN br.end_date + 1 AND br.end_date + 7
                ) AS avg_rhr_7d,

                (
                    SELECT AVG(hrv)
                    FROM analytics.daily_metrics dm
                    WHERE dm.date BETWEEN br.end_date + 1 AND br.end_date + 7
                ) AS avg_hrv_7d

            FROM block_ranges br
            LEFT JOIN analytics.daily_metrics end_dm
                ON br.end_date = end_dm.date
            LEFT JOIN analytics.daily_metrics dm7
                ON dm7.date = br.end_date + 7
            LEFT JOIN analytics.daily_metrics dm14
                ON dm14.date = br.end_date + 14
        )

        SELECT
            *,
            weight_7d - end_weight AS weight_rebound_7d,
            weight_14d - end_weight AS weight_rebound_14d,

            fat_7d - end_fat AS fat_rebound_7d,
            fat_14d - end_fat AS fat_rebound_14d,

            lean_7d - end_lean AS lean_rebound_7d,
            lean_14d - end_lean AS lean_rebound_14d
        FROM joined
        ORDER BY start_date
    """).fetchdf()

    con.close()

    df.to_csv(OUT_CSV, index=False)

    # TEXT SUMMARY
    lines: list[str] = []
    lines.append("Post-Fast Recovery Analysis")
    lines.append("============================")
    lines.append("")

    if df.empty:
        lines.append("No extended fast blocks found.")
    else:
        for _, row in df.iterrows():
            lines.append(
                f"block {int(row['block_id'])}: "
                f"{row['start_date']}→{row['end_date']}"
            )
            lines.append(
                f"  7d: weight={fmt(row['weight_rebound_7d'])}, "
                f"fat={fmt(row['fat_rebound_7d'])}, "
                f"lean={fmt(row['lean_rebound_7d'])}"
            )
            lines.append(
                f" 14d: weight={fmt(row['weight_rebound_14d'])}, "
                f"fat={fmt(row['fat_rebound_14d'])}, "
                f"lean={fmt(row['lean_rebound_14d'])}"
            )
            lines.append(
                f"  recovery: calories={fmt(row['avg_calories_7d'])}, "
                f"steps={fmt(row['avg_steps_7d'])}, "
                f"sleep={fmt(row['avg_sleep_7d'])}, "
                f"rhr={fmt(row['avg_rhr_7d'])}, "
                f"hrv={fmt(row['avg_hrv_7d'])}"
            )
            lines.append("")

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")

    print(f"Saved: {OUT_CSV}")
    print(f"Saved: {OUT_TXT}")
    print()
    print("\n".join(lines))


def fmt(value) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{float(value):.2f}"


if __name__ == "__main__":
    main()