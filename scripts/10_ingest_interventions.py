import os
from pathlib import Path

import duckdb
import pandas as pd
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"

load_dotenv(dotenv_path=ENV_PATH)

CREDS_FILE = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")

if CREDS_FILE is None or SHEET_NAME is None:
    raise RuntimeError("Missing GOOGLE_SHEETS_CREDENTIALS or GOOGLE_SHEET_NAME in .env")

creds_path = PROJECT_ROOT / CREDS_FILE
if not creds_path.exists():
    raise FileNotFoundError(f"Credentials file not found: {creds_path}")

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

creds = Credentials.from_service_account_file(str(creds_path), scopes=scope)
client = gspread.authorize(creds)

sheet = client.open(SHEET_NAME).sheet1
records = sheet.get_all_records()
df = pd.DataFrame(records)

expected_cols = [
    "date",
    "fasting_state",
    "fasting_hours",
    "mounjaro_mg",
    "hunger_score",
    "notes",
]

missing = [c for c in expected_cols if c not in df.columns]
if missing:
    raise ValueError(f"Missing columns in Google Sheet: {missing}")

df = df[expected_cols].copy()
df = df.replace("", None)

df["date"] = pd.to_datetime(df["date"], errors="raise").dt.date

for col in ["fasting_hours", "mounjaro_mg", "hunger_score"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

con = duckdb.connect(str(DB_PATH))

con.execute("DELETE FROM raw.interventions_daily")
con.register("interventions_df", df)

con.execute("""
    INSERT INTO raw.interventions_daily (
        date,
        fasting_state,
        fasting_hours,
        mounjaro_mg,
        hunger_score,
        notes
    )
    SELECT
        date,
        fasting_state,
        fasting_hours,
        mounjaro_mg,
        CAST(hunger_score AS INTEGER),
        notes
    FROM interventions_df
""")

row_count = con.execute("SELECT COUNT(*) FROM raw.interventions_daily").fetchone()[0]
preview = con.execute("""
    SELECT date, fasting_state, fasting_hours, mounjaro_mg, hunger_score, notes
    FROM raw.interventions_daily
    ORDER BY date
    LIMIT 10
""").fetchdf()

con.close()

print(f"Ingested {row_count} intervention rows.")
print(preview)