from __future__ import annotations

from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_BLOCKS_CSV = REPORTS_DIR / "optimal_fast_playbook_blocks.csv"
OUT_SUMMARY_TXT = REPORTS_DIR / "optimal_fast_playbook.txt"


def fmt(value, digits: int = 2) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{float(value):.{digits}f}"


def classify_block(row: pd.Series) -> str:
    fat_share = row.get("fat_loss_share")
    rebound_fat_14d = row.get("rebound_fat_14d")
    lean_change = row.get("fast_lean_change")
    fast_days = row.get("fast_days")

    if pd.isna(fat_share) or pd.isna(lean_change) or pd.isna(fast_days):
        return "insufficient_data"

    # Short fasts are noisy and should not be graded aggressively
    if fast_days < 10:
        if fat_share >= 0.60 and lean_change >= -2.0:
            return "short_fast_promising"
        if fat_share >= 0.40:
            return "short_fast_mixed"
        return "short_fast_noisy"

    # Long fast grading
    rebound_ok = pd.isna(rebound_fat_14d) or rebound_fat_14d <= 1.0
    rebound_strong = pd.isna(rebound_fat_14d) or rebound_fat_14d <= 0.5

    if fat_share >= 0.75 and lean_change >= -1.0 and rebound_strong:
        return "elite"

    if fat_share >= 0.60 and lean_change >= -2.5 and rebound_ok:
        return "strong"

    if fat_share >= 0.40:
        return "mixed"

    return "poor"


def avg_of(df: pd.DataFrame, col: str) -> str:
    if col not in df.columns or df[col].dropna().empty:
        return "N/A"
    return fmt(df[col].mean())


