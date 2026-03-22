import pandas as pd
from pathlib import Path

REPORTS_DIR = Path("reports")

df = pd.read_csv(REPORTS_DIR / "fasting_blocks_filtered.csv")

# approximate maintenance (historical estimate)
maintenance_kcal = 2500

df["daily_deficit"] = maintenance_kcal - df["avg_calories"]

df["total_deficit"] = df["daily_deficit"] * df["duration_days"]

df["fat_loss_kg"] = df["fat_change"].apply(lambda x: -x if x < 0 else 0)

df["fat_loss_per_1000kcal"] = df["fat_loss_kg"] / (df["total_deficit"] / 1000)

output = REPORTS_DIR / "fat_loss_efficiency.csv"
df.to_csv(output, index=False)

print("Saved fat loss efficiency:", output)

print(df[[
    "fasting_state",
    "duration_days",
    "avg_calories",
    "fat_loss_kg",
    "fat_loss_per_1000kcal"
]])
