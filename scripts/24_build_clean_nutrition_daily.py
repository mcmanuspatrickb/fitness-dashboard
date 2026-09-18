import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("DELETE FROM clean.nutrition_daily")

con.execute("""
INSERT INTO clean.nutrition_daily (
    date,
    calories,
    protein_g,
    carbs_g,
    fat_g,
    fiber_g,
    alcohol_g,
    source
)
WITH ranked AS (
    SELECT
        date,
        calories,
        protein_g,
        carbs_g,
        fat_g,
        fiber_g,
        alcohol_g,
        source,
        ROW_NUMBER() OVER (
            PARTITION BY date
            ORDER BY
                CASE
                    WHEN source = 'google_health_cronometer' THEN 1
                    WHEN source = 'cronometer_export' THEN 2
                    WHEN source = 'mfp_history' THEN 3
                    ELSE 99
                END,
                source
        ) AS rn
    FROM raw.nutrition_daily
    WHERE date IS NOT NULL
)
SELECT
    date,
    calories,
    protein_g,
    carbs_g,
    fat_g,
    fiber_g,
    alcohol_g,
    source
FROM ranked
WHERE rn = 1
ORDER BY date
""")

row_count = con.execute("SELECT COUNT(*) FROM clean.nutrition_daily").fetchone()[0]
preview = con.execute("""
SELECT *
FROM clean.nutrition_daily
ORDER BY date DESC
LIMIT 15
""").fetchdf()

con.close()

print(f"Built clean.nutrition_daily with {row_count} rows.")
print(preview)
