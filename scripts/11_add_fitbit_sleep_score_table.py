import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("""
CREATE TABLE IF NOT EXISTS raw.fitbit_sleep_score (
    date DATE,
    timestamp TIMESTAMP,
    overall_score DOUBLE,
    composition_score DOUBLE,
    revitalization_score DOUBLE,
    duration_score DOUBLE,
    deep_sleep_minutes DOUBLE,
    nightly_resting_hr DOUBLE,
    restlessness DOUBLE,
    source VARCHAR
)
""")

con.close()
print("raw.fitbit_sleep_score created successfully.")