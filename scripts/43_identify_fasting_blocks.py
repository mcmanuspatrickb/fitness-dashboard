from pathlib import Path

import duckdb
import pandas as pd


DB_PATH = Path("db/fitness.duckdb")
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_PATH = REPORTS_DIR / "fasting_blocks_analysis.csv"


def main() -> None:
    con = duckdb.connect(str(DB_PATH))

    df = con.execute("""
        SELECT
            date,
            fasting_state,
            fasting_hours,
            weight_kg,
            fat_mass_kg,
            lean_mass_kg,
            calories,
            protein_g,
            steps
        FROM analytics.daily_metrics
        ORDER BY date
    """).fetchdf()

    con.close()

    if df.empty:
        print("No daily metrics found.")
        pd.DataFrame().to_csv(OUTPUT_PATH, index=False)
        print("Saved fasting block analysis to:", OUTPUT_PATH)
        return

    df["date"] = pd.to_datetime(df["date"])
    df["fasting_state"] = df["fasting_state"].astype("string").str.strip().str.lower()

    # Keep only explicit fasting interventions
    df = df[df["fasting_state"].notna()].copy()
    df = df[df["fasting_state"] != "normal"].copy()
    df = df[df["fasting_state"] != ""].copy()

    if df.empty:
        print("No non-normal fasting blocks found.")
        pd.DataFrame(
            columns=[
                "fasting_state",
                "start_date",
                "end_date",
                "duration_days",
                "weight_change",
                "fat_change",
                "lean_change",
                "avg_calories",
                "avg_protein",
                "avg_steps",
                "min_required",
            ]
        ).to_csv(OUTPUT_PATH, index=False)
        print("Saved fasting block analysis to:", OUTPUT_PATH)
        return

    df["prev_date"] = df["date"].shift(1)
    df["prev_state"] = df["fasting_state"].shift(1)

    df["new_block"] = (
        (df["fasting_state"] != df["prev_state"]) |
        ((df["date"] - df["prev_date"]).dt.days != 1)
    ).fillna(True)

    df["block_id"] = df["new_block"].cumsum()

    rows = []
    for _, g in df.groupby("block_id"):
        g = g.sort_values("date").copy()

        start = g.iloc[0]
        end = g.iloc[-1]

        rows.append({
            "fasting_state": start["fasting_state"],
            "start_date": start["date"].date(),
            "end_date": end["date"].date(),
            "duration_days": int((end["date"] - start["date"]).days + 1),
            "weight_change": (
                end["weight_kg"] - start["weight_kg"]
                if pd.notna(start["weight_kg"]) and pd.notna(end["weight_kg"])
                else pd.NA
            ),
            "fat_change": (
                end["fat_mass_kg"] - start["fat_mass_kg"]
                if pd.notna(start["fat_mass_kg"]) and pd.notna(end["fat_mass_kg"])
                else pd.NA
            ),
            "lean_change": (
                end["lean_mass_kg"] - start["lean_mass_kg"]
                if pd.notna(start["lean_mass_kg"]) and pd.notna(end["lean_mass_kg"])
                else pd.NA
            ),
            "avg_calories": g["calories"].mean(),
            "avg_protein": g["protein_g"].mean(),
            "avg_steps": g["steps"].mean(),
            "min_required": 1,
        })

    out = pd.DataFrame(rows).sort_values(["start_date", "end_date"]).reset_index(drop=True)
    out.to_csv(OUTPUT_PATH, index=False)

    print("Saved fasting block analysis to:", OUTPUT_PATH)
    if not out.empty:
        print(out.head(20).to_string(index=False))
    else:
        print("No fasting blocks written.")


if __name__ == "__main__":
    main()