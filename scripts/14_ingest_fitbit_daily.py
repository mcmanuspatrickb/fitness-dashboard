from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone, timedelta
import os
import base64
import json

import duckdb
import pandas as pd
import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"

TOKEN_URL = "https://api.fitbit.com/oauth2/token"
API_BASE = "https://api.fitbit.com/1/user/-"


def env_present(name: str) -> bool:
    value = os.getenv(name)
    return value is not None and value.strip() != ""


def clean_env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip().strip('"').strip("'")
    return value or None


def mask_token(token: str | None, keep: int = 6) -> str:
    if not token:
        return "None"
    if len(token) <= keep * 2:
        return "*" * len(token)
    return f"{token[:keep]}...{token[-keep:]}"


def print_diagnostics() -> None:
    print("Fitbit environment diagnostics")
    print("-----------------------------")
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f".env path: {PROJECT_ROOT / '.env'}")
    print(f".env exists: {(PROJECT_ROOT / '.env').exists()}")
    print(f"DB path: {DB_PATH}")
    print(f"DB exists: {DB_PATH.exists()}")
    print(f"FITBIT_CLIENT_ID present: {env_present('FITBIT_CLIENT_ID')}")
    print(f"FITBIT_CLIENT_SECRET present: {env_present('FITBIT_CLIENT_SECRET')}")
    print(f"FITBIT_REFRESH_TOKEN present in .env: {env_present('FITBIT_REFRESH_TOKEN')}")
    print(f"FITBIT_REDIRECT_URI present: {env_present('FITBIT_REDIRECT_URI')}")
    print()


def get_connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH))


