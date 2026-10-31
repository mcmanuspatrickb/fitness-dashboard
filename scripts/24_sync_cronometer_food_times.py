"""Cronometer timestamped food-entry import, manual and read-only.

Reads the official servings CSV using the existing pinned Cronometer GWT client.
Creates versioned snapshots in private Neon; never logs food, times or secrets.
The existing daily nutrition totals remain authoritative for calories/protein.
"""
from __future__ import annotations

import argparse
import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
DAY_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d.%m.%Y")
TIME_FORMATS = ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p",
                "%I:%M%p", "%I:%M:%S%p")


def parse_day(value):
    value = str(value or "").strip()
    for fmt in DAY_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("Unsupported Cronometer Day format")


def parse_clock(value):
    value = str(value or "").strip()
    if not value:
        return None
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            pass
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise ValueError("Unsupported Cronometer Time format")


def valid_utc_local(dt):
    """Preserve precise local diary times; do not guess ambiguous DST hours."""
    local = dt.replace(tzinfo=BERLIN, fold=0)
    alt = dt.replace(tzinfo=BERLIN, fold=1)
    if local.utcoffset() != alt.utcoffset():
        return None
    utc = local.astimezone(timezone.utc)
    if utc.astimezone(BERLIN).replace(tzinfo=None) != dt:
        return None
    return utc


def normalize(rows, start, end):
    if not isinstance(rows, list):
        raise ValueError("Expected CSV row list")
    normalized = []
    seen_day = set()
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("Non-dictionary serving")
        day = parse_day(row.get("Day"))
        if day < start or day > end:
            raise ValueError("Serving day outside requested date range")
        clock = parse_clock(row.get("Time"))
        occurred_local = datetime.combine(day, clock) if clock else None
        occurred_utc = valid_utc_local(occurred_local) if occurred_local else None
        normalized.append((
            position, day, occurred_local, occurred_utc,
            str(row.get("Food Name") or "")[:500],
            str(row.get("Amount") or "")[:100],
            str(row.get("Group") or "")[:150],
            str(row.get("Category") or "")[:150],
        ))
        seen_day.add(day)
    return normalized


def persist(rows, start, end):
    import psycopg
    connection_url = os.getenv("WITHINGS_DATABASE_URL", "").strip()
    if not connection_url:
        raise RuntimeError("Missing Neon database connection")
    with psycopg.connect(connection_url) as con:
        with con.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cronometer_food_imports (
                    import_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    window_start DATE NOT NULL, window_end DATE NOT NULL,
                    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    source TEXT NOT NULL DEFAULT 'cronometer_servings_csv_read_only',
                    CHECK (window_end >= window_start)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cronometer_food_entries (
                    import_id BIGINT NOT NULL REFERENCES cronometer_food_imports(import_id),
                    entry_ordinal INTEGER NOT NULL,
                    logged_day DATE NOT NULL,
                    occurred_local TIMESTAMP,
                    occurred_at TIMESTAMPTZ,
                    food_name TEXT, amount TEXT, diary_group TEXT, category TEXT,
                    PRIMARY KEY(import_id, entry_ordinal)
                )
            """)
            cur.execute("""
                CREATE OR REPLACE VIEW cronometer_food_entries_current AS
                SELECT e.* FROM cronometer_food_entries e
                WHERE e.import_id = (
                  SELECT MAX(i.import_id) FROM cronometer_food_imports i
                  WHERE i.window_start <= e.logged_day AND i.window_end >= e.logged_day
                )
            """)
            cur.execute("""
                INSERT INTO cronometer_food_imports(window_start,window_end)
                VALUES (%s,%s) RETURNING import_id
            """, (start, end))
            import_id = cur.fetchone()[0]
            if rows:
                cur.executemany("""
                    INSERT INTO cronometer_food_entries
                    (import_id,entry_ordinal,logged_day,occurred_local,occurred_at,
                     food_name,amount,diary_group,category)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, [(import_id, *r) for r in rows])
    print(f"Timestamped serving entries safely imported: count={len(rows)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.days <= 365:
        parser.error("--days must be between 1 and 365")
    if not (os.getenv("CRONOMETER_USERNAME") and os.getenv("CRONOMETER_PASSWORD")):
        raise RuntimeError("Cronometer credentials missing from encrypted secrets")
    from cronometer_mcp.client import CronometerClient
    end = datetime.now(BERLIN).date()
    start = end - timedelta(days=args.days - 1)
    try:
        rows = CronometerClient().get_food_log(start, end)
        normalized = normalize(rows, start, end)
        stamped = sum(row[2] is not None for row in normalized)
        # Fail closed if the user's timestamped diary unexpectedly loses timestamps.
        if not normalized or stamped == 0:
            raise ValueError("No usable timestamped entries")
        print(f"Validated read-only food-entry export: rows={len(normalized)}, with_time={stamped}")
        if args.dry_run:
            print("Dry run only; no database writes")
        else:
            persist(normalized, start, end)
    except Exception as exc:
        # Vendor exception strings may contain private records/tokens.
        print(f"Food timestamp import stopped safely: {type(exc).__name__}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
