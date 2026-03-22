import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("""
CREATE TABLE IF NOT EXISTS analytics.historical_daily_metrics (
    date DATE,
    weight_kg DOUBLE,
    fat_mass_kg DOUBLE,
    lean_mass_kg DOUBLE,
    body_fat_percent DOUBLE,
    muscle_mass_kg DOUBLE,
    muscle_percent DOUBLE,
    body_water_percent DOUBLE,
    visceral_fat DOUBLE,
    bone_mass_kg DOUBLE,
    calories DOUBLE,
    protein_g DOUBLE,
    carbs_g DOUBLE,
    fat_g DOUBLE,
    fiber_g DOUBLE,
    steps INTEGER,
    sleep_hours DOUBLE,
    resting_hr DOUBLE,
    hrv DOUBLE,
    active_minutes INTEGER,
    workout_count INTEGER,
    training_volume DOUBLE,
    fasting_state VARCHAR,
    fasting_hours DOUBLE,
    mounjaro_mg DOUBLE,
    hunger_score INTEGER,
    notes VARCHAR,
    nutrition_source VARCHAR
)
""")

con.close()
print("analytics.historical_daily_metrics created successfully.")