import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("""
CREATE TABLE IF NOT EXISTS raw.withings_tokens (
    provider VARCHAR,
    access_token VARCHAR,
    refresh_token VARCHAR,
    token_type VARCHAR,
    scope VARCHAR,
    expires_in INTEGER,
    obtained_at TIMESTAMP DEFAULT now()
)
""")

con.close()
print("raw.withings_tokens created successfully.")