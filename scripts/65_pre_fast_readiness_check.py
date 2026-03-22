from __future__ import annotations

from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = REPORTS_DIR / "pre_fast_readiness.txt"

# Based on your cleaned long-fast reference blocks
TARGETS = {
    "calories": (1700, 1850),
    "protein": (105, 125),
    "carbs": (100, 140),
    "fat": (80, 110),
    "steps": (5000, 9000),
    "sleep": (6.5, 8.5),
    "rhr": (60, 72),
    "hrv": (12, 25),
}


def fmt(x):
    if pd.isna(x):
        return "N/A"
    return f"{float(x):.2f}"


def check_range(value, low, high):
    if pd.isna(value):
        return "missing"
    if value < low:
        return "low"
    if value > high:
        return "high"
    return "good"


def main():
    con = duckdb.connect(str(DB_PATH))

    df = con.execute("""
        WITH recent_dates AS (
            SELECT date
            FROM analytics.daily_metrics
            WHERE date >= CURRENT_DATE - 7
            UNION
            SELECT date
            FROM clean.nutrition_daily
            WHERE date >= CURRENT_DATE - 7
        )
        SELECT
            d.date,
            dm.calories,
            dm.protein_g,
            n.carbs_g,
            n.fat_g,
            dm.steps,
            dm.sleep_hours,
            dm.resting_hr,
            dm.hrv,
            dm.hunger_score,
            dm.weight_kg
        FROM recent_dates d
        LEFT JOIN analytics.daily_metrics dm
            ON d.date = dm.date
        LEFT JOIN clean.nutrition_daily n
            ON d.date = n.date
        ORDER BY d.date
    """).fetchdf()

    con.close()

    if df.empty:
        print("No recent data found.")
        return

    avg = df.mean(numeric_only=True)

    results = {
        "calories": avg.get("calories"),
        "protein": avg.get("protein_g"),
        "carbs": avg.get("carbs_g"),
        "fat": avg.get("fat_g"),
        "steps": avg.get("steps"),
        "sleep": avg.get("sleep_hours"),
        "rhr": avg.get("resting_hr"),
        "hrv": avg.get("hrv"),
        "hunger": avg.get("hunger_score"),
    }

    evals = {}
    score = 0
    penalties = 0

    for k, v in results.items():
        if k not in TARGETS:
            continue

        low, high = TARGETS[k]
        status = check_range(v, low, high)
        evals[k] = status

        if status == "good":
            score += 2
        elif status == "missing":
            penalties += 1
        else:
            penalties += 1

    readiness = "UNKNOWN"

    if penalties >= 4:
        readiness = "❌ HIGH RISK (likely rebound / poor fast outcome)"
    elif score >= 10:
        readiness = "✅ READY TO FAST"
    else:
        readiness = "⚠️ NEEDS ADJUSTMENT"

    lines = []
    lines.append("Pre-Fast Readiness Check")
    lines.append("========================")
    lines.append("")

    lines.append("7-Day Averages")
    lines.append("--------------")
    for k, v in results.items():
        lines.append(f"{k:10}: {fmt(v)} ({evals.get(k, 'n/a')})")

    lines.append("")
    lines.append("Assessment")
    lines.append("----------")
    lines.append(f"Score: {score}")
    lines.append(f"Penalties: {penalties}")
    lines.append(f"Readiness: {readiness}")

    lines.append("")
    lines.append("Guidance")
    lines.append("--------")

    if readiness.startswith("❌"):
        lines.append("- Fix nutrition before starting a fast.")
        lines.append("- Increase protein and stabilize calories.")
        lines.append("- Avoid starting a fast in a chaotic state.")
    elif readiness.startswith("⚠️"):
        lines.append("- Adjust 1–2 variables before fasting.")
        lines.append("- Focus on protein and sleep first.")
        lines.append("- Avoid aggressive carb spikes.")
    else:
        lines.append("- You are well prepared.")
        lines.append("- Maintain current routine.")
        lines.append("- Start fast with confidence.")

    lines.append("")
    lines.append("Target Adjustments")
    lines.append("------------------")
    for k, status in evals.items():
        if status == "low":
            lines.append(f"- Increase {k}")
        elif status == "high":
            lines.append(f"- Reduce {k}")
        elif status == "missing":
            lines.append(f"- Track {k}")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")

    print(f"Saved: {OUT_PATH}")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()