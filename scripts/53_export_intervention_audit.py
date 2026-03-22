from __future__ import annotations

from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

RAW_OUT = REPORTS_DIR / "intervention_audit_raw.csv"
CLEAN_OUT = REPORTS_DIR / "intervention_audit_clean.csv"
COUNTS_OUT = REPORTS_DIR / "intervention_audit_counts.csv"
RECENT_OUT = REPORTS_DIR / "intervention_audit_recent.csv"
TXT_OUT = REPORTS_DIR / "intervention_audit_summary.txt"


def main() -> None:
    con = duckdb.connect(str(DB_PATH))

    raw_df = con.execute("""
        SELECT
            date,
            fasting_state,
            fasting_hours,
            mounjaro_mg,
            hunger_score,
            notes,
            created_at
        FROM raw.interventions_daily
        ORDER BY date
    """).fetchdf()

    clean_df = con.execute("""
        SELECT
            date,
            fasting_state,
            fasting_hours,
            mounjaro_mg,
            hunger_score,
            notes
        FROM clean.interventions_daily
        ORDER BY date
    """).fetchdf()

    counts_df = con.execute("""
        SELECT
            COALESCE(fasting_state, '<<NULL>>') AS fasting_state,
            COUNT(*) AS row_count,
            MIN(date) AS earliest_date,
            MAX(date) AS latest_date,
            AVG(fasting_hours) AS avg_fasting_hours,
            MIN(fasting_hours) AS min_fasting_hours,
            MAX(fasting_hours) AS max_fasting_hours
        FROM clean.interventions_daily
        GROUP BY 1
        ORDER BY row_count DESC, fasting_state
    """).fetchdf()

    recent_df = con.execute("""
        SELECT
            date,
            fasting_state,
            fasting_hours,
            mounjaro_mg,
            hunger_score,
            notes
        FROM clean.interventions_daily
        ORDER BY date DESC
        LIMIT 60
    """).fetchdf()

    ef_blocks_df = con.execute("""
        WITH ef_days AS (
            SELECT
                date,
                fasting_state,
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
                SUM(new_block) OVER (ORDER BY date ROWS UNBOUNDED PRECEDING) AS block_id
            FROM flagged
        )
        SELECT
            block_id,
            MIN(date) AS start_date,
            MAX(date) AS end_date,
            COUNT(*) AS day_count,
            COUNT(*) * 24 AS implied_hours
        FROM blocks
        GROUP BY block_id
        ORDER BY start_date
    """).fetchdf()

    con.close()

    raw_df.to_csv(RAW_OUT, index=False)
    clean_df.to_csv(CLEAN_OUT, index=False)
    counts_df.to_csv(COUNTS_OUT, index=False)
    recent_df.to_csv(RECENT_OUT, index=False)

    lines: list[str] = []
    lines.append("Intervention Audit Summary")
    lines.append("==========================")
    lines.append("")
    lines.append("Coverage")
    lines.append("--------")
    lines.append(f"raw_rows: {len(raw_df)}")
    lines.append(f"clean_rows: {len(clean_df)}")

    if not clean_df.empty:
        lines.append(f"earliest_clean_date: {clean_df['date'].min()}")
        lines.append(f"latest_clean_date: {clean_df['date'].max()}")

    lines.append("")
    lines.append("Counts by Fasting State")
    lines.append("-----------------------")
    if counts_df.empty:
        lines.append("No intervention rows found.")
    else:
        for _, row in counts_df.iterrows():
            lines.append(
                f"{row['fasting_state']}: "
                f"rows={int(row['row_count'])}, "
                f"range={row['earliest_date']}→{row['latest_date']}, "
                f"avg_hours={row['avg_fasting_hours'] if pd.notna(row['avg_fasting_hours']) else 'N/A'}, "
                f"min_hours={row['min_fasting_hours'] if pd.notna(row['min_fasting_hours']) else 'N/A'}, "
                f"max_hours={row['max_fasting_hours'] if pd.notna(row['max_fasting_hours']) else 'N/A'}"
            )

    lines.append("")
    lines.append("Extended Fast Blocks")
    lines.append("--------------------")
    if ef_blocks_df.empty:
        lines.append("No extended_fast blocks found.")
    else:
        for _, row in ef_blocks_df.iterrows():
            lines.append(
                f"block {int(row['block_id'])}: "
                f"{row['start_date']}→{row['end_date']} | "
                f"days={int(row['day_count'])} | implied_hours={int(row['implied_hours'])}"
            )

    lines.append("")
    lines.append("Recent Intervention Preview")
    lines.append("---------------------------")
    if recent_df.empty:
        lines.append("No recent rows found.")
    else:
        preview_n = min(15, len(recent_df))
        for _, row in recent_df.head(preview_n).iterrows():
            lines.append(
                f"{row['date']} | state={row['fasting_state']} | "
                f"hours={row['fasting_hours'] if pd.notna(row['fasting_hours']) else 'N/A'} | "
                f"mounjaro={row['mounjaro_mg'] if pd.notna(row['mounjaro_mg']) else 'N/A'} | "
                f"hunger={row['hunger_score'] if pd.notna(row['hunger_score']) else 'N/A'} | "
                f"notes={row['notes'] if pd.notna(row['notes']) else ''}"
            )

    TXT_OUT.write_text("\n".join(lines), encoding="utf-8")

    print(f"Saved: {RAW_OUT}")
    print(f"Saved: {CLEAN_OUT}")
    print(f"Saved: {COUNTS_OUT}")
    print(f"Saved: {RECENT_OUT}")
    print(f"Saved: {TXT_OUT}")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()