"""Read-only, privacy-preserving Cronometer per-serving timestamp probe.

It prints only CSV column names and aggregate coverage counts.
No food entries, timestamps, secrets or response bodies are logged or saved.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os


def main():
    if not (os.getenv("CRONOMETER_USERNAME") and os.getenv("CRONOMETER_PASSWORD")):
        raise RuntimeError("Cronometer credentials must be provided through secure secrets")
    from cronometer_mcp.client import CronometerClient
    today = datetime.now(ZoneInfo("Europe/Berlin")).date()
    start = today - timedelta(days=12)
    try:
        rows = CronometerClient().get_food_log(start, today)
        if not isinstance(rows, list):
            raise ValueError("Unexpected export response")
        headers = sorted(set().union(*(r.keys() for r in rows))) if rows else []
        with_time = sum(bool(str(r.get("Time") or "").strip()) for r in rows)
        with_day = sum(bool(str(r.get("Day") or "").strip()) for r in rows)
        print(f"Read-only servings export: rows={len(rows)}; with_time={with_time}; with_day={with_day}; headers={headers}")
    except Exception as exc:
        # Do not expose upstream exception text because it can contain account data.
        print(f"Read-only servings export failed: {type(exc).__name__}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
