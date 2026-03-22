from __future__ import annotations

from pathlib import Path
import re

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_ROOT / "data_raw" / "interventions" / "historical_fasting.csv"
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"

PRIORITY = {
    "EF": 5,
    "OMAD": 4,
    "IF": 3,
    "NORMAL": 2,
    "BASELINE": 1,
}


def load_file(path: Path) -> pd.DataFrame:
    for sep in [";", "\t", ","]:
        try:
            df = pd.read_csv(path, sep=sep)
            if len(df.columns) > 1:
                print(f"Detected delimiter: {repr(sep)}")
                return df
        except Exception:
            pass
    raise ValueError(f"Could not parse file with expected delimiters: {path}")


def normalize_fasting_state(value: object) -> str | None:
    if pd.isna(value):
        return None

    raw = str(value).strip()
    if not raw:
        return None

    upper = raw.upper()

    mapping = {
        "BASELINE": "normal",
        "NORMAL": "normal",
        "FED": "normal",
        "NONE": "normal",
        "IF": "if",
        "INTERMITTENT FASTING": "if",
        "EF": "ef",
        "EXTENDED FAST": "ef",
        "EXTENDED FASTING": "ef",
        "OMAD": "omad",
    }

    if upper in mapping:
        return mapping[upper]

    if re.match(r"^\d{1,2}\s*[:/\-]\s*\d{1,2}$", raw):
        return "if"

    return raw.lower()


def infer_fasting_hours(value: object) -> float | None:
    if pd.isna(value):
        return None

    raw = str(value).strip()
    if not raw:
        return None

    upper = raw.upper()

    if upper == "OMAD":
        return 23.0
    if upper == "IF":
        return 16.0
    if upper == "EF":
        return 36.0

    m = re.match(r"^\s*(\d{1,2})\s*[:/\-]\s*(\d{1,2})\s*$", raw)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None

    return None


def habit_priority(value: object) -> int:
    if pd.isna(value):
        return 0
    return PRIORITY.get(str(value).strip().upper(), 0)


def build_daily_rows(df: pd.DataFrame) -> pd.DataFrame:
    # choose strongest fasting label per day:
    # EF > OMAD > IF > Normal > Baseline
    ranked = df.copy()
    ranked["priority"] = ranked["Eating Habits"].apply(habit_priority)

    ranked = ranked.sort_values(
        by=["date", "priority", "Meal"],
        ascending=[True, False, True],
        na_position="last",
    )

    best = ranked.drop_duplicates(subset=["date"], keep="first").copy()

    best["fasting_state"] = best["Eating Habits"].apply(normalize_fasting_state)
    best["fasting_hours"] = best["Eating Habits"].apply(infer_fasting_hours)
    best["mounjaro_mg"] = None
    best["hunger_score"] = None
    best["notes"] = best["Eating Habits"].apply(
        lambda x: f"historical_fasting_import: {x}" if pd.notna(x) else "historical_fasting_import"
    )

    out = best[
        ["date", "fasting_state", "fasting_hours", "mounjaro_mg", "hunger_score", "notes"]
    ].copy()

    out = out.dropna(subset=["date"])
    out = out[
        out["fasting_state"].notna() | out["fasting_hours"].notna()
    ].copy()

    out = out.sort_values("date").reset_index(drop=True)
    return out


def ensure_raw_interventions_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute("""
        CREATE TABLE IF NOT EXISTS raw.interventions_daily (
            date DATE,
            fasting_state VARCHAR,
            fasting_hours DOUBLE,
            mounjaro_mg DOUBLE,
            hunger_score INTEGER,
            notes VARCHAR
        )
    """)


def main() -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Historical fasting file not found: {CSV_PATH}")

    print(f"Loading historical fasting CSV: {CSV_PATH}")
    df = load_file(CSV_PATH)
    print(f"Loaded {len(df)} meal-level rows.")

    print("\nColumns found:")
    for c in df.columns:
        print(f" - {c}")

    required_cols = ["Date", "Eating Habits"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce").dt.date
    df = df.dropna(subset=["date"]).copy()

    out = build_daily_rows(df)

    print("\nNormalized daily preview:")
    print(out.head(30).to_string(index=False))

    print("\nSample around 2019-10-23:")
    sample = out[
        (out["date"] >= pd.to_datetime("2019-10-20").date()) &
        (out["date"] <= pd.to_datetime("2019-10-30").date())
    ]
    if not sample.empty:
        print(sample.to_string(index=False))
    else:
        print("No rows found in sample range.")

    print(f"\nImport date range: {out['date'].min()} -> {out['date'].max()}")
    print(f"Rows to import: {len(out)}")

    con = duckdb.connect(str(DB_PATH))
    try:
        ensure_raw_interventions_table(con)
        con.register("historical_fasting_df", out)

        con.execute("""
            DELETE FROM raw.interventions_daily
            WHERE date IN (
                SELECT date
                FROM historical_fasting_df
            )
            AND notes LIKE 'historical_fasting_import:%'
        """)

        con.execute("""
            INSERT INTO raw.interventions_daily (
                date,
                fasting_state,
                fasting_hours,
                mounjaro_mg,
                hunger_score,
                notes
            )
            SELECT
                date,
                fasting_state,
                fasting_hours,
                mounjaro_mg,
                hunger_score,
                notes
            FROM historical_fasting_df
            ORDER BY date
        """)

        preview = con.execute("""
            SELECT *
            FROM raw.interventions_daily
            WHERE notes LIKE 'historical_fasting_import:%'
            ORDER BY date DESC
            LIMIT 30
        """).fetchdf()

        check_2019 = con.execute("""
            SELECT date, fasting_state, fasting_hours, notes
            FROM raw.interventions_daily
            WHERE date BETWEEN DATE '2019-10-20' AND DATE '2019-10-30'
            ORDER BY date
        """).fetchdf()

        print("\nImported historical fasting preview:")
        print(preview.to_string(index=False))

        print("\nImported check around 2019-10-23:")
        if not check_2019.empty:
            print(check_2019.to_string(index=False))
        else:
            print("No imported rows found in sample range.")

    finally:
        con.close()


if __name__ == "__main__":
    main()