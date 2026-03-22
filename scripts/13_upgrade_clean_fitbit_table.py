import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("DROP TABLE IF EXISTS clean.fitbit_daily")

con.execute("""
CREATE TABLE clean.fitbit_daily (
    date DATE,
    steps INTEGER,
    calories_burned DOUBLE,
    resting_hr DOUBLE,
    hrv DOUBLE,
    sleep_hours DOUBLE,
    active_minutes INTEGER,
    sleep_efficiency DOUBLE,
    deep_sleep_minutes DOUBLE,
    rem_sleep_minutes DOUBLE,
    wake_minutes DOUBLE,
    sleep_score DOUBLE,
    sleep_restlessness DOUBLE
)
""")

con.close()
print("Upgraded clean.fitbit_daily successfully.")