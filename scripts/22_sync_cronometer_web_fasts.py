"""Read-only Cronometer web fasting history -> private Neon, manual runs only.

The upstream GWT-RPC reader is pinned in the workflow. This code does NOT
change any Cronometer account data and never prints raw timestamps/records,
secrets, session cookies, or HTTP response bodies to GitHub logs.
"""
from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
GWT_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789$_"


def decode_gwt_long(raw: str | None) -> datetime | None:
    """GWT's base-64-encoded 64-bit epoch milliseconds, NOT ordinary base64/base62."""
    if raw in (None, "", "0"):
        return None
    if not isinstance(raw, str) or not 4 <= len(raw) <= 11:
        raise ValueError("Invalid encoded timestamp")
    number = 0
    for char in raw:
        if char not in GWT_ALPHABET:
            raise ValueError("Unexpected encoded timestamp character")
        number = number * 64 + GWT_ALPHABET.index(char)
    # Signed 64-bit base64 long: reject implausible millisecond epochs.
    if not 946684800000 <= number <= 4102444800000:
        raise ValueError("Decoded timestamp outside permitted 2000-2100 window")
    return datetime.fromtimestamp(number / 1000, timezone.utc)


def normalize(records: list[dict]) -> list[tuple]:
    if not isinstance(records, list) or not records:
        raise ValueError("Empty fasting history: abort rather than erase data")
    rows = []
    ids = set()
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("Non-object fasting history record")
        ident = item.get("fast_id")
        if not isinstance(ident, int) or ident <= 0 or str(ident) in ids:
            raise ValueError("Missing, invalid or duplicate fasting ID")
        ids.add(str(ident))
        start = decode_gwt_long(item.get("start_ts"))
        end = decode_gwt_long(item.get("end_ts"))
        if start is None:
            raise ValueError("Missing fasting start")
        active = bool(item.get("is_active", False))
        if active and end is not None:
            raise ValueError("Active fast has end timestamp")
        if not active and end is None:
            raise ValueError("Completed fast has no end timestamp")
        if end and (end <= start or end - start > timedelta(days=90)):
            raise ValueError("Invalid fasting duration")
        name = str(item.get("name") or "")[:250]
        rows.append((str(ident), start, end, name))
    return rows


def validated_against_screenshots(rows: list[tuple]) -> int:
    """Optional one-time comparison using visible, user-supplied anchor times."""
    anchors = [
        (datetime(2026, 10, 27, 22, 17, tzinfo=BERLIN), datetime(2026, 10, 28, 12, 50, tzinfo=BERLIN)),
        (datetime(2026, 10, 28, 16, 42, tzinfo=BERLIN), datetime(2026, 10, 29, 17, 15, tzinfo=BERLIN)),
        (datetime(2026, 10, 26, 21, 12, tzinfo=BERLIN), datetime(2026, 10, 27, 11, 33, tzinfo=BERLIN)),
        (datetime(2026, 10, 31, 0, 36, tzinfo=BERLIN), datetime(2026, 10, 31, 16, 5, tzinfo=BERLIN)),
    ]
    validated = sum(any(
        end is not None
        and abs((start - reference_start).total_seconds()) <= 300
        and abs((end - reference_end).total_seconds()) <= 300
        for _, start, end, _ in rows
    ) for reference_start, reference_end in anchors)
    return validated


def persist_neon(rows: list[tuple]) -> None:
    import psycopg
    database_url = os.environ.get("WITHINGS_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("Missing Neon connection secret")
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cronometer_fasting_intervals (
                    fast_id TEXT PRIMARY KEY,
                    start_at TIMESTAMPTZ NOT NULL,
                    end_at TIMESTAMPTZ,
                    name TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'cronometer_web_gwt',
                    synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT cronometer_fast_time_order CHECK (end_at IS NULL OR end_at > start_at)
                )
            """)
            cur.executemany("""
                INSERT INTO cronometer_fasting_intervals
                    (fast_id, start_at, end_at, name, source, synced_at)
                VALUES (%s, %s, %s, %s, 'cronometer_web_gwt', now())
                ON CONFLICT(fast_id) DO UPDATE SET
                    start_at=EXCLUDED.start_at,
                    end_at=EXCLUDED.end_at,
                    name=EXCLUDED.name,
                    source=EXCLUDED.source,
                    synced_at=now()
            """, rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-screenshots", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not os.getenv("CRONOMETER_USERNAME") or not os.getenv("CRONOMETER_PASSWORD"):
        raise RuntimeError("Missing Cronometer credentials in secrets")
    from cronometer_mcp.client import CronometerClient
    try:
        # Only read operations; do not call account edit/delete methods.
        records = CronometerClient().get_user_fasts()
        rows = normalize(records)
        if args.validate_screenshots:
            matched = validated_against_screenshots(rows)
            if matched != 4:
                raise ValueError("Fasting records do not match known screenshot anchors")
            print(f"Verified screenshot anchors: {matched}/4")
        print(f"Read-only Cronometer history verified: records={len(rows)}")
        if args.dry_run:
            print("Dry run; no Neon changes.")
        else:
            persist_neon(rows)
            print(f"Neon upsert succeeded: records={len(rows)}")
    except Exception as exc:
        # Never log account data potentially embedded in upstream error text.
        print(f"Cronometer import failed safely: {type(exc).__name__}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
