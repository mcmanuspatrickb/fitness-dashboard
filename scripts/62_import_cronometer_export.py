from pathlib import Path
import subprocess
import sys

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
CRONOMETER_DIR = PROJECT_ROOT / "data_raw" / "current" / "cronometer"


def newest_csv_path() -> Path:
    csvs = sorted(
        CRONOMETER_DIR.glob("*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not csvs:
        raise FileNotFoundError(
            f"No Cronometer CSV files found in: {CRONOMETER_DIR}"
        )
    return csvs[0]


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def require_columns(df: pd.DataFrame, required: list[str]) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required Cronometer columns: {missing}")


def to_numeric_or_none(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def map_cronometer_to_canonical(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map Cronometer Daily Nutrition export columns into raw.nutrition_daily schema.
    """

    df = normalize_columns(df)

    required = [
        "Date",
        "Energy (kcal)",
        "Protein (g)",
        "Carbs (g)",
        "Fat (g)",
        "Fiber (g)",
        "Alcohol (g)",
    ]
    require_columns(df, required)

    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df["Date"], errors="coerce").dt.date,
            "calories": to_numeric_or_none(df["Energy (kcal)"]),
            "protein_g": to_numeric_or_none(df["Protein (g)"]),
            "carbs_g": to_numeric_or_none(df["Carbs (g)"]),
            "fat_g": to_numeric_or_none(df["Fat (g)"]),
            "fiber_g": to_numeric_or_none(df["Fiber (g)"]),
            "alcohol_g": to_numeric_or_none(df["Alcohol (g)"]),
            "source": "cronometer_export",
        }
    )

    # Drop rows without a valid date
    out = out.dropna(subset=["date"]).copy()

    # If duplicate dates somehow appear in the export, keep the last row
    out = (
        out.sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .reset_index(drop=True)
    )

    return out


def import_into_raw(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    if df.empty:
        print("Mapped Cronometer dataset is empty. Nothing to import.")
        return

    min_date = df["date"].min()
    max_date = df["date"].max()

    print(f"Import date range: {min_date} -> {max_date}")
    print(f"Rows to import: {len(df)}")

    con.register("cronometer_import_df", df)

    # Idempotent delete only for this source and date window
    con.execute(
        """
        DELETE FROM raw.nutrition_daily
        WHERE source = 'cronometer_export'
          AND date BETWEEN ? AND ?
        """,
        [min_date, max_date],
    )

    con.execute(
        """
        INSERT INTO raw.nutrition_daily (
            date,
            calories,
            protein_g,
            carbs_g,
            fat_g,
            fiber_g,
            alcohol_g,
            source
        )
        SELECT
            date,
            calories,
            protein_g,
            carbs_g,
            fat_g,
            fiber_g,
            alcohol_g,
            source
        FROM cronometer_import_df
        ORDER BY date
        """
    )


def preview_import(con: duckdb.DuckDBPyConnection) -> None:
    preview = con.execute(
        """
        SELECT
            date,
            calories,
            protein_g,
            carbs_g,
            fat_g,
            fiber_g,
            alcohol_g,
            source
        FROM raw.nutrition_daily
        WHERE source = 'cronometer_export'
        ORDER BY date DESC
        LIMIT 10
        """
    ).fetchdf()

    print("\nImported Cronometer preview:")
    print(preview.to_string(index=False))


def run_downstream_scripts() -> None:
    downstream_scripts = [
        "24_build_clean_nutrition_daily.py",
        "30_build_daily_metrics.py",
        "41_build_historical_daily_metrics.py",
        "40_build_weekly_metrics.py",
    ]

    print("\nRebuilding downstream tables...")
    for script_name in downstream_scripts:
        script_path = PROJECT_ROOT / "scripts" / script_name
        print(f"\nRunning {script_name}...")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=PROJECT_ROOT,
            check=True,
        )
        if result.returncode == 0:
            print(f"Finished {script_name}")


def main() -> None:
    print("Starting Cronometer import...")

    if not CRONOMETER_DIR.exists():
        raise FileNotFoundError(f"Cronometer directory not found: {CRONOMETER_DIR}")

    if not DB_PATH.exists():
        raise FileNotFoundError(f"DuckDB database not found: {DB_PATH}")

    csv_path = newest_csv_path()
    print(f"Using newest CSV: {csv_path.name}")

    df_raw = pd.read_csv(csv_path)
    print(f"CSV rows: {len(df_raw)}")

    print("\nCSV columns:")
    for col in df_raw.columns:
        print(f" - {col}")

    df_mapped = map_cronometer_to_canonical(df_raw)

    print("\nMapped preview:")
    if df_mapped.empty:
        print("No valid rows after mapping.")
    else:
        print(df_mapped.head(10).to_string(index=False))

    con = duckdb.connect(str(DB_PATH))
    try:
        import_into_raw(con, df_mapped)
        preview_import(con)
    finally:
        con.close()

    run_downstream_scripts()

    print("\nCronometer import complete.")


if __name__ == "__main__":
    main()