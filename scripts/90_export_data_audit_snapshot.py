from pathlib import Path

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def export_table_summary(con: duckdb.DuckDBPyConnection) -> None:
    summary_query = """
    WITH table_list AS (
        SELECT 'raw.withings_measurements' AS table_name
        UNION ALL SELECT 'raw.fitbit_daily'
        UNION ALL SELECT 'raw.fitbit_sleep_history'
        UNION ALL SELECT 'raw.fitbit_sleep_score'
        UNION ALL SELECT 'raw.fitbit_hrv_history'
        UNION ALL SELECT 'raw.hevy_workouts'
        UNION ALL SELECT 'raw.hevy_sets'
        UNION ALL SELECT 'raw.nutrition_daily'
        UNION ALL SELECT 'raw.interventions_daily'
        UNION ALL SELECT 'clean.body_composition'
        UNION ALL SELECT 'clean.fitbit_daily'
        UNION ALL SELECT 'clean.training_summary'
        UNION ALL SELECT 'clean.nutrition_daily'
        UNION ALL SELECT 'clean.interventions_daily'
        UNION ALL SELECT 'analytics.daily_metrics'
        UNION ALL SELECT 'analytics.daily_trends'
        UNION ALL SELECT 'analytics.historical_daily_metrics'
        UNION ALL SELECT 'analytics.weekly_metrics'
    )
    SELECT *
    FROM table_list
    """

    tables = con.execute(summary_query).fetchdf()

    rows = []
    for table_name in tables["table_name"]:
        try:
            row_count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        except Exception:
            row_count = None

        latest_date = None
        earliest_date = None

        for candidate in ["date", "week_start", "created_at", "start_time"]:
            try:
                result = con.execute(
                    f"SELECT MIN({candidate}), MAX({candidate}) FROM {table_name}"
                ).fetchone()
                if result is not None and (result[0] is not None or result[1] is not None):
                    earliest_date, latest_date = result
                    break
            except Exception:
                continue

        rows.append(
            {
                "table_name": table_name,
                "row_count": row_count,
                "earliest_date": earliest_date,
                "latest_date": latest_date,
            }
        )

    df = pd.DataFrame(rows).sort_values("table_name").reset_index(drop=True)
    output_path = REPORTS_DIR / "data_audit_table_summary.csv"
    df.to_csv(output_path, index=False)
    print(f"Saved: {output_path}")
    print(df.to_string(index=False))


