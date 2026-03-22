import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("""
CREATE TABLE IF NOT EXISTS clean.fitbit_daily (
    date DATE,
    steps INTEGER,
    calories_burned DOUBLE,
    resting_hr DOUBLE,
    hrv DOUBLE,
    sleep_hours DOUBLE,
    active_minutes INTEGER
)
""")

con.close()

print("clean.fitbit_daily created successfully.")