def ensure_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")

    con.execute("""
        CREATE TABLE IF NOT EXISTS raw.fitbit_tokens (
            refresh_token VARCHAR,
            created_at TIMESTAMP
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS raw.fitbit_daily (
            date DATE,
            steps DOUBLE,
            calories_burned DOUBLE,
            resting_hr DOUBLE,
            hrv DOUBLE,
            sleep_hours DOUBLE,
            active_minutes DOUBLE,
            sleep_efficiency DOUBLE,
            deep_sleep_minutes DOUBLE,
            rem_sleep_minutes DOUBLE,
            wake_minutes DOUBLE,
            sleep_score DOUBLE,
            sleep_restlessness DOUBLE,
            created_at TIMESTAMP
        )
    """)

    existing_cols = {
        row[0]
        for row in con.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'raw'
              AND table_name = 'fitbit_daily'
        """).fetchall()
    }

    wanted = {
        "sleep_efficiency": "DOUBLE",
        "deep_sleep_minutes": "DOUBLE",
        "rem_sleep_minutes": "DOUBLE",
        "wake_minutes": "DOUBLE",
        "sleep_score": "DOUBLE",
        "sleep_restlessness": "DOUBLE",
    }

    for col, dtype in wanted.items():
        if col not in existing_cols:
            con.execute(f"ALTER TABLE raw.fitbit_daily ADD COLUMN {col} {dtype}")


def get_stored_refresh_token(con: duckdb.DuckDBPyConnection) -> str | None:
    try:
        row = con.execute("""
            SELECT refresh_token
            FROM raw.fitbit_tokens
            WHERE refresh_token IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 1
        """).fetchone()
        if not row:
            return None
        token = str(row[0]).strip().strip('"').strip("'")
        return token or None
    except Exception:
        return None


def save_refresh_token(con: duckdb.DuckDBPyConnection, refresh_token: str) -> None:
    con.execute("""
        INSERT INTO raw.fitbit_tokens (refresh_token, created_at)
        VALUES (?, ?)
    """, [refresh_token, datetime.now(timezone.utc)])


def refresh_access_token() -> str:
    con = get_connection()
    try:
        ensure_tables(con)

        env_refresh = clean_env_value("FITBIT_REFRESH_TOKEN")
        db_refresh = get_stored_refresh_token(con)

        print(f"Stored refresh token present in DB: {db_refresh is not None}")
        print(f"Env refresh token preview: {mask_token(env_refresh)}")
        print(f"DB refresh token preview: {mask_token(db_refresh)}")

        refresh_token = env_refresh or db_refresh
        if not refresh_token:
            raise RuntimeError(
                "No Fitbit refresh token found in DB or environment. "
                "Check that .env contains FITBIT_REFRESH_TOKEN=..."
            )

        client_id = clean_env_value("FITBIT_CLIENT_ID")
        client_secret = clean_env_value("FITBIT_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise RuntimeError("Missing FITBIT_CLIENT_ID or FITBIT_CLIENT_SECRET in .env")

        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        response = requests.post(
            TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=30,
        )

        if not response.ok:
            print("\nFitbit token refresh failed")
            print("--------------------------")
            print(f"HTTP status: {response.status_code}")
            print(f"Response text: {response.text}")
            try:
                print("Response JSON:")
                print(json.dumps(response.json(), indent=2))
            except Exception:
                pass
            raise RuntimeError(
                "Fitbit token refresh failed. The refresh token is likely invalid/revoked "
                "or does not match the current Fitbit app credentials."
            )

        payload = response.json()

        access_token = payload["access_token"]
        new_refresh_token = payload.get("refresh_token")

        if new_refresh_token:
            save_refresh_token(con, new_refresh_token)

        print("Fitbit access token refreshed successfully.")
        return access_token

    finally:
        con.close()


def get_json(url: str, access_token: str) -> dict:
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_latest_raw_date(con: duckdb.DuckDBPyConnection):
    row = con.execute("SELECT MAX(date) FROM raw.fitbit_daily").fetchone()
    return row[0] if row and row[0] is not None else None


def build_steps_df(access_token: str, start_date: str, end_date: str) -> pd.DataFrame:
    url = f"{API_BASE}/activities/steps/date/{start_date}/{end_date}.json"
    data = get_json(url, access_token)
    rows = data.get("activities-steps", [])
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["date", "steps"])
    df["date"] = pd.to_datetime(df["dateTime"]).dt.date
    df["steps"] = pd.to_numeric(df["value"], errors="coerce")
    return df[["date", "steps"]]


def build_sleep_detail_df(access_token: str, start_date: str, end_date: str) -> pd.DataFrame:
    days = pd.date_range(start_date, end_date, freq="D")
    rows = []

    for day in days:
        ds = day.strftime("%Y-%m-%d")
        url = f"{API_BASE}/sleep/date/{ds}.json"
        try:
            data = get_json(url, access_token)
        except requests.HTTPError:
            rows.append({
                "date": pd.to_datetime(ds).date(),
                "sleep_hours": None,
                "sleep_efficiency": None,
                "deep_sleep_minutes": None,
                "rem_sleep_minutes": None,
                "wake_minutes": None,
            })
            continue

        sleeps = data.get("sleep", [])
        if not sleeps:
            rows.append({
                "date": pd.to_datetime(ds).date(),
                "sleep_hours": None,
                "sleep_efficiency": None,
                "deep_sleep_minutes": None,
                "rem_sleep_minutes": None,
                "wake_minutes": None,
            })
            continue

        main_sleep = next((s for s in sleeps if s.get("isMainSleep")), sleeps[0])

        duration_ms = main_sleep.get("duration")
        sleep_hours = (duration_ms / 1000 / 3600) if duration_ms is not None else None
        efficiency = main_sleep.get("efficiency")

        levels = main_sleep.get("levels", {}).get("summary", {})
        deep_minutes = levels.get("deep", {}).get("minutes")
        rem_minutes = levels.get("rem", {}).get("minutes")
        wake_minutes = levels.get("wake", {}).get("minutes")

        rows.append({
            "date": pd.to_datetime(ds).date(),
            "sleep_hours": sleep_hours,
            "sleep_efficiency": pd.to_numeric(efficiency, errors="coerce"),
            "deep_sleep_minutes": pd.to_numeric(deep_minutes, errors="coerce"),
            "rem_sleep_minutes": pd.to_numeric(rem_minutes, errors="coerce"),
            "wake_minutes": pd.to_numeric(wake_minutes, errors="coerce"),
        })

    return pd.DataFrame(rows)


def build_hrv_df(access_token: str, start_date: str, end_date: str) -> pd.DataFrame:
    days = pd.date_range(start_date, end_date, freq="D")
    rows = []

    for day in days:
        ds = day.strftime("%Y-%m-%d")
        url = f"{API_BASE}/hrv/date/{ds}.json"
        try:
            data = get_json(url, access_token)
        except requests.HTTPError:
            rows.append({"date": pd.to_datetime(ds).date(), "hrv": None})
            continue

        item = data.get("hrv", [{}])
        val = None
        if item:
            val = item[0].get("value", {}).get("rmssd")
        rows.append({"date": pd.to_datetime(ds).date(), "hrv": pd.to_numeric(val, errors="coerce")})

    return pd.DataFrame(rows)


def build_rhr_df(access_token: str, start_date: str, end_date: str) -> pd.DataFrame:
    days = pd.date_range(start_date, end_date, freq="D")
    rows = []

    for day in days:
        ds = day.strftime("%Y-%m-%d")
        url = f"{API_BASE}/activities/heart/date/{ds}/1d.json"
        try:
            data = get_json(url, access_token)
            summary = data.get("activities-heart", [{}])[0].get("value", {})
            rhr = summary.get("restingHeartRate")
        except requests.HTTPError:
            rhr = None

        rows.append({
            "date": pd.to_datetime(ds).date(),
            "resting_hr": pd.to_numeric(rhr, errors="coerce"),
        })

    return pd.DataFrame(rows)


def main() -> None:
    print_diagnostics()

    access_token = refresh_access_token()

    con = get_connection()
    try:
        ensure_tables(con)

        latest_raw_date = get_latest_raw_date(con)
        print(f"Latest raw Fitbit date in DB: {latest_raw_date}")

        today = datetime.now().date()
        if latest_raw_date is None:
               start_date = (today - timedelta(days=14)).isoformat()
        else:
                start_date = (latest_raw_date + timedelta(days=1)).isoformat()

        end_date = today.isoformat()
        print(f"Computed pull window: {start_date} -> {end_date}")

        if pd.to_datetime(start_date) > pd.to_datetime(end_date):
            print("No new Fitbit dates to pull.")
            return

        print(f"Pulling steps from {start_date} to {end_date}...")
        steps_df = build_steps_df(access_token, start_date, end_date)

        print(f"Pulling sleep details from {start_date} to {end_date}...")
        sleep_df = build_sleep_detail_df(access_token, start_date, end_date)

        print(f"Pulling HRV from {start_date} to {end_date}...")
        hrv_df = build_hrv_df(access_token, start_date, end_date)

        print(f"Pulling resting HR from {start_date} to {end_date}...")
        rhr_df = build_rhr_df(access_token, start_date, end_date)

        merged = pd.DataFrame({"date": pd.date_range(start_date, end_date, freq="D").date})
        for df in [steps_df, sleep_df, hrv_df, rhr_df]:
            merged = merged.merge(df, on="date", how="left")

        merged["calories_burned"] = None
        merged["active_minutes"] = None
        merged["sleep_score"] = None
        merged["sleep_restlessness"] = None
        merged["created_at"] = datetime.now(timezone.utc)

        merged = merged[
            [
                "date",
                "steps",
                "calories_burned",
                "resting_hr",
                "hrv",
                "sleep_hours",
                "active_minutes",
                "sleep_efficiency",
                "deep_sleep_minutes",
                "rem_sleep_minutes",
                "wake_minutes",
                "sleep_score",
                "sleep_restlessness",
                "created_at",
            ]
        ].copy()

        print("\nMerged Fitbit preview:")
        print(merged.head(10).to_string(index=False))

        con.register("fitbit_daily_new_df", merged)

        con.execute("""
            DELETE FROM raw.fitbit_daily
            WHERE date IN (SELECT date FROM fitbit_daily_new_df)
        """)

        con.execute("""
            INSERT INTO raw.fitbit_daily (
                date,
                steps,
                calories_burned,
                resting_hr,
                hrv,
                sleep_hours,
                active_minutes,
                sleep_efficiency,
                deep_sleep_minutes,
                rem_sleep_minutes,
                wake_minutes,
                sleep_score,
                sleep_restlessness,
                created_at
            )
            SELECT
                date,
                steps,
                calories_burned,
                resting_hr,
                hrv,
                sleep_hours,
                active_minutes,
                sleep_efficiency,
                deep_sleep_minutes,
                rem_sleep_minutes,
                wake_minutes,
                sleep_score,
                sleep_restlessness,
                created_at
            FROM fitbit_daily_new_df
            ORDER BY date
        """)

        preview = con.execute("""
            SELECT *
            FROM raw.fitbit_daily
            ORDER BY date DESC
            LIMIT 20
        """).fetchdf()

        print(f"\nIngested {len(merged)} Fitbit daily rows.")
        print(preview.to_string(index=False))

    finally:
        con.close()


if __name__ == "__main__":
    main()