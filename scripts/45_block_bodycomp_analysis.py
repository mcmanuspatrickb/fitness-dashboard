import pandas as pd
from pathlib import Path

REPORTS_DIR = Path("reports")

df = pd.read_csv(REPORTS_DIR / "fasting_blocks_filtered.csv")

df["fat_loss_ratio"] = df["fat_change"] / df["weight_change"]
df["lean_loss_ratio"] = df["lean_change"] / df["weight_change"]

df["fat_percent"] = df["fat_loss_ratio"] * 100
df["lean_percent"] = df["lean_loss_ratio"] * 100

output = REPORTS_DIR / "fasting_bodycomp_analysis.csv"
df.to_csv(output, index=False)

print("Saved body composition analysis to:", output)
print(df[[
    "fasting_state",
    "start_date",
    "end_date",
    "duration_days",
    "weight_change",
    "fat_change",
    "lean_change",
    "fat_percent",
    "lean_percent"
]])
