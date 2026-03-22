import os
from pathlib import Path
from datetime import datetime, timezone

import duckdb
import pandas as pd
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"

load_dotenv(dotenv_path=ENV_PATH)

CLIENT_ID = os.getenv("WITHINGS_CLIENT_ID")
CLIENT_SECRET = os.getenv("WITHINGS_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    raise RuntimeError("Missing WITHINGS_CLIENT_ID or WITHINGS_CLIENT_SECRET in .env")

MEASURE_URL = "https://wbsapi.withings.net/measure"
TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"

WITHINGS_TYPES = {
    1: "weight_kg",
    6: "fat_percent",
    8: "fat_mass_kg",
    76: "muscle_mass_kg",
    77: "hydration_mass_kg",
    88: "bone_mass_kg",
    91: "pulse_wave_velocity",
    170: "visceral_fat",
    71: "muscle_percent",
    73: "body_water_percent",
}


def refresh_access_token(con):
    row = con.execute("""
        SELECT refresh_token
        FROM raw.withings_tokens
        WHERE provider = 'withings'
        ORDER BY obtained_at DESC
        LIMIT 1
    """).fetchone()

    if not row:
        raise RuntimeError("No Withings refresh token found. Run OAuth first.")

    refresh_token = row[0]

    payload = {
        "action": "requesttoken",
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
    }

    response = requests.post(TOKEN_URL, data=payload, timeout=30)
    response.raise_for_status()
    data = response.json()

    if data.get("status") != 0:
        raise RuntimeError(f"Withings token refresh failed: {data}")

    body = data["body"]

    con.execute("DELETE FROM raw.withings_tokens WHERE provider = 'withings'")
    con.execute("""
        INSERT INTO raw.withings_tokens (
            provider,
            access_token,
            refresh_token,
            token_type,
            scope,
            expires_in
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, [
        "withings",
        body["access_token"],
        body["refresh_token"],
        body.get("token_type"),
        body.get("scope"),
        body.get("expires_in"),
    ])

    return body["access_token"]


def fetch_all_measurements(access_token):
    offset = 0
    all_groups = []

    while True:
        params = {
            "action": "getmeas",
            "access_token": access_token,
            "category": 1,
            "offset": offset,
        }

        response = requests.get(MEASURE_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != 0:
            raise RuntimeError(f"Withings measure API failed: {data}")

        body = data.get("body", {})
        groups = body.get("measuregrps", [])
        all_groups.extend(groups)

        more = body.get("more", 0)
        if more != 1:
            break

        offset = body.get("offset", 0)

    return all_groups


def transform_measure_groups(groups):
    rows = []

    for grp in groups:
        ts = grp.get("date")
        if ts is None:
            continue

        measurement_time = datetime.fromtimestamp(ts, tz=timezone.utc)
        row = {
            "measurement_time": measurement_time,
            "date": measurement_time.date(),
            "weight_kg": None,
            "fat_percent": None,
            "fat_mass_kg": None,
            "muscle_percent": None,
            "muscle_mass_kg": None,
            "body_water_percent": None,
            "visceral_fat": None,
            "bone_mass_kg": None,
            "source": "withings_api",
        }

        for measure in grp.get("measures", []):
            mtype = measure.get("type")
            value = measure.get("value")
            unit = measure.get("unit")

            if mtype not in WITHINGS_TYPES:
                continue

            field = WITHINGS_TYPES[mtype]
            real_value = value * (10 ** unit)

            # Convert hydration mass to body_water_percent only if that exact field exists elsewhere later.
            # For now we only store known table columns.
            if field in row:
                row[field] = real_value

        rows.append(row)

    return pd.DataFrame(rows)


def main():
    con = duckdb.connect(str(DB_PATH))

    access_token = refresh_access_token(con)
    print("Access token refreshed.")

    groups = fetch_all_measurements(access_token)
    print(f"Fetched {len(groups)} Withings measurement groups.")

    df = transform_measure_groups(groups)

    if df.empty:
        print("No Withings measurements returned.")
        con.close()
        return

    con.register("withings_df", df)

    con.execute("DELETE FROM raw.withings_measurements")

    con.execute("""
        INSERT INTO raw.withings_measurements (
            measurement_time,
            date,
            weight_kg,
            fat_percent,
            fat_mass_kg,
            muscle_percent,
            muscle_mass_kg,
            body_water_percent,
            visceral_fat,
            bone_mass_kg,
            source
        )
        SELECT
            measurement_time,
            date,
            weight_kg,
            fat_percent,
            fat_mass_kg,
            muscle_percent,
            muscle_mass_kg,
            body_water_percent,
            visceral_fat,
            bone_mass_kg,
            source
        FROM withings_df
        ORDER BY measurement_time
    """)

    count = con.execute("SELECT COUNT(*) FROM raw.withings_measurements").fetchone()[0]
    preview = con.execute("""
        SELECT measurement_time, date, weight_kg, fat_percent, fat_mass_kg, muscle_mass_kg, visceral_fat
        FROM raw.withings_measurements
        ORDER BY measurement_time DESC
        LIMIT 10
    """).fetchdf()

    con.close()

    print(f"Inserted {count} rows into raw.withings_measurements.")
    print(preview)


if __name__ == "__main__":
    main()