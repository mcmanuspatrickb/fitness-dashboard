from pathlib import Path
import json

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
SLEEP_DIR = PROJECT_ROOT / "data_raw" / "historical" / "Fitbit" / "Global Export Data"

if not SLEEP_DIR.exists():
    raise FileNotFoundError(f"Directory not found: {SLEEP_DIR}")

sleep_files = sorted(SLEEP_DIR.glob("sleep-*.json"))

if not sleep_files:
    raise FileNotFoundError(f"No sleep-*.json files found in {SLEEP_DIR}")

rows = []

for file_path in sleep_files:
    data = json.loads(file_path.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        continue

    for item in data:
        levels_summary = item.get("levels", {}).get("summary", {})

        rows.append({
            "date": pd.to_datetime(item.get("dateOfSleep"), errors="coerce").date() if item.get("dateOfSleep") else None,
            "log_id": str(item.get("logId")) if item.get("logId") is not None else None,
            "start_time": pd.to_datetime(item.get("startTime"), errors="coerce"),
            "end_time": pd.to_datetime(item.get("endTime"), errors="coerce"),
            "duration_hours": (item.get("minutesAsleep") / 60.0) if item.get("minutesAsleep") is not None else None,
            "minutes_asleep": item.get("minutesAsleep"),
            "minutes_awake": item.get("minutesAwake"),
            "time_in_bed": item.get("timeInBed"),
            "efficiency": item.get("efficiency"),
            "deep_minutes": levels_summary.get("deep", {}).get("minutes"),
            "light_minutes": levels_summary.get("light", {}).get("minutes"),
            "rem_minutes": levels_summary.get("rem", {}).get("minutes"),
            "wake_minutes": levels_summary.get("wake", {}).get("minutes"),
            "source": "fitbit_export_sleep_json",
        })

df = pd.DataFrame(rows)

con = duckdb.connect(str(DB_PATH))

con.execute("DELETE FROM raw.fitbit_sleep_history WHERE source = 'fitbit_export_sleep_json'")
con.register("fitbit_sleep_df", df)

con.execute("""
    INSERT INTO raw.fitbit_sleep_history (
        date,
        log_id,
        start_time,
        end_time,
        duration_hours,
        minutes_asleep,
        minutes_awake,
        time_in_bed,
        efficiency,
        deep_minutes,
        light_minutes,
        rem_minutes,
        wake_minutes,
        source
    )
    SELECT
        date,
        log_id,
        start_time,
        end_time,
        duration_hours,
        minutes_asleep,
        minutes_awake,
        time_in_bed,
        efficiency,
        deep_minutes,
        light_minutes,
        rem_minutes,
        wake_minutes,
        source
    FROM fitbit_sleep_df
    WHERE date IS NOT NULL
    ORDER BY date
""")

row_count = con.execute("SELECT COUNT(*) FROM raw.fitbit_sleep_history").fetchone()[0]
preview = con.execute("""
    SELECT
        date,
        duration_hours,
        minutes_asleep,
        minutes_awake,
        efficiency,
        deep_minutes,
        rem_minutes
    FROM raw.fitbit_sleep_history
    ORDER BY date DESC
    LIMIT 10
""").fetchdf()

con.close()

print(f"Imported {row_count} Fitbit historical sleep rows.")
print(preview)