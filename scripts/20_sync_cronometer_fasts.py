"""Cronometer fasting-history read-only proof of concept.

UNOFFICIAL mobile API. Requires account credentials supplied only through
secure environment variables. Default operation probes response *shape* and
never prints private fasting records or auth tokens.

The --sync option is intentionally conservative: it rejects unknown timestamp
formats rather than risk putting incorrect fasting windows in Neon.
Reference implementation: rwestergren/cronometer-api-mcp (MIT).
"""
from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

HOST = "https://mobile.cronometer.com"
BERLIN = ZoneInfo("Europe/Berlin")


def required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing secure environment variable {name}")
    return value


def login(session):
    # IMPORTANT: timezone=None avoids changing the user's Cronometer setting.
    payload = {
        "email": required("CRONOMETER_USERNAME"),
        "password": required("CRONOMETER_PASSWORD"),
        "timezone": None,
        "userCode": os.getenv("CRONOMETER_TOTP_CODE") or None,
        "build": "4.48.2 b2807-a",
        "device": "Android 14 (SDK 34), Google Pixel 6 Pro",
        "firebaseToken": "",
        "features": {
            "food_search_config": '{"newSearch": true, "newSpellcheck": true}',
            "use_gpt_autofill": "true",
        },
        "auth": {"userId": None, "token": None, "api": 3,
                 "os": "Android", "build": "2807", "flavour": "free"},
        "lastSeen": 0,
        "config": {"call_version": 2},
    }
    response = session.post(f"{HOST}/api/v2/login", json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    if "sessionKey" not in data or "id" not in data:
        raise RuntimeError("Cronometer authentication unsuccessful; credentials not logged")
    return int(data["id"]), str(data["sessionKey"])


def fetch_history(start: date, end: date, session=None):
    if end < start:
        raise ValueError("End before start")
    session = session or requests.Session()
    session.headers.update({"User-Agent": "Dart/3.9 (dart:io)",
                            "Content-Type": "text/plain; charset=utf-8"})
    user_id, token = login(session)
    payload = {
        "start": f"{start.year}-{start.month}-{start.day}",
        "end": f"{end.year}-{end.month}-{end.day}",
        "config": {"call_version": 1},
        "auth": {"userId": user_id, "token": token, "api": 3,
                 "os": "Android", "build": "2807", "flavour": "free"},
    }
    response = session.post(f"{HOST}/api/v2/get_fasting_with_date_range",
                            json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or data.get("result") in ("FAIL", "FAILURE"):
        raise RuntimeError("Fasting response unsuccessful or invalid")
    return data


def instant(value):
    """Only timezone-aware ISO dates or numeric epoch seconds/milliseconds."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        epoch = float(value)
        if epoch > 1e11:
            epoch /= 1000
        if epoch <= 0:
            return None
        return datetime.fromtimestamp(epoch, timezone.utc)
    if isinstance(value, str):
        value = value.strip()
        if value.isdecimal():
            return instant(int(value))
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
        except ValueError:
            pass
    return None


def first(record, names):
    for name in names:
        if record.get(name) not in (None, ""):
            return record[name]
    return None


def extract_fasts(payload):
    containers = [payload]
    for key in ("data", "fasting", "fasts", "history", "resultData"):
        if isinstance(payload.get(key), dict):
            containers.append(payload[key])
    items = None
    for container in containers:
        for key in ("fasts", "history", "fasting", "entries", "data"):
            if isinstance(container.get(key), list):
                items = container[key]
                break
        if items is not None:
            break
    if items is None:
        raise ValueError("Unknown fasting response structure; no records imported")
    rows = []
    for fast in items:
        if not isinstance(fast, dict):
            raise ValueError("Non-record fasting entry")
        fid = first(fast, ("id", "fastId", "fast_id"))
        start = instant(first(fast, ("start", "startTime", "start_time", "startTs", "startTimestamp")))
        raw_end = first(fast, ("end", "endTime", "end_time", "endTs", "endTimestamp"))
        end = instant(raw_end)
        if fid is None or start is None:
            raise ValueError("Unknown fasting ID/start timestamp; abort import")
        if raw_end not in (None, "", 0, "0") and end is None:
            raise ValueError("Unknown fasting end timestamp; abort import")
        if end is not None and end <= start:
            raise ValueError("Fasting end before start; abort import")
        rows.append((str(fid), start, end, str(first(fast, ("name", "title")) or "")[:250]))
    return rows


def persist(rows):
    import psycopg
    with psycopg.connect(required("WITHINGS_DATABASE_URL")) as conn, conn.cursor() as cur:
        conn.execute("""CREATE TABLE IF NOT EXISTS cronometer_fasting_intervals (
            fast_id TEXT PRIMARY KEY, start_at TIMESTAMPTZ NOT NULL,
            end_at TIMESTAMPTZ, name TEXT,
            source TEXT NOT NULL DEFAULT 'cronometer_mobile_read_only',
            synced_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        if rows:
            cur.executemany("""INSERT INTO cronometer_fasting_intervals
                (fast_id,start_at,end_at,name) VALUES (%s,%s,%s,%s)
                ON CONFLICT(fast_id) DO UPDATE SET start_at=excluded.start_at,
                end_at=excluded.end_at,name=excluded.name,synced_at=now()""", rows)
    print(f"Imported {len(rows)} Cronometer fasting intervals")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--sync", action="store_true",
                        help="Only after confirming real Cronometer response schema")
    args = parser.parse_args()
    if not 1 <= args.days <= 365:
        parser.error("--days must be 1..365")
    end = datetime.now(BERLIN).date()
    payload = fetch_history(end - timedelta(days=args.days - 1), end)
    if not args.sync:
        # Never print actual fasts, login details, access tokens, or response bodies.
        list_shapes = {k: len(v) for k, v in payload.items() if isinstance(v, list)}
        messages = payload.get("messages")
        message_shapes = []
        if isinstance(messages, list):
            for item in messages[:3]:
                message_shapes.append(sorted(item.keys()) if isinstance(item, dict)
                                      else type(item).__name__)
        print(f"Read-only fasting probe: keys={sorted(payload.keys())}; "
              f"list_counts={list_shapes}; message_shapes={message_shapes}")
        return
    persist(extract_fasts(payload))


if __name__ == "__main__":
    main()
