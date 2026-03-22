from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
HRV_DIR = PROJECT_ROOT / "data_raw" / "historical" / "Fitbit" / "Heart Rate Variability"

if not HRV_DIR.exists():
    raise FileNotFoundError(f"Directory not found: {HRV_DIR}")

# Pick the daily summary CSV files only
csv_files = sorted(HRV_DIR.glob("Daily Heart Rate Variability Summary*.csv"))

if not csv_files:
    raise FileNotFoundError(f"No 'Daily Heart Rate Variability Summary*.csv' files found in {HRV_DIR}")

frames = []

for file_path in csv_files:
    df = pd.read_csv(file_path)
    df.columns = [c.strip() for c in df.columns]

    expected = {"timestamp", "rmssd", "nremhr", "entropy"}
    missing = expected - set(df.columns)
    if missing:
        print(f"Skipping {file_path.name}, missing columns: {missing}")
        continue

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["date"] = df["timestamp"].dt.date
    df["source"] = "fitbit_export_hrv_daily"

    frames.append(df[["date", "timestamp", "rmssd", "nremhr", "entropy", "source"]].copy())

if not frames:
    raise RuntimeError("No valid HRV daily summary files were parsed.")

all_df = pd.concat(frames, ignore_index=True)

con = duckdb.connect(str(DB_PATH))

con.execute("DELETE FROM raw.fitbit_hrv_history WHERE source = 'fitbit_export_hrv_daily'")
con.register("fitbit_hrv_df", all_df)

con.execute("""
    INSERT INTO raw.fitbit_hrv_history (
        date,
        timestamp,
        rmssd,
        nremhr,
        entropy,
        source
    )
    SELECT
        date,
        timestamp,
        rmssd,
        nremhr,
        entropy,
        source
    FROM fitbit_hrv_df
    WHERE date IS NOT NULL
    ORDER BY date, timestamp
""")

row_count = con.execute("SELECT COUNT(*) FROM raw.fitbit_hrv_history").fetchone()[0]
preview = con.execute("""
    SELECT date, rmssd, nremhr, entropy
    FROM raw.fitbit_hrv_history
    ORDER BY date DESC
    LIMIT 10
""").fetchdf()

con.close()

print(f"Imported {row_count} Fitbit HRV history rows.")
print(preview)