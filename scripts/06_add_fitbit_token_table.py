import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("""
CREATE TABLE IF NOT EXISTS raw.fitbit_tokens (
    provider VARCHAR,
    access_token VARCHAR,
    refresh_token VARCHAR,
    token_type VARCHAR,
    scope VARCHAR,
    expires_in INTEGER,
    user_id VARCHAR,
    obtained_at TIMESTAMP DEFAULT now()
)
""")

con.close()
print("raw.fitbit_tokens created successfully.")