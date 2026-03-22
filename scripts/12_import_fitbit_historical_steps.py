from __future__ import annotations

from pathlib import Path
from datetime import datetime, UTC
import re

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data_raw" / "historical" / "Fitbit" / "Physical Activity_GoogleData"
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"


def find_step_files() -> list[Path]:
    files = sorted({p.resolve() for p in DATA_DIR.glob("*steps*.csv")})
    files = [Path(p) for p in files]
    if not files:
        raise FileNotFoundError(f"No step CSV files found in {DATA_DIR}")
    return files


def extract_date_from_filename(path: Path):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    if not m:
        return None
    return pd.to_datetime(m.group(1), errors="coerce").date()


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def detect_steps_column(df: pd.DataFrame) -> str | None:
    candidates = ["value", "steps", "step", "step count", "step_count"]
    for c in candidates:
        if c in df.columns:
            return c

    for c in df.columns:
        if c in {"time", "timestamp", "date", "activityday", "starttime"}:
            continue
        sample = pd.to_numeric(df[c], errors="coerce")
        if sample.notna().sum() > 0:
            return c
    return None


def detect_date_series(df: pd.DataFrame, file_date):
    for c in ["date", "activityday", "day"]:
        if c in df.columns:
            parsed = pd.to_datetime(df[c], errors="coerce")
            if parsed.notna().sum() > 0:
                return parsed.dt.date

    for c in ["starttime", "timestamp", "datetime", "time"]:
        if c in df.columns:
            parsed = pd.to_datetime(df[c], errors="coerce")
            if parsed.notna().sum() > 0:
                return parsed.dt.date

    if file_date is not None:
        return pd.Series([file_date] * len(df), index=df.index)

    return pd.Series([pd.NaT] * len(df), index=df.index)


def load_one_file(file: Path) -> pd.DataFrame:
    print(f"Loading: {file.name}")

    df = pd.read_csv(file)
    raw_columns = list(df.columns)
    df = normalize_columns(df)

    file_date = extract_date_from_filename(file)
    steps_col = detect_steps_column(df)
    if steps_col is None:
        raise ValueError(
            f"Could not find steps column in {file.name}. "
            f"Columns seen: {raw_columns}"
        )

    date_series = detect_date_series(df, file_date)

    out = pd.DataFrame({
        "date": date_series,
        "steps": pd.to_numeric(df[steps_col], errors="coerce"),
    }).dropna(subset=["date", "steps"])

    if out.empty:
        print(f"  Warning: no usable rows found in {file.name}")
        print(f"  Raw columns: {raw_columns}")
        return out

    out = out.groupby("date", as_index=False)["steps"].sum()
    return out


def load_and_normalize(files: list[Path]) -> pd.DataFrame:
    dfs = []
    for file in files:
        one = load_one_file(file)
        if not one.empty:
            dfs.append(one)

    if not dfs:
        raise ValueError("No usable historical Fitbit step rows were parsed.")

    combined = pd.concat(dfs, ignore_index=True)
    combined = (
        combined.groupby("date", as_index=False)["steps"]
        .sum()
        .sort_values("date")
        .reset_index(drop=True)
    )
    return combined


def write_to_db(df: pd.DataFrame) -> None:
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        con.execute("""
            CREATE TABLE IF NOT EXISTS raw.fitbit_steps_historical (
                date DATE,
                steps DOUBLE,
                source VARCHAR,
                created_at TIMESTAMP
            )
        """)

        existing_cols = {
            row[0]
            for row in con.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'raw'
                  AND table_name = 'fitbit_steps_historical'
            """).fetchall()
        }

        if "source" not in existing_cols:
            con.execute("ALTER TABLE raw.fitbit_steps_historical ADD COLUMN source VARCHAR")
        if "created_at" not in existing_cols:
            con.execute("ALTER TABLE raw.fitbit_steps_historical ADD COLUMN created_at TIMESTAMP")

        con.execute("DELETE FROM raw.fitbit_steps_historical")

        df = df.copy()
        df["source"] = "fitbit_takeout_csv"
        df["created_at"] = datetime.now(UTC)

        con.register("fitbit_steps_hist_df", df)
        con.execute("""
            INSERT INTO raw.fitbit_steps_historical (date, steps, source, created_at)
            SELECT date, steps, source, created_at
            FROM fitbit_steps_hist_df
            ORDER BY date
        """)

        preview = con.execute("""
            SELECT *
            FROM raw.fitbit_steps_historical
            ORDER BY date DESC
            LIMIT 20
        """).fetchdf()

        print(f"\nInserted rows: {len(df)}")
        print(f"Date range: {df['date'].min()} -> {df['date'].max()}")
        print("\nPreview:")
        print(preview.to_string(index=False))

    finally:
        con.close()


def main() -> None:
    print("Finding Fitbit step files...")
    files = find_step_files()
    print(f"Found {len(files)} files.")

    df = load_and_normalize(files)

    print("\nCombined preview:")
    print(df.head(10).to_string(index=False))
    print(df.tail(10).to_string(index=False))

    write_to_db(df)


if __name__ == "__main__":
    main()