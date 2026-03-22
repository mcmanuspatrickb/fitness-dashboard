from pathlib import Path

import duckdb
import pandas as pd
import matplotlib.pyplot as plt


DB_PATH = Path("db/fitness.duckdb")
REPORTS_DIR = Path("reports")

REPORTS_DIR.mkdir(parents=True, exist_ok=True)

DATE_COLUMNS = {"week_start"}

INTEGER_COLUMNS = {
    "avg_steps",
}

DECIMAL_2_COLUMNS = {
    "avg_weight",
    "avg_fat_mass",
    "avg_lean_mass",
    "avg_sleep",
    "avg_resting_hr",
    "avg_hrv",
    "weight_change",
    "fat_mass_change",
    "lean_mass_change",
    "mounjaro_mg_mode",
    "avg_hunger_score",
}

TEXT_COLUMNS = {
    "fasting_state_mode",
}


def save_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    output_path: Path,
) -> None:
    chart_df = df[[x_col, y_col]].dropna().copy()

    if chart_df.empty:
        print(f"Skipped chart (no data): {output_path}")
        return

    plt.figure(figsize=(10, 5))
    plt.plot(chart_df[x_col], chart_df[y_col], marker="o")
    plt.title(title)
    plt.xlabel(x_col)
    plt.ylabel(y_col)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def row_is_complete(row: pd.Series) -> bool:
    core_fields = [
        "avg_weight",
        "avg_steps",
        "avg_sleep",
        "avg_resting_hr",
    ]
    return any(pd.notna(row.get(col)) for col in core_fields)


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


def format_value(column: str, value) -> str:
    if column in DATE_COLUMNS:
        return format_date(value)

    if column in INTEGER_COLUMNS:
        return format_integer(value)

    if column in DECIMAL_2_COLUMNS:
        return format_number(value, 2)

    if column in TEXT_COLUMNS:
        return "N/A" if pd.isna(value) else str(value)

    if pd.isna(value):
        return "N/A"

    if isinstance(value, (int, float)):
        return format_number(value, 2)

    return str(value)


def print_summary(title: str, row: pd.Series) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    for col, value in row.items():
        print(f"{col}: {format_value(col, value)}")


def main() -> None:
    con = duckdb.connect(str(DB_PATH))

    weekly_df = con.execute("""
        SELECT *
        FROM analytics.weekly_metrics
        ORDER BY week_start DESC
    """).fetchdf()

    con.close()

    if weekly_df.empty:
        print("No weekly metrics found.")
        return

    weekly_csv_path = REPORTS_DIR / "weekly_metrics_latest.csv"
    weekly_df.to_csv(weekly_csv_path, index=False)
    print(f"Saved weekly metrics CSV to: {weekly_csv_path}")

    chart_df = weekly_df.sort_values("week_start").copy()

    save_chart(
        chart_df,
        "week_start",
        "avg_weight",
        "Weekly Average Weight",
        REPORTS_DIR / "chart_weight_trend.png",
    )
    save_chart(
        chart_df,
        "week_start",
        "avg_steps",
        "Weekly Average Steps",
        REPORTS_DIR / "chart_steps_trend.png",
    )
    save_chart(
        chart_df,
        "week_start",
        "avg_resting_hr",
        "Weekly Average Resting HR",
        REPORTS_DIR / "chart_resting_hr_trend.png",
    )

    latest_row = weekly_df.iloc[0]
    complete_candidates = weekly_df[weekly_df.apply(row_is_complete, axis=1)]

    latest_complete_row = None
    if not complete_candidates.empty:
        latest_complete_row = complete_candidates.iloc[0]

    print("\nLatest Weekly Summary")
    print("---------------------")

    if row_is_complete(latest_row):
        for col, value in latest_row.items():
            print(f"{col}: {format_value(col, value)}")
    else:
        print("Latest week is partial / incomplete.")
        print(f"current_week_start: {format_value('week_start', latest_row['week_start'])}")

        if latest_complete_row is not None:
            print_summary("Latest Complete Week", latest_complete_row)
        else:
            print("No complete week found yet.")

        print_summary("Current Partial Week", latest_row)


if __name__ == "__main__":
    main()