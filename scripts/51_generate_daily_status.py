from pathlib import Path

import duckdb
import pandas as pd


DB_PATH = Path("db/fitness.duckdb")
REPORTS_DIR = Path("reports")

REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def format_date(value) -> str:
    if pd.isna(value):
        return "N/A"
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def format_number(value, decimals: int = 2) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{float(value):.{decimals}f}"


def format_integer(value) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{int(round(float(value)))}"


def format_text(value) -> str:
    if pd.isna(value) or value is None:
        return "N/A"
    return str(value)


def main() -> None:
    con = duckdb.connect(str(DB_PATH))

    trends_df = con.execute("""
        SELECT *
        FROM analytics.daily_trends
        ORDER BY date DESC
    """).fetchdf()

    nutrition_df = con.execute("""
        SELECT
            date,
            calories,
            protein_g,
            carbs_g,
            fat_g,
            fiber_g,
            alcohol_g,
            source AS nutrition_source
        FROM clean.nutrition_daily
        ORDER BY date DESC
    """).fetchdf()

    con.close()

    if trends_df.empty:
        print("No daily trends found.")
        return

    merged = trends_df.merge(nutrition_df, on="date", how="left", suffixes=("", "_nutrition"))

    latest_date = merged["date"].max()
    latest_row = merged.loc[merged["date"] == latest_date].iloc[0]

    status = {
        "date": latest_row["date"],
        "weight_kg": latest_row.get("weight_kg"),
        "weight_7d_avg": latest_row.get("weight_7d_avg"),
        "fat_mass_kg": latest_row.get("fat_mass_kg"),
        "fat_mass_7d_avg": latest_row.get("fat_mass_7d_avg"),
        "lean_mass_kg": latest_row.get("lean_mass_kg"),
        "lean_mass_7d_avg": latest_row.get("lean_mass_7d_avg"),
        "visceral_fat": latest_row.get("visceral_fat"),
        "visceral_fat_7d_avg": latest_row.get("visceral_fat_7d_avg"),
        "steps": latest_row.get("steps"),
        "steps_7d_avg": latest_row.get("steps_7d_avg"),
        "sleep_hours": latest_row.get("sleep_hours"),
        "sleep_hours_7d_avg": latest_row.get("sleep_hours_7d_avg"),
        "resting_hr": latest_row.get("resting_hr"),
        "resting_hr_7d_avg": latest_row.get("resting_hr_7d_avg"),
        "hrv": latest_row.get("hrv"),
        "hrv_7d_avg": latest_row.get("hrv_7d_avg"),
        "calories": latest_row.get("calories"),
        "calories_7d_avg": latest_row.get("calories_7d_avg"),
        "protein_g": latest_row.get("protein_g"),
        "protein_g_7d_avg": latest_row.get("protein_g_7d_avg"),
        "carbs_g": latest_row.get("carbs_g"),
        "carbs_g_7d_avg": latest_row.get("carbs_g_7d_avg"),
        "fat_g": latest_row.get("fat_g"),
        "fat_g_7d_avg": latest_row.get("fat_g_7d_avg"),
        "fiber_g": latest_row.get("fiber_g"),
        "alcohol_g": latest_row.get("alcohol_g"),
        "fasting_state": latest_row.get("fasting_state"),
        "mounjaro_mg": latest_row.get("mounjaro_mg"),
        "hunger_score": latest_row.get("hunger_score"),
        "nutrition_source": latest_row.get("nutrition_source"),
    }

    status_df = pd.DataFrame([status])
    csv_path = REPORTS_DIR / "daily_status_latest.csv"
    txt_path = REPORTS_DIR / "daily_status_latest.txt"

    status_df.to_csv(csv_path, index=False)
    print(f"Saved daily status CSV to: {csv_path}")

    lines = [
        "Current Status",
        "--------------",
        f"date: {format_date(status['date'])}",
        "",
        "Body Composition",
        "----------------",
        f"weight_kg: {format_number(status['weight_kg'])}",
        f"weight_7d_avg: {format_number(status['weight_7d_avg'])}",
        f"fat_mass_kg: {format_number(status['fat_mass_kg'])}",
        f"fat_mass_7d_avg: {format_number(status['fat_mass_7d_avg'])}",
        f"lean_mass_kg: {format_number(status['lean_mass_kg'])}",
        f"lean_mass_7d_avg: {format_number(status['lean_mass_7d_avg'])}",
        f"visceral_fat: {format_number(status['visceral_fat'])}",
        f"visceral_fat_7d_avg: {format_number(status['visceral_fat_7d_avg'])}",
        "",
        "Activity / Recovery",
        "-------------------",
        f"steps: {format_integer(status['steps'])}",
        f"steps_7d_avg: {format_integer(status['steps_7d_avg'])}",
        f"sleep_hours: {format_number(status['sleep_hours'])}",
        f"sleep_hours_7d_avg: {format_number(status['sleep_hours_7d_avg'])}",
        f"resting_hr: {format_number(status['resting_hr'])}",
        f"resting_hr_7d_avg: {format_number(status['resting_hr_7d_avg'])}",
        f"hrv: {format_number(status['hrv'])}",
        f"hrv_7d_avg: {format_number(status['hrv_7d_avg'])}",
        "",
        "Nutrition",
        "---------",
        f"calories: {format_number(status['calories'])}",
        f"calories_7d_avg: {format_number(status['calories_7d_avg'])}",
        f"protein_g: {format_number(status['protein_g'])}",
        f"protein_g_7d_avg: {format_number(status['protein_g_7d_avg'])}",
        f"carbs_g: {format_number(status['carbs_g'])}",
        f"carbs_g_7d_avg: {format_number(status['carbs_g_7d_avg'])}",
        f"fat_g: {format_number(status['fat_g'])}",
        f"fat_g_7d_avg: {format_number(status['fat_g_7d_avg'])}",
        f"fiber_g: {format_number(status['fiber_g'])}",
        f"alcohol_g: {format_number(status['alcohol_g'])}",
        f"nutrition_source: {format_text(status['nutrition_source'])}",
        "",
        "Interventions",
        "-------------",
        f"fasting_state: {format_text(status['fasting_state'])}",
        f"mounjaro_mg: {format_number(status['mounjaro_mg'])}",
        f"hunger_score: {format_number(status['hunger_score'])}",
    ]

    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved daily status TXT to: {txt_path}")

    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()