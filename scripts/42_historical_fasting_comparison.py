from pathlib import Path

import duckdb
import pandas as pd

DB_PATH = "db/fitness.duckdb"
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

con = duckdb.connect(DB_PATH)

df = con.execute("""
    SELECT
        fasting_state,
        COUNT(*) AS day_count,
        AVG(calories) AS avg_calories,
        AVG(protein_g) AS avg_protein_g,
        AVG(carbs_g) AS avg_carbs_g,
        AVG(fat_g) AS avg_fat_g,
        AVG(fiber_g) AS avg_fiber_g,
        AVG(steps) AS avg_steps,
        AVG(resting_hr) AS avg_resting_hr,
        AVG(sleep_hours) AS avg_sleep_hours,
        AVG(hrv) AS avg_hrv,
        AVG(weight_kg) AS avg_weight_kg,
        AVG(fat_mass_kg) AS avg_fat_mass_kg,
        AVG(lean_mass_kg) AS avg_lean_mass_kg
    FROM analytics.historical_daily_metrics
    WHERE fasting_state IS NOT NULL
      AND nutrition_source = 'mfp_history'
    GROUP BY fasting_state
    ORDER BY fasting_state
""").fetchdf()

con.close()

if df.empty:
    raise RuntimeError("No historical fasting comparison data found.")

output_path = REPORTS_DIR / "historical_fasting_comparison.csv"
df.to_csv(output_path, index=False)

print(f"Saved fasting comparison to: {output_path}")
print(df)
