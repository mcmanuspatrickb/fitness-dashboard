from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_JSON = REPORTS_DIR / "data_freshness.json"
OUTPUT_TXT = REPORTS_DIR / "data_freshness.txt"

CHECKS = {
    "body_composition": {
        # A current weight alone is not enough for the weekly body-composition
        # interpretation. Require a recent composition value as well so missing
        # Withings fat data cannot be reported as a healthy/fresh source.
        "sql": """
            SELECT MAX(date)
            FROM clean.body_composition
            WHERE weight_kg IS NOT NULL
              AND (fat_mass_kg IS NOT NULL OR body_fat_percent IS NOT NULL)
        """,
        "max_age_days": 14,
    },
    "activity_recovery": {
        "sql": """
            SELECT MAX(date)
            FROM clean.fitbit_daily
            WHERE steps IS NOT NULL
               OR sleep_hours IS NOT NULL
               OR resting_hr IS NOT NULL
               OR hrv IS NOT NULL
        """,
        "max_age_days": 3,
    },
    "nutrition": {
        "sql": """
            SELECT MAX(date)
            FROM clean.nutrition_daily
            WHERE calories IS NOT NULL OR protein_g IS NOT NULL
        """,
        "max_age_days": 7,
    },
    "training": {
        "sql": "SELECT MAX(date) FROM clean.training_summary WHERE workout_count > 0",
        "max_age_days": 14,
    },
}


def main() -> None:
    today = date.today()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        results = {}
        for name, spec in CHECKS.items():
            try:
                row = con.execute(spec["sql"]).fetchone()
                latest = row[0] if row else None
            except Exception as exc:
                results[name] = {
                    "latest_date": None,
                    "age_days": None,
                    "max_age_days": spec["max_age_days"],
                    "status": "error",
                    "error": str(exc),
                }
                continue

            if latest is None:
                results[name] = {
                    "latest_date": None,
                    "age_days": None,
                    "max_age_days": spec["max_age_days"],
                    "status": "missing",
                }
                continue

            if hasattr(latest, "date") and not isinstance(latest, date):
                latest = latest.date()
            age_days = (today - latest).days
            results[name] = {
                "latest_date": latest.isoformat(),
                "age_days": age_days,
                "max_age_days": spec["max_age_days"],
                "status": "fresh" if age_days <= spec["max_age_days"] else "stale",
            }
    finally:
        con.close()

    fresh_count = sum(item["status"] == "fresh" for item in results.values())
    problem_count = sum(item["status"] in {"stale", "missing", "error"} for item in results.values())

    if problem_count == 0:
        overall = "fresh"
    elif fresh_count >= 2:
        overall = "partial"
    else:
        overall = "stale"

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "today": today.isoformat(),
        "overall_status": overall,
        "checks": results,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "Weekly Coaching Data Freshness",
        "==============================",
        f"Overall: {overall.upper()}",
        f"Checked: {payload['generated_at']}",
        "",
    ]
    for name, item in results.items():
        latest_text = item.get("latest_date") or "n/a"
        age_text = "n/a" if item.get("age_days") is None else str(item["age_days"])
        lines.append(
            f"{name}: {item['status'].upper()} | latest={latest_text} | age_days={age_text} | allowed={item['max_age_days']}"
        )
        if item.get("error"):
            lines.append(f"  error: {item['error']}")

    OUTPUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"Saved: {OUTPUT_JSON}")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    main()