def series_ids(df: pd.DataFrame) -> str:
    if df.empty:
        return "none"
    return ", ".join(str(int(x)) for x in df["block_id"])


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
                COUNT(*) AS fast_days,
                COUNT(*) * 24 AS fast_hours
            FROM blocks
            GROUP BY block_id
        ),
        body_outcomes AS (
            SELECT
                br.block_id,
                br.start_date,
                br.end_date,
                br.fast_days,
                br.fast_hours,

                s.weight_kg AS start_weight,
                e.weight_kg AS end_weight,
                e.weight_kg - s.weight_kg AS fast_weight_change,

                s.fat_mass_kg AS start_fat_mass,
                e.fat_mass_kg AS end_fat_mass,
                e.fat_mass_kg - s.fat_mass_kg AS fast_fat_change,

                s.lean_mass_kg AS start_lean_mass,
                e.lean_mass_kg AS end_lean_mass,
                e.lean_mass_kg - s.lean_mass_kg AS fast_lean_change,

                d7.weight_kg - e.weight_kg AS rebound_weight_7d,
                d14.weight_kg - e.weight_kg AS rebound_weight_14d,

                d7.fat_mass_kg - e.fat_mass_kg AS rebound_fat_7d,
                d14.fat_mass_kg - e.fat_mass_kg AS rebound_fat_14d,

                d7.lean_mass_kg - e.lean_mass_kg AS rebound_lean_7d,
                d14.lean_mass_kg - e.lean_mass_kg AS rebound_lean_14d
            FROM block_ranges br
            LEFT JOIN analytics.daily_metrics s
                ON s.date = br.start_date
            LEFT JOIN analytics.daily_metrics e
                ON e.date = br.end_date
            LEFT JOIN analytics.daily_metrics d7
                ON d7.date = br.end_date + 7
            LEFT JOIN analytics.daily_metrics d14
                ON d14.date = br.end_date + 14
        ),
        prep_nutrition AS (
            SELECT
                br.block_id,

                AVG(CASE WHEN n.date BETWEEN br.start_date - 3 AND br.start_date - 1 THEN n.calories END) AS prep3_calories,
                AVG(CASE WHEN n.date BETWEEN br.start_date - 3 AND br.start_date - 1 THEN n.protein_g END) AS prep3_protein,
                AVG(CASE WHEN n.date BETWEEN br.start_date - 3 AND br.start_date - 1 THEN n.carbs_g END) AS prep3_carbs,
                AVG(CASE WHEN n.date BETWEEN br.start_date - 3 AND br.start_date - 1 THEN n.fat_g END) AS prep3_fat,

                AVG(CASE WHEN n.date BETWEEN br.start_date - 5 AND br.start_date - 1 THEN n.calories END) AS prep5_calories,
                AVG(CASE WHEN n.date BETWEEN br.start_date - 5 AND br.start_date - 1 THEN n.protein_g END) AS prep5_protein,
                AVG(CASE WHEN n.date BETWEEN br.start_date - 5 AND br.start_date - 1 THEN n.carbs_g END) AS prep5_carbs,
                AVG(CASE WHEN n.date BETWEEN br.start_date - 5 AND br.start_date - 1 THEN n.fat_g END) AS prep5_fat,

                AVG(CASE WHEN n.date BETWEEN br.start_date - 7 AND br.start_date - 1 THEN n.calories END) AS prep7_calories,
                AVG(CASE WHEN n.date BETWEEN br.start_date - 7 AND br.start_date - 1 THEN n.protein_g END) AS prep7_protein,
                AVG(CASE WHEN n.date BETWEEN br.start_date - 7 AND br.start_date - 1 THEN n.carbs_g END) AS prep7_carbs,
                AVG(CASE WHEN n.date BETWEEN br.start_date - 7 AND br.start_date - 1 THEN n.fat_g END) AS prep7_fat
            FROM block_ranges br
            LEFT JOIN clean.nutrition_daily n
                ON n.date BETWEEN br.start_date - 7 AND br.start_date - 1
            GROUP BY br.block_id
        ),
        prep_fitbit AS (
            SELECT
                br.block_id,

                AVG(CASE WHEN f.date BETWEEN br.start_date - 3 AND br.start_date - 1 THEN f.steps END) AS prep3_steps,
                AVG(CASE WHEN f.date BETWEEN br.start_date - 3 AND br.start_date - 1 THEN f.sleep_hours END) AS prep3_sleep,
                AVG(CASE WHEN f.date BETWEEN br.start_date - 3 AND br.start_date - 1 THEN f.resting_hr END) AS prep3_rhr,
                AVG(CASE WHEN f.date BETWEEN br.start_date - 3 AND br.start_date - 1 THEN f.hrv END) AS prep3_hrv,

                AVG(CASE WHEN f.date BETWEEN br.start_date - 5 AND br.start_date - 1 THEN f.steps END) AS prep5_steps,
                AVG(CASE WHEN f.date BETWEEN br.start_date - 5 AND br.start_date - 1 THEN f.sleep_hours END) AS prep5_sleep,
                AVG(CASE WHEN f.date BETWEEN br.start_date - 5 AND br.start_date - 1 THEN f.resting_hr END) AS prep5_rhr,
                AVG(CASE WHEN f.date BETWEEN br.start_date - 5 AND br.start_date - 1 THEN f.hrv END) AS prep5_hrv,

                AVG(CASE WHEN f.date BETWEEN br.start_date - 7 AND br.start_date - 1 THEN f.steps END) AS prep7_steps,
                AVG(CASE WHEN f.date BETWEEN br.start_date - 7 AND br.start_date - 1 THEN f.sleep_hours END) AS prep7_sleep,
                AVG(CASE WHEN f.date BETWEEN br.start_date - 7 AND br.start_date - 1 THEN f.resting_hr END) AS prep7_rhr,
                AVG(CASE WHEN f.date BETWEEN br.start_date - 7 AND br.start_date - 1 THEN f.hrv END) AS prep7_hrv
            FROM block_ranges br
            LEFT JOIN clean.fitbit_daily f
                ON f.date BETWEEN br.start_date - 7 AND br.start_date - 1
            GROUP BY br.block_id
        ),
        recovery AS (
            SELECT
                br.block_id,

                AVG(CASE WHEN n.date BETWEEN br.end_date + 1 AND br.end_date + 7 THEN n.calories END) AS recovery7_calories,
                AVG(CASE WHEN n.date BETWEEN br.end_date + 1 AND br.end_date + 7 THEN n.protein_g END) AS recovery7_protein,
                AVG(CASE WHEN n.date BETWEEN br.end_date + 1 AND br.end_date + 7 THEN n.carbs_g END) AS recovery7_carbs,
                AVG(CASE WHEN n.date BETWEEN br.end_date + 1 AND br.end_date + 7 THEN n.fat_g END) AS recovery7_fat,

                AVG(CASE WHEN f.date BETWEEN br.end_date + 1 AND br.end_date + 7 THEN f.steps END) AS recovery7_steps,
                AVG(CASE WHEN f.date BETWEEN br.end_date + 1 AND br.end_date + 7 THEN f.sleep_hours END) AS recovery7_sleep,
                AVG(CASE WHEN f.date BETWEEN br.end_date + 1 AND br.end_date + 7 THEN f.resting_hr END) AS recovery7_rhr,
                AVG(CASE WHEN f.date BETWEEN br.end_date + 1 AND br.end_date + 7 THEN f.hrv END) AS recovery7_hrv
            FROM block_ranges br
            LEFT JOIN clean.nutrition_daily n
                ON n.date BETWEEN br.end_date + 1 AND br.end_date + 7
            LEFT JOIN clean.fitbit_daily f
                ON f.date BETWEEN br.end_date + 1 AND br.end_date + 7
            GROUP BY br.block_id
        )
        SELECT
            bo.*,
            pn.*,
            pf.*,
            r.*,
            CASE
                WHEN bo.fast_weight_change IS NOT NULL
                     AND bo.fast_weight_change <> 0
                     AND bo.fast_fat_change IS NOT NULL
                THEN ABS(bo.fast_fat_change) / ABS(bo.fast_weight_change)
                ELSE NULL
            END AS fat_loss_share
        FROM body_outcomes bo
        LEFT JOIN prep_nutrition pn
            ON bo.block_id = pn.block_id
        LEFT JOIN prep_fitbit pf
            ON bo.block_id = pf.block_id
        LEFT JOIN recovery r
            ON bo.block_id = r.block_id
        ORDER BY bo.start_date
    """).fetchdf()

    con.close()

    if df.empty:
        OUT_BLOCKS_CSV.write_text("", encoding="utf-8")
        OUT_SUMMARY_TXT.write_text("No extended fast blocks found.\n", encoding="utf-8")
        print(f"Saved: {OUT_BLOCKS_CSV}")
        print(f"Saved: {OUT_SUMMARY_TXT}")
        print("\nNo extended fast blocks found.")
        return

    df["block_grade"] = df.apply(classify_block, axis=1)

    # Save all blocks for full transparency
    df.to_csv(OUT_BLOCKS_CSV, index=False)

    # Long fasts only
    df_long = df[df["fast_days"] >= 10].copy()
    if df_long.empty:
        print("No long fasts (>=10 days) found. Using all blocks instead.")
        df_long = df.copy()

    # Best long fast reference blocks:
    # - must be strong/elite
    # - if rebound_fat_14d exists, it must be <= 1.0
    df_reference = df_long[
        df_long["block_grade"].isin(["elite", "strong"])
        & (
            df_long["rebound_fat_14d"].isna()
            | (df_long["rebound_fat_14d"] <= 1.0)
        )
    ].copy()

    # Fallback if filter becomes too strict
    if df_reference.empty:
        df_reference = df_long[
            df_long["block_grade"].isin(["elite", "strong"])
        ].copy()

    if df_reference.empty:
        df_reference = df_long.copy()

    lines: list[str] = []
    lines.append("Optimal Fast Playbook")
    lines.append("=====================")
    lines.append("")

    lines.append("All Block Rankings")
    lines.append("------------------")
    for _, row in df.iterrows():
        lines.append(
            f"block {int(row['block_id'])}: "
            f"{row['start_date']}→{row['end_date']} | "
            f"days={int(row['fast_days'])} | "
            f"grade={row['block_grade']} | "
            f"fat_share={fmt(row['fat_loss_share'])} | "
            f"fast_fat={fmt(row['fast_fat_change'])} | "
            f"fast_lean={fmt(row['fast_lean_change'])} | "
            f"rebound_fat_14d={fmt(row['rebound_fat_14d'])}"
        )

    lines.append("")
    lines.append("Long Fast Reference Set")
    lines.append("-----------------------")
    lines.append(f"Using blocks with fast_days >= 10: {series_ids(df_long)}")
    lines.append(
        "Reference blocks after excluding meaningful fat rebound "
        f"(rebound_fat_14d > 1.0 when available): {series_ids(df_reference)}"
    )

    lines.append("")
    lines.append("Suggested Prep Targets")
    lines.append("----------------------")
    lines.append(f"prep3_calories: {avg_of(df_reference, 'prep3_calories')}")
    lines.append(f"prep5_calories: {avg_of(df_reference, 'prep5_calories')}")
    lines.append(f"prep7_calories: {avg_of(df_reference, 'prep7_calories')}")
    lines.append(f"prep3_protein:  {avg_of(df_reference, 'prep3_protein')}")
    lines.append(f"prep5_protein:  {avg_of(df_reference, 'prep5_protein')}")
    lines.append(f"prep7_protein:  {avg_of(df_reference, 'prep7_protein')}")
    lines.append(f"prep3_carbs:    {avg_of(df_reference, 'prep3_carbs')}")
    lines.append(f"prep5_carbs:    {avg_of(df_reference, 'prep5_carbs')}")
    lines.append(f"prep7_carbs:    {avg_of(df_reference, 'prep7_carbs')}")
    lines.append(f"prep3_fat:      {avg_of(df_reference, 'prep3_fat')}")
    lines.append(f"prep5_fat:      {avg_of(df_reference, 'prep5_fat')}")
    lines.append(f"prep7_fat:      {avg_of(df_reference, 'prep7_fat')}")
    lines.append(f"prep3_steps:    {avg_of(df_reference, 'prep3_steps')}")
    lines.append(f"prep5_steps:    {avg_of(df_reference, 'prep5_steps')}")
    lines.append(f"prep7_steps:    {avg_of(df_reference, 'prep7_steps')}")
    lines.append(f"prep3_sleep:    {avg_of(df_reference, 'prep3_sleep')}")
    lines.append(f"prep5_sleep:    {avg_of(df_reference, 'prep5_sleep')}")
    lines.append(f"prep7_sleep:    {avg_of(df_reference, 'prep7_sleep')}")
    lines.append(f"prep3_rhr:      {avg_of(df_reference, 'prep3_rhr')}")
    lines.append(f"prep5_rhr:      {avg_of(df_reference, 'prep5_rhr')}")
    lines.append(f"prep7_rhr:      {avg_of(df_reference, 'prep7_rhr')}")
    lines.append(f"prep3_hrv:      {avg_of(df_reference, 'prep3_hrv')}")
    lines.append(f"prep5_hrv:      {avg_of(df_reference, 'prep5_hrv')}")
    lines.append(f"prep7_hrv:      {avg_of(df_reference, 'prep7_hrv')}")

    lines.append("")
    lines.append("Suggested Recovery Targets")
    lines.append("--------------------------")
    lines.append(f"recovery7_calories: {avg_of(df_reference, 'recovery7_calories')}")
    lines.append(f"recovery7_protein:  {avg_of(df_reference, 'recovery7_protein')}")
    lines.append(f"recovery7_carbs:    {avg_of(df_reference, 'recovery7_carbs')}")
    lines.append(f"recovery7_fat:      {avg_of(df_reference, 'recovery7_fat')}")
    lines.append(f"recovery7_steps:    {avg_of(df_reference, 'recovery7_steps')}")
    lines.append(f"recovery7_sleep:    {avg_of(df_reference, 'recovery7_sleep')}")
    lines.append(f"recovery7_rhr:      {avg_of(df_reference, 'recovery7_rhr')}")
    lines.append(f"recovery7_hrv:      {avg_of(df_reference, 'recovery7_hrv')}")

    lines.append("")
    lines.append("Interpretation")
    lines.append("--------------")
    lines.append("This playbook is based on long fasts only.")
    lines.append("Blocks with clear fat regain by day 14 are excluded from the reference set when that rebound data exists.")
    lines.append("Use this as your practical template:")
    lines.append("- controlled prep calories")
    lines.append("- adequate protein before the fast")
    lines.append("- moderate carbs before the fast")
    lines.append("- controlled recovery calories")
    lines.append("- high protein during recovery")
    lines.append("- maintain steps during recovery")
    lines.append("- treat the refeed as part of the intervention, not the end of it")

    OUT_SUMMARY_TXT.write_text("\n".join(lines), encoding="utf-8")

    print(f"Saved: {OUT_BLOCKS_CSV}")
    print(f"Saved: {OUT_SUMMARY_TXT}")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()