from pathlib import Path
import duckdb

# Database path
DB_PATH = Path("db/fitness.duckdb")

def main() -> None:
    # Ensure parent folder exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Connect to DuckDB (creates file if it does not exist)
    con = duckdb.connect(str(DB_PATH))

    # Create schemas
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    con.execute("CREATE SCHEMA IF NOT EXISTS clean;")
    con.execute("CREATE SCHEMA IF NOT EXISTS analytics;")

    # Optional: simple sanity table
    con.execute("""
        CREATE TABLE IF NOT EXISTS analytics.project_info (
            key VARCHAR PRIMARY KEY,
            value VARCHAR
        );
    """)

    con.execute("""
        INSERT OR IGNORE INTO analytics.project_info (key, value)
        VALUES
            ('project_name', 'fitness_dashboard'),
            ('db_version', '1');
    """)

    con.close()
    print(f"Initialized DuckDB at: {DB_PATH}")

if __name__ == "__main__":
    main()