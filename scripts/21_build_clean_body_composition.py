import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("DELETE FROM clean.body_composition")

con.execute("""
INSERT INTO clean.body_composition (
    date,
    weight_kg,
    fat_mass_kg,
    lean_mass_kg,
    body_fat_percent,
    muscle_mass_kg,
    muscle_percent,
    body_water_percent,
    visceral_fat,
    bone_mass_kg
)
WITH ranked AS (
    SELECT
        measurement_time,
        date,
        weight_kg,
        fat_mass_kg,
        fat_percent AS body_fat_percent,
        muscle_mass_kg,
        muscle_percent,
        body_water_percent,
        visceral_fat,
        bone_mass_kg,
        (
            CASE WHEN weight_kg IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN fat_mass_kg IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN fat_percent IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN muscle_mass_kg IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN muscle_percent IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN body_water_percent IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN visceral_fat IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN bone_mass_kg IS NOT NULL THEN 1 ELSE 0 END
        ) AS completeness_score,
        ROW_NUMBER() OVER (
            PARTITION BY date
            ORDER BY
                CASE WHEN weight_kg IS NOT NULL THEN 1 ELSE 0 END DESC,
                (
                    CASE WHEN weight_kg IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN fat_mass_kg IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN fat_percent IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN muscle_mass_kg IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN muscle_percent IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN body_water_percent IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN visceral_fat IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN bone_mass_kg IS NOT NULL THEN 1 ELSE 0 END
                ) DESC,
                measurement_time DESC
        ) AS rn
    FROM raw.withings_measurements
    WHERE date IS NOT NULL
)
SELECT
    date,
    weight_kg,
    fat_mass_kg,
    CASE
        WHEN weight_kg IS NOT NULL AND fat_mass_kg IS NOT NULL
            THEN weight_kg - fat_mass_kg
        ELSE NULL
    END AS lean_mass_kg,
    body_fat_percent,
    muscle_mass_kg,
    muscle_percent,
    body_water_percent,
    visceral_fat,
    bone_mass_kg
FROM ranked
WHERE rn = 1
  AND weight_kg IS NOT NULL
ORDER BY date
""")

row_count = con.execute("SELECT COUNT(*) FROM clean.body_composition").fetchone()[0]
preview = con.execute("""
SELECT *
FROM clean.body_composition
ORDER BY date DESC
LIMIT 10
""").fetchdf()

con.close()

print(f"Built clean.body_composition with {row_count} rows.")
print(preview)