def export_daily_audit_snapshot(con: duckdb.DuckDBPyConnection) -> None:
    query = """
    WITH date_spine AS (
        SELECT date FROM analytics.daily_metrics
        UNION
        SELECT date FROM clean.nutrition_daily
        UNION
        SELECT date FROM clean.fitbit_daily
        UNION
        SELECT date FROM clean.body_composition
        UNION
        SELECT date FROM clean.training_summary
        UNION
        SELECT date FROM clean.interventions_daily
    )
    SELECT
        d.date,

        -- body comp
        bc.weight_kg,
        bc.fat_mass_kg,
        bc.lean_mass_kg,

        -- fitbit / recovery
        fb.steps,
        fb.sleep_hours,
        fb.resting_hr,
        fb.hrv,
        fb.sleep_efficiency,

        -- training
        ts.workout_count,
        ts.total_volume AS training_volume,

        -- nutrition
        n.calories,
        n.protein_g,
        n.carbs_g,
        n.fat_g,
        n.fiber_g,
        n.alcohol_g,
        n.source AS nutrition_source,

        -- interventions
        i.fasting_state,
        i.fasting_hours,
        i.mounjaro_mg,
        i.hunger_score,
        i.notes,

        -- analytics.daily_metrics copy
        dm.weight_kg AS dm_weight_kg,
        dm.fat_mass_kg AS dm_fat_mass_kg,
        dm.lean_mass_kg AS dm_lean_mass_kg,
        dm.steps AS dm_steps,
        dm.sleep_hours AS dm_sleep_hours,
        dm.resting_hr AS dm_resting_hr,
        dm.hrv AS dm_hrv,
        dm.calories AS dm_calories,

        -- trends
        dt.weight_7d_avg,
        dt.fat_mass_7d_avg,
        dt.lean_mass_7d_avg,
        dt.steps_7d_avg,
        dt.sleep_hours_7d_avg,
        dt.resting_hr_7d_avg,
        dt.hrv_7d_avg,
        dt.calories_7d_avg,
        dt.protein_g_7d_avg,
        dt.carbs_g_7d_avg,
        dt.fat_g_7d_avg,

        -- presence flags for quick auditing
        CASE WHEN bc.date IS NOT NULL THEN 1 ELSE 0 END AS has_body_comp,
        CASE WHEN fb.date IS NOT NULL THEN 1 ELSE 0 END AS has_fitbit,
        CASE WHEN ts.date IS NOT NULL THEN 1 ELSE 0 END AS has_training,
        CASE WHEN n.date IS NOT NULL THEN 1 ELSE 0 END AS has_nutrition,
        CASE WHEN i.date IS NOT NULL THEN 1 ELSE 0 END AS has_interventions,
        CASE WHEN dm.date IS NOT NULL THEN 1 ELSE 0 END AS has_daily_metrics,
        CASE WHEN dt.date IS NOT NULL THEN 1 ELSE 0 END AS has_daily_trends

    FROM date_spine d
    LEFT JOIN clean.body_composition bc
        ON d.date = bc.date
    LEFT JOIN clean.fitbit_daily fb
        ON d.date = fb.date
    LEFT JOIN clean.training_summary ts
        ON d.date = ts.date
    LEFT JOIN clean.nutrition_daily n
        ON d.date = n.date
    LEFT JOIN clean.interventions_daily i
        ON d.date = i.date
    LEFT JOIN analytics.daily_metrics dm
        ON d.date = dm.date
    LEFT JOIN analytics.daily_trends dt
        ON d.date = dt.date
    ORDER BY d.date DESC
    """

    df = con.execute(query).fetchdf()
    output_path = REPORTS_DIR / "data_audit_daily_snapshot.csv"
    df.to_csv(output_path, index=False)
    print(f"\nSaved: {output_path}")
    print(df.head(20).to_string(index=False))


def export_missingness_summary(con: duckdb.DuckDBPyConnection) -> None:
    query = """
    SELECT
        COUNT(*) AS total_days,
        SUM(CASE WHEN weight_kg IS NULL THEN 1 ELSE 0 END) AS missing_weight_days,
        SUM(CASE WHEN fat_mass_kg IS NULL THEN 1 ELSE 0 END) AS missing_fat_mass_days,
        SUM(CASE WHEN lean_mass_kg IS NULL THEN 1 ELSE 0 END) AS missing_lean_mass_days,
        SUM(CASE WHEN steps IS NULL THEN 1 ELSE 0 END) AS missing_steps_days,
        SUM(CASE WHEN sleep_hours IS NULL THEN 1 ELSE 0 END) AS missing_sleep_days,
        SUM(CASE WHEN resting_hr IS NULL THEN 1 ELSE 0 END) AS missing_resting_hr_days,
        SUM(CASE WHEN hrv IS NULL THEN 1 ELSE 0 END) AS missing_hrv_days,
        SUM(CASE WHEN calories IS NULL THEN 1 ELSE 0 END) AS missing_calorie_days,
        SUM(CASE WHEN fasting_state IS NULL THEN 1 ELSE 0 END) AS missing_fasting_state_days,
        SUM(CASE WHEN mounjaro_mg IS NULL THEN 1 ELSE 0 END) AS missing_mounjaro_days,
        SUM(CASE WHEN hunger_score IS NULL THEN 1 ELSE 0 END) AS missing_hunger_score_days
    FROM analytics.daily_metrics
    """

    df = con.execute(query).fetchdf()
    output_path = REPORTS_DIR / "data_audit_missingness_summary.csv"
    df.to_csv(output_path, index=False)
    print(f"\nSaved: {output_path}")
    print(df.to_string(index=False))


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    con = duckdb.connect(str(DB_PATH))
    try:
        export_table_summary(con)
        export_daily_audit_snapshot(con)
        export_missingness_summary(con)
    finally:
        con.close()

    print("\nData audit export complete.")
    print("Generated files:")
    print(f" - {REPORTS_DIR / 'data_audit_table_summary.csv'}")
    print(f" - {REPORTS_DIR / 'data_audit_daily_snapshot.csv'}")
    print(f" - {REPORTS_DIR / 'data_audit_missingness_summary.csv'}")


if __name__ == "__main__":
    main()