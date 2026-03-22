import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("""
CREATE TABLE IF NOT EXISTS raw.fitbit_sleep_history (
    date DATE,
    log_id VARCHAR,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_hours DOUBLE,
    minutes_asleep DOUBLE,
    minutes_awake DOUBLE,
    time_in_bed DOUBLE,
    efficiency DOUBLE,
    deep_minutes DOUBLE,
    light_minutes DOUBLE,
    rem_minutes DOUBLE,
    wake_minutes DOUBLE,
    source VARCHAR
)
""")

con.close()
print("raw.fitbit_sleep_history created successfully.")