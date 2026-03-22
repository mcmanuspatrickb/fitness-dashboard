from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"

FILE_PATH = PROJECT_ROOT / "data_raw" / "historical" / "Fitbit" / "Sleep Score" / "sleep_score.csv"

if not FILE_PATH.exists():
    raise FileNotFoundError(f"File not found: {FILE_PATH}")

df = pd.read_csv(FILE_PATH)
df.columns = [c.strip() for c in df.columns]

df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df["date"] = df["timestamp"].dt.date

con = duckdb.connect(str(DB_PATH))

con.execute("DELETE FROM raw.fitbit_sleep_score WHERE source = 'fitbit_export_sleep_score'")
con.register("sleep_score_df", df)

con.execute("""
INSERT INTO raw.fitbit_sleep_score (
    date,
    timestamp,
    overall_score,
    composition_score,
    revitalization_score,
    duration_score,
    deep_sleep_minutes,
    nightly_resting_hr,
    restlessness,
    source
)
SELECT
    date,
    timestamp,
    overall_score,
    composition_score,
    revitalization_score,
    duration_score,
    deep_sleep_in_minutes,
    resting_heart_rate,
    restlessness,
    'fitbit_export_sleep_score'
FROM sleep_score_df
WHERE date IS NOT NULL
""")

row_count = con.execute("SELECT COUNT(*) FROM raw.fitbit_sleep_score").fetchone()[0]

preview = con.execute("""
SELECT date, overall_score, nightly_resting_hr, restlessness
FROM raw.fitbit_sleep_score
ORDER BY date DESC
LIMIT 10
""").fetchdf()

con.close()

print(f"Imported {row_count} sleep score rows.")
print(preview)