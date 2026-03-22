from __future__ import annotations

import duckdb


DB_PATH = "db/fitness.duckdb"


def table_exists(con: duckdb.DuckDBPyConnection, full_table_name: str) -> bool:
    schema_name, table_name = full_table_name.split(".", 1)
    row = con.execute("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = ? AND table_name = ?
    """, [schema_name, table_name]).fetchone()
    return bool(row and row[0] > 0)


def column_exists(con: duckdb.DuckDBPyConnection, full_table_name: str, column_name: str) -> bool:
    schema_name, table_name = full_table_name.split(".", 1)
    row = con.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = ?
          AND table_name = ?
          AND column_name = ?
    """, [schema_name, table_name, column_name]).fetchone()
    return bool(row and row[0] > 0)


def ensure_column(con: duckdb.DuckDBPyConnection, full_table_name: str, column_name: str, column_type: str) -> None:
    if not column_exists(con, full_table_name, column_name):
        con.execute(f"ALTER TABLE {full_table_name} ADD COLUMN {column_name} {column_type}")


def ensure_daily_trends_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS analytics")

    if not table_exists(con, "analytics.daily_trends"):
        con.execute("""
            CREATE TABLE analytics.daily_trends (
                date DATE,
                weight_kg DOUBLE,
                weight_7d_avg DOUBLE,
                fat_mass_kg DOUBLE,
                fat_mass_7d_avg DOUBLE,
                lean_mass_kg DOUBLE,
                lean_mass_7d_avg DOUBLE,
                visceral_fat DOUBLE,
                visceral_fat_7d_avg DOUBLE,
                steps DOUBLE,
                steps_7d_avg DOUBLE,
                sleep_hours DOUBLE,
                sleep_hours_7d_avg DOUBLE,
                resting_hr DOUBLE,
                resting_hr_7d_avg DOUBLE,
                hrv DOUBLE,
                hrv_7d_avg DOUBLE,
                calories DOUBLE,
                calories_7d_avg DOUBLE,
                protein_g DOUBLE,
                protein_g_7d_avg DOUBLE,
                carbs_g DOUBLE,
                carbs_g_7d_avg DOUBLE,
                fat_g DOUBLE,
                fat_g_7d_avg DOUBLE,
                fasting_state VARCHAR,
                mounjaro_mg DOUBLE,
                hunger_score DOUBLE
            )
        """)
    else:
        ensure_column(con, "analytics.daily_trends", "date", "DATE")
        ensure_column(con, "analytics.daily_trends", "weight_kg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "weight_7d_avg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "fat_mass_kg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "fat_mass_7d_avg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "lean_mass_kg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "lean_mass_7d_avg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "visceral_fat", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "visceral_fat_7d_avg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "steps", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "steps_7d_avg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "sleep_hours", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "sleep_hours_7d_avg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "resting_hr", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "resting_hr_7d_avg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "hrv", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "hrv_7d_avg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "calories", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "calories_7d_avg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "protein_g", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "protein_g_7d_avg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "carbs_g", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "carbs_g_7d_avg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "fat_g", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "fat_g_7d_avg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "fasting_state", "VARCHAR")
        ensure_column(con, "analytics.daily_trends", "mounjaro_mg", "DOUBLE")
        ensure_column(con, "analytics.daily_trends", "hunger_score", "DOUBLE")


def main() -> None:
    con = duckdb.connect(DB_PATH)

    try:
        ensure_daily_trends_table(con)

        con.execute("DELETE FROM analytics.daily_trends")

        con.execute("""
            INSERT INTO analytics.daily_trends (
                date,
                weight_kg,
                weight_7d_avg,
                fat_mass_kg,
                fat_mass_7d_avg,
                lean_mass_kg,
                lean_mass_7d_avg,
                visceral_fat,
                visceral_fat_7d_avg,
                steps,
                steps_7d_avg,
                sleep_hours,
                sleep_hours_7d_avg,
                resting_hr,
                resting_hr_7d_avg,
                hrv,
                hrv_7d_avg,
                calories,
                calories_7d_avg,
                protein_g,
                protein_g_7d_avg,
                carbs_g,
                carbs_g_7d_avg,
                fat_g,
                fat_g_7d_avg,
                fasting_state,
                mounjaro_mg,
                hunger_score
            )
            WITH base AS (
                SELECT
                    dm.date,
                    dm.weight_kg,
                    dm.fat_mass_kg,
                    dm.lean_mass_kg,
                    dm.visceral_fat,
                    dm.steps,
                    dm.sleep_hours,
                    dm.resting_hr,
                    dm.hrv,
                    dm.calories,
                    dm.fasting_state,
                    dm.mounjaro_mg,
                    dm.hunger_score,
                    n.protein_g,
                    n.carbs_g,
                    n.fat_g
                FROM analytics.daily_metrics dm
                LEFT JOIN clean.nutrition_daily n
                    ON dm.date = n.date
            )
            SELECT
                date,

                weight_kg,
                AVG(weight_kg) OVER (
                    ORDER BY date
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS weight_7d_avg,

                fat_mass_kg,
                AVG(fat_mass_kg) OVER (
                    ORDER BY date
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS fat_mass_7d_avg,

                lean_mass_kg,
                AVG(lean_mass_kg) OVER (
                    ORDER BY date
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS lean_mass_7d_avg,

                visceral_fat,
                AVG(visceral_fat) OVER (
                    ORDER BY date
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS visceral_fat_7d_avg,

                steps,
                AVG(steps) OVER (
                    ORDER BY date
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS steps_7d_avg,

                sleep_hours,
                AVG(sleep_hours) OVER (
                    ORDER BY date
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS sleep_hours_7d_avg,

                resting_hr,
                AVG(resting_hr) OVER (
                    ORDER BY date
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS resting_hr_7d_avg,

                hrv,
                AVG(hrv) OVER (
                    ORDER BY date
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS hrv_7d_avg,

                calories,
                AVG(calories) OVER (
                    ORDER BY date
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS calories_7d_avg,

                protein_g,
                AVG(protein_g) OVER (
                    ORDER BY date
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS protein_g_7d_avg,

                carbs_g,
                AVG(carbs_g) OVER (
                    ORDER BY date
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS carbs_g_7d_avg,

                fat_g,
                AVG(fat_g) OVER (
                    ORDER BY date
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS fat_g_7d_avg,

                fasting_state,
                mounjaro_mg,
                hunger_score
            FROM base
            ORDER BY date
        """)

        row_count = con.execute("""
            SELECT COUNT(*)
            FROM analytics.daily_trends
        """).fetchone()[0]

        preview = con.execute("""
            SELECT *
            FROM analytics.daily_trends
            ORDER BY date DESC
            LIMIT 20
        """).fetchdf()

        print(f"Built analytics.daily_trends with {row_count} rows.")
        print(preview.to_string(index=False))

    finally:
        con.close()


if __name__ == "__main__":
    main()