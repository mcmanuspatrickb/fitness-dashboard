import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("DELETE FROM analytics.daily_metrics")

con.execute("""
INSERT INTO analytics.daily_metrics (
    date,
    weight_kg,
    fat_mass_kg,
    lean_mass_kg,
    steps,
    sleep_hours,
    resting_hr,
    hrv,
    calories,
    protein_g,
    carbs_g,
    fat_g,
    fiber_g,
    alcohol_g,
    nutrition_source,
    workout_count,
    training_volume,
    fasting_state,
    mounjaro_mg,
    hunger_score
)
WITH date_spine AS (
    SELECT date FROM clean.body_composition
    UNION
    SELECT date FROM clean.fitbit_daily
    UNION
    SELECT date FROM clean.nutrition_daily
    UNION
    SELECT date FROM clean.training_summary
    UNION
    SELECT date FROM clean.interventions_daily
)
SELECT
    d.date,
    bc.weight_kg,
    bc.fat_mass_kg,
    bc.lean_mass_kg,
    fb.steps,
    fb.sleep_hours,
    fb.resting_hr,
    fb.hrv,
    n.calories,
    n.protein_g,
    n.carbs_g,
    n.fat_g,
    n.fiber_g,
    n.alcohol_g,
    n.source AS nutrition_source,
    ts.workout_count,
    ts.total_volume AS training_volume,
    COALESCE(i.fasting_state, 'normal') AS fasting_state,
    i.mounjaro_mg,
    i.hunger_score
FROM date_spine d
LEFT JOIN clean.body_composition bc
    ON d.date = bc.date
LEFT JOIN clean.fitbit_daily fb
    ON d.date = fb.date
LEFT JOIN clean.nutrition_daily n
    ON d.date = n.date
LEFT JOIN clean.training_summary ts
    ON d.date = ts.date
LEFT JOIN clean.interventions_daily i
    ON d.date = i.date
ORDER BY d.date
""")

row_count = con.execute("SELECT COUNT(*) FROM analytics.daily_metrics").fetchone()[0]

coverage = con.execute("""
SELECT
    COUNT(*) AS rows,
    MIN(date) AS min_date,
    MAX(date) AS max_date,
    COUNT(calories) AS calories_days,
    COUNT(protein_g) AS protein_days,
    COUNT(carbs_g) AS carbs_days,
    COUNT(fat_g) AS fat_days,
    COUNT(fiber_g) AS fiber_days,
    COUNT(alcohol_g) AS alcohol_days
FROM analytics.daily_metrics
""").fetchdf()

preview = con.execute("""
SELECT
    date,
    weight_kg,
    fat_mass_kg,
    lean_mass_kg,
    steps,
    sleep_hours,
    resting_hr,
    hrv,
    calories,
    protein_g,
    carbs_g,
    fat_g,
    fiber_g,
    alcohol_g,
    nutrition_source,
    workout_count,
    training_volume,
    fasting_state,
    mounjaro_mg,
    hunger_score
FROM analytics.daily_metrics
ORDER BY date DESC
LIMIT 20
""").fetchdf()

con.close()

print(f"Built analytics.daily_metrics with {row_count} rows.")
print()
print("Nutrition coverage:")
print(coverage.to_string(index=False))
print()
print(preview)