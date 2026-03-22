import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("""
CREATE TABLE IF NOT EXISTS clean.interventions_daily (
    date DATE,
    fasting_state VARCHAR,
    fasting_hours DOUBLE,
    mounjaro_mg DOUBLE,
    hunger_score INTEGER,
    notes VARCHAR
)
""")

con.close()

print("clean.interventions_daily created successfully.")