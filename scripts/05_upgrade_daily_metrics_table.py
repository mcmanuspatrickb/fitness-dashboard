import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("DROP TABLE IF EXISTS analytics.daily_metrics")

con.execute("""
CREATE TABLE analytics.daily_metrics (
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
    steps INTEGER,
    sleep_hours DOUBLE,
    resting_hr DOUBLE,
    hrv DOUBLE,
    workout_count INTEGER,
    training_volume DOUBLE,
    waist_cm DOUBLE,
    fasting_state VARCHAR,
    fasting_hours DOUBLE,
    mounjaro_mg DOUBLE,
    hunger_score INTEGER,
    notes VARCHAR
)
""")

con.close()

print("Upgraded analytics.daily_metrics successfully.")