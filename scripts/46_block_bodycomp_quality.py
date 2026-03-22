import pandas as pd
from pathlib import Path

REPORTS_DIR = Path("reports")

df = pd.read_csv(REPORTS_DIR / "fasting_blocks_filtered.csv")

# calculate losses only
df["fat_loss"] = df["fat_change"].apply(lambda x: -x if x < 0 else 0)
df["lean_loss"] = df["lean_change"].apply(lambda x: -x if x < 0 else 0)

df["total_loss"] = df["fat_loss"] + df["lean_loss"]

df["fat_loss_fraction"] = df["fat_loss"] / df["total_loss"]
df["lean_loss_fraction"] = df["lean_loss"] / df["total_loss"]

df["fat_loss_percent"] = df["fat_loss_fraction"] * 100
df["lean_loss_percent"] = df["lean_loss_fraction"] * 100

output = REPORTS_DIR / "fasting_bodycomp_quality.csv"
df.to_csv(output, index=False)

print("Saved improved body composition analysis to:", output)

print(df[[
    "fasting_state",
    "start_date",
    "end_date",
    "duration_days",
    "weight_change",
    "fat_change",
    "lean_change",
    "fat_loss_percent",
    "lean_loss_percent"
]])
