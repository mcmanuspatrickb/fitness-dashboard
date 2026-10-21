"""Compare dated extended-fasting blocks and the documented nutrition between them.

No eating is inferred from a missing log, and follow-up weight is not attributed to
an earlier fast when another extended-fast block intervened.
Generated reports are ignored by Git and must not be committed to public repos.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "fitness.duckdb"
OUT_CSV = ROOT / "reports" / "historical_fast_refeed_cycles.csv"
OUT_TXT = ROOT / "reports" / "historical_fast_refeed_cycles.txt"
COLUMNS = [
    "start_date", "end_date", "fast_days_labelled", "fast_category",
    "start_weight_kg", "end_weight_kg", "fast_scale_change_kg",
    "next_fast_start", "non_fast_interval_days", "logged_intake_days",
    "avg_logged_calories", "avg_logged_protein_g",
    "weight_after_7d_kg", "weight_after_28d_kg",
    "net_scale_change_7d_kg", "net_scale_change_28d_kg",
]


def analyze(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["fasting_state"] = (
        df["fasting_state"].astype("string").str.strip().str.lower()
        .replace({"ef": "extended_fast", "extended fast": "extended_fast",
                  "extended fasting": "extended_fast"})
    )
    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    by_date = df.set_index("date")
    fast = df[df["fasting_state"].eq("extended_fast").fillna(False)].copy()
    if fast.empty:
        return pd.DataFrame(columns=COLUMNS)
    fast["block"] = fast["date"].diff().dt.days.ne(1).cumsum()
    blocks = [g for _, g in fast.groupby("block", sort=True)]
    rows = []
    for pos, g in enumerate(blocks):
        start = g["date"].iloc[0]
        end = g["date"].iloc[-1]
        next_start = blocks[pos + 1]["date"].iloc[0] if pos + 1 < len(blocks) else None
        interval_end = min(
            end + pd.Timedelta(days=28),
            next_start - pd.Timedelta(days=1) if next_start is not None
            else end + pd.Timedelta(days=28),
        )
        interval = df[(df["date"] > end) & (df["date"] <= interval_end)]
        intake = interval[interval["calories"].notna()]
        start_w = by_date.at[start, "weight_kg"]
        end_w = by_date.at[end, "weight_kg"]

        def follow(days: int):
            target = end + pd.Timedelta(days=days)
            if (next_start is not None and next_start <= target) or target not in by_date.index:
                return float("nan")
            return by_date.at[target, "weight_kg"]

        seven, twenty_eight = follow(7), follow(28)
        rows.append({
            "start_date": start.date().isoformat(),
            "end_date": end.date().isoformat(),
            "fast_days_labelled": len(g),
            "fast_category": "3-day-or-shorter" if len(g) <= 3 else
                             ("7+-day" if len(g) >= 7 else "4-to-6-day"),
            "start_weight_kg": start_w,
            "end_weight_kg": end_w,
            "fast_scale_change_kg": end_w - start_w,
            "next_fast_start": next_start.date().isoformat() if next_start is not None else None,
            "non_fast_interval_days": max(0, (interval_end - end).days),
            "logged_intake_days": len(intake),
            "avg_logged_calories": intake["calories"].mean(),
            "avg_logged_protein_g": intake["protein_g"].mean(),
            "weight_after_7d_kg": seven,
            "weight_after_28d_kg": twenty_eight,
            "net_scale_change_7d_kg": seven - start_w,
            "net_scale_change_28d_kg": twenty_eight - start_w,
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def main() -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute("""
            SELECT d.date, i.fasting_state, d.weight_kg,
                   d.fat_mass_kg, d.lean_mass_kg,
                   n.calories, n.protein_g
            FROM analytics.daily_metrics d
            LEFT JOIN clean.interventions_daily i ON d.date = i.date
            LEFT JOIN clean.nutrition_daily n ON d.date = n.date
            ORDER BY d.date
        """).fetchdf()
    finally:
        con.close()
    result = analyze(df)
    result.to_csv(OUT_CSV, index=False)
    lines = ["Historical fasting and between-fast nutrition review",
             "==================================================", ""]
    if result.empty:
        lines.append("WARNING: No explicitly labelled extended-fasting blocks were imported.")
        lines.append("This is a data-coverage gap, not evidence that no fasting occurred.")
    else:
        lines.append(f"Labelled fasting blocks: {len(result)}")
        for _, row in result.iterrows():
            lines.append(
                f"{row['start_date']} to {row['end_date']}: {int(row['fast_days_labelled'])} "
                f"days, category={row['fast_category']}; "
                f"non-fast interval={int(row['non_fast_interval_days'])} days, "
                f"logged nutrition days={int(row['logged_intake_days'])}"
            )
        lines.append("")
        lines.append("Missing food logs are UNKNOWN, not zero-calorie days.")
        lines.append("7/28-day follow-ups are blank if another fast intervened.")
        lines.append("Body-composition scale estimates may shift with hydration.")
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"Saved: {OUT_CSV} and {OUT_TXT}")


if __name__ == "__main__":
    main()
