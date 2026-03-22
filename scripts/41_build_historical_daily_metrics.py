import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("DELETE FROM analytics.historical_daily_metrics")

con.execute("""
INSERT INTO analytics.historical_daily_metrics (
    date,
    weight_kg,
    fat_mass_kg,
    lean_mass_kg,
    steps,
    sleep_hours,
    resting_hr,
    hrv,
    calories,
    workout_count,
    training_volume,
    fasting_state,
    mounjaro_mg,
    nutrition_source
)
SELECT
    dm.date,
    dm.weight_kg,
    dm.fat_mass_kg,
    dm.lean_mass_kg,
    dm.steps,
    dm.sleep_hours,
    dm.resting_hr,
    dm.hrv,
    dm.calories,
    dm.workout_count,
    dm.training_volume,
    COALESCE(dm.fasting_state, 'normal') AS fasting_state,
    dm.mounjaro_mg,
    n.source AS nutrition_source
FROM analytics.daily_metrics dm
LEFT JOIN clean.nutrition_daily n
    ON dm.date = n.date
ORDER BY dm.date DESC
""")

row_count = con.execute(
    "SELECT COUNT(*) FROM analytics.historical_daily_metrics"
).fetchone()[0]

preview = con.execute("""
SELECT *
FROM analytics.historical_daily_metrics
ORDER BY date DESC
LIMIT 20
""").fetchdf()

con.close()

print(f"Built analytics.historical_daily_metrics with {row_count} rows.")
print(preview)