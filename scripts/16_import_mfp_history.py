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

# Standardize column names
df.columns = [c.strip() for c in df.columns]

# Parse date
df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date

# Columns that appear to be scaled 10x too high
numeric_cols = [
    "Calories",
    "Fat (g)",
    "Saturated Fat",
    "Polyunsaturated Fat",
    "Monounsaturated Fat",
    "Trans Fat",
    "Cholesterol",
    "Sodium (mg)",
    "Potassium",
    "Carbohydrates (g)",
    "Fiber",
    "Sugar",
    "Protein (g)",
    "Vitamin A",
    "Vitamin C",
    "Calcium",
    "Iron",
]

for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce") / 10.0

# Aggregate meal rows into daily rows
agg_map = {
    "Calories": "sum",
    "Fat (g)": "sum",
    "Carbohydrates (g)": "sum",
    "Protein (g)": "sum",
    "Fiber": "sum",
    "Sugar": "sum",
    "Sodium (mg)": "sum",
    "Potassium": "sum",
    "Eating Habits": "last",
}

daily_df = (
    df.groupby("Date", dropna=True)
      .agg(agg_map)
      .reset_index()
      .rename(columns={
          "Date": "date",
          "Calories": "calories",
          "Fat (g)": "fat_g",
          "Carbohydrates (g)": "carbs_g",
          "Protein (g)": "protein_g",
          "Fiber": "fiber_g",
          "Sugar": "sugar_g",
          "Sodium (mg)": "sodium_mg",
          "Potassium": "potassium_mg",
          "Eating Habits": "source_habit_label",
      })
)

# Add source column
daily_df["source"] = "mfp_history"

con = duckdb.connect(str(DB_PATH))

# Clear only old MFP history rows
con.execute("DELETE FROM raw.nutrition_daily WHERE source = 'mfp_history'")

con.register("mfp_daily_df", daily_df)

con.execute("""
    INSERT INTO raw.nutrition_daily (
        date,
        calories,
        protein_g,
        carbs_g,
        fat_g,
        fiber_g,
        alcohol_g,
        source
    )
    SELECT
        date,
        calories,
        protein_g,
        carbs_g,
        fat_g,
        fiber_g,
        NULL AS alcohol_g,
        source
    FROM mfp_daily_df
    ORDER BY date
""")

row_count = con.execute("""
    SELECT COUNT(*)
    FROM raw.nutrition_daily
    WHERE source = 'mfp_history'
""").fetchone()[0]

preview = con.execute("""
    SELECT date, calories, protein_g, carbs_g, fat_g, fiber_g, source
    FROM raw.nutrition_daily
    WHERE source = 'mfp_history'
    ORDER BY date
    LIMIT 10
""").fetchdf()

con.close()

print(f"Imported {row_count} historical MFP daily rows.")
print(preview)