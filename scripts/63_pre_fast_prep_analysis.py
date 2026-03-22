from __future__ import annotations

from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_CSV = REPORTS_DIR / "pre_fast_prep_analysis.csv"
OUT_TXT = REPORTS_DIR / "pre_fast_prep_analysis.txt"


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
                MAX(date) AS end_date,
                COUNT(*) AS fast_days
            FROM blocks
            GROUP BY block_id
        ),
        outcomes AS (
            SELECT
                br.block_id,
                br.start_date,
                br.end_date,
                br.fast_days,

                start_dm.weight_kg AS start_weight,
                end_dm.weight_kg AS end_weight,
                end_dm.weight_kg - start_dm.weight_kg AS fast_weight_change,

                start_dm.fat_mass_kg AS start_fat,
                end_dm.fat_mass_kg AS end_fat,
                end_dm.fat_mass_kg - start_dm.fat_mass_kg AS fast_fat_change,

                start_dm.lean_mass_kg AS start_lean,
                end_dm.lean_mass_kg AS end_lean,
                end_dm.lean_mass_kg - start_dm.lean_mass_kg AS fast_lean_change,

                dm7.weight_kg - end_dm.weight_kg AS rebound_weight_7d,
                dm7.fat_mass_kg - end_dm.fat_mass_kg AS rebound_fat_7d,
                dm7.lean_mass_kg - end_dm.lean_mass_kg AS rebound_lean_7d,

                dm14.weight_kg - end_dm.weight_kg AS rebound_weight_14d,
                dm14.fat_mass_kg - end_dm.fat_mass_kg AS rebound_fat_14d,
                dm14.lean_mass_kg - end_dm.lean_mass_kg AS rebound_lean_14d

            FROM block_ranges br
            LEFT JOIN analytics.daily_metrics start_dm
                ON start_dm.date = br.start_date
            LEFT JOIN analytics.daily_metrics end_dm
                ON end_dm.date = br.end_date
            LEFT JOIN analytics.daily_metrics dm7
                ON dm7.date = br.end_date + 7
            LEFT JOIN analytics.daily_metrics dm14
                ON dm14.date = br.end_date + 14
        ),
        prep AS (
            SELECT
                br.block_id,

                AVG(CASE WHEN dm.date BETWEEN br.start_date - 3 AND br.start_date - 1 THEN dm.calories END) AS prep3_avg_calories,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 3 AND br.start_date - 1 THEN dm.protein_g END) AS prep3_avg_protein,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 3 AND br.start_date - 1 THEN dm.steps END) AS prep3_avg_steps,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 3 AND br.start_date - 1 THEN dm.sleep_hours END) AS prep3_avg_sleep,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 3 AND br.start_date - 1 THEN dm.resting_hr END) AS prep3_avg_rhr,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 3 AND br.start_date - 1 THEN dm.hrv END) AS prep3_avg_hrv,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 3 AND br.start_date - 1 THEN dm.weight_kg END) AS prep3_avg_weight,

                AVG(CASE WHEN dm.date BETWEEN br.start_date - 5 AND br.start_date - 1 THEN dm.calories END) AS prep5_avg_calories,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 5 AND br.start_date - 1 THEN dm.protein_g END) AS prep5_avg_protein,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 5 AND br.start_date - 1 THEN dm.steps END) AS prep5_avg_steps,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 5 AND br.start_date - 1 THEN dm.sleep_hours END) AS prep5_avg_sleep,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 5 AND br.start_date - 1 THEN dm.resting_hr END) AS prep5_avg_rhr,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 5 AND br.start_date - 1 THEN dm.hrv END) AS prep5_avg_hrv,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 5 AND br.start_date - 1 THEN dm.weight_kg END) AS prep5_avg_weight,

                AVG(CASE WHEN dm.date BETWEEN br.start_date - 7 AND br.start_date - 1 THEN dm.calories END) AS prep7_avg_calories,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 7 AND br.start_date - 1 THEN dm.protein_g END) AS prep7_avg_protein,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 7 AND br.start_date - 1 THEN dm.steps END) AS prep7_avg_steps,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 7 AND br.start_date - 1 THEN dm.sleep_hours END) AS prep7_avg_sleep,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 7 AND br.start_date - 1 THEN dm.resting_hr END) AS prep7_avg_rhr,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 7 AND br.start_date - 1 THEN dm.hrv END) AS prep7_avg_hrv,
                AVG(CASE WHEN dm.date BETWEEN br.start_date - 7 AND br.start_date - 1 THEN dm.weight_kg END) AS prep7_avg_weight

            FROM block_ranges br
            LEFT JOIN analytics.daily_metrics dm
                ON dm.date BETWEEN br.start_date - 7 AND br.start_date - 1
            GROUP BY br.block_id
        )
        SELECT
            o.*,
            p.*,

            CASE
                WHEN fast_weight_change IS NOT NULL AND fast_weight_change != 0
                     AND fast_fat_change IS NOT NULL
                THEN ABS(fast_fat_change) / ABS(fast_weight_change)
                ELSE NULL
            END AS fat_loss_share_of_weight_loss,

            CASE
                WHEN fast_lean_change IS NOT NULL
                THEN -1 * fast_lean_change
                ELSE NULL
            END AS lean_loss_magnitude

        FROM outcomes o
        LEFT JOIN prep p
            ON o.block_id = p.block_id
        ORDER BY o.start_date
    """).fetchdf()

    con.close()

    df.to_csv(OUT_CSV, index=False)

    lines: list[str] = []
    lines.append("Pre-Fast Prep Analysis")
    lines.append("======================")
    lines.append("")

    if df.empty:
        lines.append("No extended_fast blocks found.")
    else:
        lines.append("Block Prep Summary")
        lines.append("------------------")
        for _, row in df.iterrows():
            lines.append(
                f"block {int(row['block_id'])}: "
                f"{row['start_date']}→{row['end_date']} | "
                f"days={int(row['fast_days'])}"
            )
            lines.append(
                f"  prep3: calories={fmt(row['prep3_avg_calories'])}, "
                f"protein={fmt(row['prep3_avg_protein'])}, "
                f"steps={fmt(row['prep3_avg_steps'])}, "
                f"sleep={fmt(row['prep3_avg_sleep'])}, "
                f"rhr={fmt(row['prep3_avg_rhr'])}, "
                f"hrv={fmt(row['prep3_avg_hrv'])}"
            )
            lines.append(
                f"  prep5: calories={fmt(row['prep5_avg_calories'])}, "
                f"protein={fmt(row['prep5_avg_protein'])}, "
                f"steps={fmt(row['prep5_avg_steps'])}, "
                f"sleep={fmt(row['prep5_avg_sleep'])}, "
                f"rhr={fmt(row['prep5_avg_rhr'])}, "
                f"hrv={fmt(row['prep5_avg_hrv'])}"
            )
            lines.append(
                f"  prep7: calories={fmt(row['prep7_avg_calories'])}, "
                f"protein={fmt(row['prep7_avg_protein'])}, "
                f"steps={fmt(row['prep7_avg_steps'])}, "
                f"sleep={fmt(row['prep7_avg_sleep'])}, "
                f"rhr={fmt(row['prep7_avg_rhr'])}, "
                f"hrv={fmt(row['prep7_avg_hrv'])}"
            )
            lines.append(
                f"  fast outcome: weight={fmt(row['fast_weight_change'])}, "
                f"fat={fmt(row['fast_fat_change'])}, "
                f"lean={fmt(row['fast_lean_change'])}, "
                f"fat_share={fmt(row['fat_loss_share_of_weight_loss'])}"
            )
            lines.append(
                f"  rebound: 7d weight={fmt(row['rebound_weight_7d'])}, "
                f"7d fat={fmt(row['rebound_fat_7d'])}, "
                f"14d weight={fmt(row['rebound_weight_14d'])}, "
                f"14d fat={fmt(row['rebound_fat_14d'])}"
            )
            lines.append("")

        lines.append("High-Level Notes")
        lines.append("----------------")
        lines.append("Look for blocks where:")
        lines.append("- prep protein is higher")
        lines.append("- prep calories are moderate, not binge-like")
        lines.append("- prep sleep is stronger")
        lines.append("- fast lean loss is smaller")
        lines.append("- rebound fat gain is smaller")

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