import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("""
CREATE TABLE IF NOT EXISTS raw.hevy_workout_events (
    event_id VARCHAR,
    event_type VARCHAR,
    workout_id VARCHAR,
    event_time TIMESTAMP,
    raw_json JSON
)
""")

con.execute("""
CREATE TABLE IF NOT EXISTS raw.hevy_workouts (
    workout_id VARCHAR,
    workout_start TIMESTAMP,
    workout_end TIMESTAMP,
    title VARCHAR,
    source VARCHAR,
    raw_json JSON
)
""")

con.execute("""
CREATE TABLE IF NOT EXISTS raw.hevy_sets (
    workout_id VARCHAR,
    exercise_name VARCHAR,
    set_index INTEGER,
    reps INTEGER,
    weight_kg DOUBLE,
    duration_seconds DOUBLE,
    distance_meters DOUBLE,
    raw_json JSON
)
""")

con.close()
print("Hevy raw tables created successfully.")