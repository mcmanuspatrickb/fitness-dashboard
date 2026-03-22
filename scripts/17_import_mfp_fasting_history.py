from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
FILE_PATH = PROJECT_ROOT / "data_raw" / "historical" / "MFP_Historical_Data.xlsx"
SHEET_NAME = "Historical Fasting Periods"

if not FILE_PATH.exists():
    raise FileNotFoundError(f"File not found: {FILE_PATH}")

# Read Excel
df = pd.read_excel(FILE_PATH, sheet_name=SHEET_NAME)
df.columns = [c.strip() for c in df.columns]

# Parse date
df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date

if "Eating Habits" not in df.columns:
    raise ValueError("Column 'Eating Habits' not found in MFP file.")

habit_df = (
    df[["Date", "Eating Habits"]]
    .dropna(subset=["Date"])
    .copy()
)

# Normalize text
habit_df["Eating Habits"] = (
    habit_df["Eating Habits"]
    .fillna("")
    .astype(str)
    .str.strip()
)

# Collapse to one row per date
habit_df = (
    habit_df.groupby("Date", dropna=True)["Eating Habits"]
    .last()
    .reset_index()
)

def map_fasting_state(habit: str) -> str:
    h = (habit or "").strip().lower()

    if h == "ef":
        return "ef"
    if h == "omad":
        return "omad"
    if h == "if":
        return "if"
    if h in {"normal", "baseline"}:
        return "normal"

    # default fallback
    return "normal"

habit_df["fasting_state"] = habit_df["Eating Habits"].apply(map_fasting_state)
habit_df["fasting_hours"] = None
habit_df["mounjaro_mg"] = None
habit_df["hunger_score"] = None

# Preserve original label in notes for traceability
habit_df["notes"] = "mfp_historical_fasting:" + habit_df["Eating Habits"].fillna("").astype(str)

habit_df = habit_df.rename(columns={"Date": "date"})
habit_df = habit_df[
    ["date", "fasting_state", "fasting_hours", "mounjaro_mg", "hunger_score", "notes"]
].copy()

con = duckdb.connect(str(DB_PATH))

# Remove only prior MFP historical fasting imports
con.execute("""
    DELETE FROM raw.interventions_daily
    WHERE notes LIKE 'mfp_historical_fasting:%'
       OR notes = 'mfp_historical_fasting'
""")

con.register("mfp_fasting_df", habit_df)

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
        hunger_score,
        notes
    FROM mfp_fasting_df
    ORDER BY date
""")

row_count = con.execute("""
    SELECT COUNT(*)
    FROM raw.interventions_daily
    WHERE notes LIKE 'mfp_historical_fasting:%'
""").fetchone()[0]

preview = con.execute("""
    SELECT date, fasting_state, notes
    FROM raw.interventions_daily
    WHERE notes LIKE 'mfp_historical_fasting:%'
    ORDER BY date
    LIMIT 20
""").fetchdf()

con.close()

print(f"Imported {row_count} historical fasting rows from MFP.")
print(preview)
