import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

# ---------- RAW DATA TABLES ----------

con.execute("""
CREATE TABLE IF NOT EXISTS raw.withings_measurements (
    measurement_time TIMESTAMP,
    date DATE,
    weight_kg DOUBLE,
    fat_percent DOUBLE,
    fat_mass_kg DOUBLE,
    muscle_percent DOUBLE,
    muscle_mass_kg DOUBLE,
    body_water_percent DOUBLE,
    visceral_fat DOUBLE,
    bone_mass_kg DOUBLE,
    source VARCHAR,
    created_at TIMESTAMP DEFAULT now()
)
""")

con.execute("""
CREATE TABLE IF NOT EXISTS raw.fitbit_daily (
    date DATE,
    steps INTEGER,
    calories_burned DOUBLE,
    resting_hr DOUBLE,
    hrv DOUBLE,
    sleep_hours DOUBLE,
    active_minutes INTEGER,
    created_at TIMESTAMP DEFAULT now()
)
""")

con.execute("""
CREATE TABLE IF NOT EXISTS raw.nutrition_daily (
    date DATE,
    calories DOUBLE,
    protein_g DOUBLE,
    carbs_g DOUBLE,
    fat_g DOUBLE,
    fiber_g DOUBLE,
    alcohol_g DOUBLE,
    source VARCHAR,
    created_at TIMESTAMP DEFAULT now()
)
""")

con.execute("""
CREATE TABLE IF NOT EXISTS raw.training_sets (
    workout_time TIMESTAMP,
    exercise VARCHAR,
    weight_kg DOUBLE,
    reps INTEGER,
    set_number INTEGER,
    volume DOUBLE,
    source VARCHAR,
    created_at TIMESTAMP DEFAULT now()
)
""")

con.execute("""
CREATE TABLE IF NOT EXISTS raw.training_body_stats (
    date DATE,
    weight_kg DOUBLE,
    fat_percent DOUBLE,
    waist_cm DOUBLE,
    chest_cm DOUBLE,
    arms_cm DOUBLE,
    thighs_cm DOUBLE,
    shoulders_cm DOUBLE,
    neck_cm DOUBLE,
    calves_cm DOUBLE,
    created_at TIMESTAMP DEFAULT now()
)
""")

con.execute("""
CREATE TABLE IF NOT EXISTS raw.interventions_daily (
    date DATE,
    fasting_state VARCHAR,
    fasting_hours DOUBLE,
    mounjaro_mg DOUBLE,
    hunger_score INTEGER,
    notes VARCHAR,
    created_at TIMESTAMP DEFAULT now()
)
""")

# ---------- CLEAN TABLES ----------

con.execute("""
CREATE TABLE IF NOT EXISTS clean.body_composition (
    date DATE,
    weight_kg DOUBLE,
    fat_mass_kg DOUBLE,
    lean_mass_kg DOUBLE,
    body_fat_percent DOUBLE
)
""")

con.execute("""
CREATE TABLE IF NOT EXISTS clean.training_summary (
    date DATE,
    workout_count INTEGER,
    total_volume DOUBLE
)
""")

# ---------- ANALYTICS TABLES ----------

con.execute("""
CREATE TABLE IF NOT EXISTS analytics.daily_metrics (
    date DATE,
    weight_kg DOUBLE,
    fat_mass_kg DOUBLE,
    lean_mass_kg DOUBLE,
    calories DOUBLE,
    protein_g DOUBLE,
    steps INTEGER,
    sleep_hours DOUBLE,
    resting_hr DOUBLE,
    hrv DOUBLE,
    workout_count INTEGER,
    training_volume DOUBLE,
    waist_cm DOUBLE
)
""")

con.execute("""
CREATE TABLE IF NOT EXISTS analytics.weekly_metrics (
    week_start DATE,
    avg_weight DOUBLE,
    avg_calories DOUBLE,
    avg_protein DOUBLE,
    avg_steps DOUBLE,
    avg_sleep DOUBLE,
    weight_change DOUBLE,
    fat_mass_change DOUBLE,
    lean_mass_change DOUBLE
)
""")

con.close()

print("Tables created successfully.")
