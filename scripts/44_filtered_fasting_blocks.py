from pathlib import Path
import pandas as pd

REPORTS_DIR = Path("reports")

df = pd.read_csv(REPORTS_DIR / "fasting_blocks_analysis.csv")

# minimum durations
min_days = {
    "ef": 2,
    "omad": 7,
    "if": 14,
    "normal": 14
}

df["min_required"] = df["fasting_state"].map(min_days)

filtered = df[df["duration_days"] >= df["min_required"]]

output = REPORTS_DIR / "fasting_blocks_filtered.csv"
filtered.to_csv(output, index=False)

print("Filtered blocks saved to:", output)
print(filtered)
