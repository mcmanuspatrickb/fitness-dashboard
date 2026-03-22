from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import base64
import os
import webbrowser

import duckdb
import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"

FITBIT_CLIENT_ID = os.getenv("FITBIT_CLIENT_ID", "").strip().strip('"').strip("'")
FITBIT_CLIENT_SECRET = os.getenv("FITBIT_CLIENT_SECRET", "").strip().strip('"').strip("'")
FITBIT_REDIRECT_URI = os.getenv("FITBIT_REDIRECT_URI", "").strip().strip('"').strip("'")

AUTHORIZE_URL = "https://www.fitbit.com/oauth2/authorize"
TOKEN_URL = "https://api.fitbit.com/oauth2/token"

SCOPES = [
    "activity",
    "heartrate",
    "sleep",
    "profile",
]


def ensure_token_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute("""
        CREATE TABLE IF NOT EXISTS raw.fitbit_tokens (
            provider VARCHAR,
            access_token VARCHAR,
            refresh_token VARCHAR,
            created_at TIMESTAMP
        )
    """)

    existing_cols = {
        row[0]
        for row in con.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'raw'
              AND table_name = 'fitbit_tokens'
        """).fetchall()
    }

    wanted = {
        "provider": "VARCHAR",
        "access_token": "VARCHAR",
        "refresh_token": "VARCHAR",
        "created_at": "TIMESTAMP",
    }

    for col, dtype in wanted.items():
        if col not in existing_cols:
            con.execute(f"ALTER TABLE raw.fitbit_tokens ADD COLUMN {col} {dtype}")


def build_authorization_url() -> str:
    if not FITBIT_CLIENT_ID:
        raise RuntimeError("FITBIT_CLIENT_ID is missing from .env")
    if not FITBIT_REDIRECT_URI:
        raise RuntimeError("FITBIT_REDIRECT_URI is missing from .env")

    scope_str = "+".join(SCOPES)
    return (
        f"{AUTHORIZE_URL}"
        f"?client_id={FITBIT_CLIENT_ID}"
        f"&response_type=code"
        f"&scope={scope_str}"
        f"&redirect_uri={requests.utils.quote(FITBIT_REDIRECT_URI, safe='')}"
        f"&expires_in=604800"
    )


def exchange_code_for_tokens(code: str) -> dict:
    if not FITBIT_CLIENT_ID or not FITBIT_CLIENT_SECRET:
        raise RuntimeError("FITBIT_CLIENT_ID / FITBIT_CLIENT_SECRET missing from .env")

    basic = base64.b64encode(
        f"{FITBIT_CLIENT_ID}:{FITBIT_CLIENT_SECRET}".encode("utf-8")
    ).decode("utf-8")

    response = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "client_id": FITBIT_CLIENT_ID,
            "grant_type": "authorization_code",
            "redirect_uri": FITBIT_REDIRECT_URI,
            "code": code,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def store_tokens(body: dict) -> None:
    access_token = body.get("access_token")
    refresh_token = body.get("refresh_token")

    if not access_token or not refresh_token:
        raise RuntimeError(
            "OAuth token response did not include access_token and refresh_token."
        )

    con = duckdb.connect(str(DB_PATH))
    try:
        ensure_token_table(con)

        con.execute("DELETE FROM raw.fitbit_tokens WHERE provider = 'fitbit'")
        con.execute("""
            INSERT INTO raw.fitbit_tokens (
                provider,
                access_token,
                refresh_token,
                created_at
            )
            VALUES (?, ?, ?, ?)
        """, [
            "fitbit",
            access_token,
            refresh_token,
            datetime.now(timezone.utc),
        ])
    finally:
        con.close()


def main() -> None:
    auth_url = build_authorization_url()

    print("Opening browser for Fitbit authorization...")
    print(auth_url)
    webbrowser.open(auth_url)

    code = input(
        "\nPaste the Fitbit authorization code from the callback URL here:\n> "
    ).strip()

    if not code:
        raise RuntimeError("No authorization code was provided.")

    print("Authorization code received. Exchanging for tokens...")
    body = exchange_code_for_tokens(code)

    store_tokens(body)

    print("Fitbit tokens stored successfully.")


if __name__ == "__main__":
    main()