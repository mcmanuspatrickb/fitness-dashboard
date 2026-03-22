import pandas as pd
from pathlib import Path

REPORTS_DIR = Path("reports")

df = pd.read_csv(REPORTS_DIR / "fasting_blocks_filtered.csv")

# Energy densities
FAT_KCAL_PER_KG = 7700
LEAN_KCAL_PER_KG = 1000

def fat_loss(x):
    return -x if x < 0 else 0

def lean_loss(x):
    return -x if x < 0 else 0

df["fat_loss_kg"] = df["fat_change"].apply(fat_loss)
df["lean_loss_kg"] = df["lean_change"].apply(lean_loss)

df["daily_fat_kcal"] = (df["fat_loss_kg"] * FAT_KCAL_PER_KG) / df["duration_days"]
df["daily_lean_kcal"] = (df["lean_loss_kg"] * LEAN_KCAL_PER_KG) / df["duration_days"]

df["energy_from_tissue"] = df["daily_fat_kcal"] + df["daily_lean_kcal"]

df["estimated_tdee"] = df["avg_calories"] + df["energy_from_tissue"]

output = REPORTS_DIR / "historical_tdee_estimates.csv"
df.to_csv(output, index=False)

print("Saved historical TDEE estimates:", output)

print(df[[
    "fasting_state",
    "start_date",
    "end_date",
    "duration_days",
    "avg_calories",
    "fat_loss_kg",
    "lean_loss_kg",
    "estimated_tdee"
]])
