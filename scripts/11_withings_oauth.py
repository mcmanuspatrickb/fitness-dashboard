import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import duckdb
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"

load_dotenv(dotenv_path=ENV_PATH)

CLIENT_ID = os.getenv("WITHINGS_CLIENT_ID")
CLIENT_SECRET = os.getenv("WITHINGS_CLIENT_SECRET")
REDIRECT_URI = os.getenv("WITHINGS_REDIRECT_URI")

if not CLIENT_ID or not CLIENT_SECRET or not REDIRECT_URI:
    raise RuntimeError("Missing WITHINGS_CLIENT_ID, WITHINGS_CLIENT_SECRET, or WITHINGS_REDIRECT_URI in .env")

AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"
TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"

SCOPES = "user.info,user.metrics"

auth_code_holder = {"code": None}


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        query = parse_qs(parsed.query)
        code = query.get("code", [None])[0]
        auth_code_holder["code"] = code

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><h2>Withings authorization successful. You can close this window.</h2></body></html>")

    def log_message(self, format, *args):
        return


def run_server():
    server = HTTPServer(("localhost", 8000), CallbackHandler)
    server.handle_request()


def main():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": "fitness_dashboard",
    }

    url = f"{AUTH_URL}?{urlencode(params)}"
    print("Opening browser for Withings authorization...")
    print(url)
    webbrowser.open(url)

    server_thread.join(timeout=300)

    code = auth_code_holder["code"]
    if not code:
        raise RuntimeError("Authorization code was not received. Try again.")

    print("Authorization code received. Exchanging for tokens...")

    payload = {
        "action": "requesttoken",
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }

    response = requests.post(TOKEN_URL, data=payload, timeout=30)
    response.raise_for_status()
    data = response.json()

    if data.get("status") != 0:
        raise RuntimeError(f"Withings token request failed: {data}")

    body = data["body"]

    con = duckdb.connect(str(DB_PATH))
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
    con.close()

    print("Withings tokens stored successfully.")


if __name__ == "__main__":
    main()