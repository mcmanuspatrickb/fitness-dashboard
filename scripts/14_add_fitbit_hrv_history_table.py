import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("""
CREATE TABLE IF NOT EXISTS raw.fitbit_hrv_history (
    date DATE,
    timestamp TIMESTAMP,
    rmssd DOUBLE,
    nremhr DOUBLE,
    entropy DOUBLE,
    source VARCHAR
)
""")

con.close()
print("raw.fitbit_hrv_history created successfully.")