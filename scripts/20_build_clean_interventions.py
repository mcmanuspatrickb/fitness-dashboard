import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("CREATE SCHEMA IF NOT EXISTS clean")

con.execute("""
CREATE TABLE IF NOT EXISTS clean.interventions_daily (
    date DATE,
    fasting_state VARCHAR,
    fasting_hours DOUBLE,
    mounjaro_mg DOUBLE,
    hunger_score INTEGER,
    notes VARCHAR
)
""")

con.execute("DELETE FROM clean.interventions_daily")

con.execute("""
INSERT INTO clean.interventions_daily (
    date,
    fasting_state,
    fasting_hours,
    mounjaro_mg,
    hunger_score,
    notes
)
WITH ranked AS (
    SELECT
        date,
        LOWER(TRIM(fasting_state)) AS fasting_state,
        fasting_hours,
        mounjaro_mg,
        hunger_score,
        notes,
        ROW_NUMBER() OVER (
            PARTITION BY date
            ORDER BY
                CASE
                    WHEN notes LIKE 'historical_fasting_import%' THEN 2
                    WHEN notes LIKE 'mfp_historical_fasting:%' THEN 3
                    ELSE 1
                END,
                date
        ) AS rn
    FROM raw.interventions_daily
    WHERE date IS NOT NULL
)
SELECT
    date,
    fasting_state,
    fasting_hours,
    mounjaro_mg,
    hunger_score,
    notes
FROM ranked
WHERE rn = 1
ORDER BY date
""")

row_count = con.execute("SELECT COUNT(*) FROM clean.interventions_daily").fetchone()[0]
preview = con.execute("""
SELECT *
FROM clean.interventions_daily
ORDER BY date DESC
LIMIT 20
""").fetchdf()

con.close()

print(f"Built clean.interventions_daily with {row_count} rows.")
print(preview.to_string(index=False))