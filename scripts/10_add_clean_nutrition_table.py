import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("""
CREATE TABLE IF NOT EXISTS clean.nutrition_daily (
    date DATE,
    calories DOUBLE,
    protein_g DOUBLE,
    carbs_g DOUBLE,
    fat_g DOUBLE,
    fiber_g DOUBLE,
    alcohol_g DOUBLE,
    source VARCHAR
)
""")

con.close()
print("clean.nutrition_daily created successfully.")