from __future__ import annotations

import json
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

FRESHNESS_JSON = REPORTS_DIR / "data_freshness.json"
OUTPUT_TXT = REPORTS_DIR / "weekly_coaching_summary.txt"
OUTPUT_HTML = REPORTS_DIR / "weekly_coaching_summary.html"


def _freshness() -> dict[str, Any]:
    if not FRESHNESS_JSON.exists():
        return {"overall_status": "unknown", "checks": {}}
    try:
        return json.loads(FRESHNESS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"overall_status": "unknown", "checks": {}}


def _num(value: Any, decimals: int = 1, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{decimals}f}{suffix}"


def _load_window() -> tuple[pd.DataFrame, pd.DataFrame, date | None]:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        # Anchor the report to the latest day for which the core daily sources
        # all have data. This prevents a same-day Withings weigh-in from shifting
        # the email window ahead of Google Health/Cronometer and making the email
        # disagree with the attached coaching packet.
        latest = con.execute(
            """
            WITH source_dates AS (
                SELECT
                    (SELECT MAX(date)
                     FROM clean.body_composition
                     WHERE weight_kg IS NOT NULL) AS body_date,
                    (SELECT MAX(date)
                     FROM clean.fitbit_daily
                     WHERE steps IS NOT NULL
                        OR sleep_hours IS NOT NULL
                        OR resting_hr IS NOT NULL
                        OR hrv IS NOT NULL) AS activity_date,
                    (SELECT MAX(date)
                     FROM clean.nutrition_daily
                     WHERE calories IS NOT NULL
                        OR protein_g IS NOT NULL) AS nutrition_date
            )
            SELECT CASE
                WHEN body_date IS NULL
                  OR activity_date IS NULL
                  OR nutrition_date IS NULL
                THEN NULL
                ELSE LEAST(body_date, activity_date, nutrition_date)
            END
            FROM source_dates
            """
        ).fetchone()[0]
        if latest is None:
            return pd.DataFrame(), pd.DataFrame(), None

        current = con.execute(
            """
            SELECT *
            FROM analytics.daily_metrics
            WHERE date BETWEEN (?::DATE - INTERVAL 6 DAY) AND ?::DATE
            ORDER BY date
            """,
            [latest, latest],
        ).fetchdf()
        previous = con.execute(
            """
            SELECT *
            FROM analytics.daily_metrics
            WHERE date BETWEEN (?::DATE - INTERVAL 13 DAY) AND (?::DATE - INTERVAL 7 DAY)
            ORDER BY date
            """,
            [latest, latest],
        ).fetchdf()
        return current, previous, latest
    finally:
        con.close()


def _mean(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return None if values.empty else float(values.mean())


def _sum(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return None if values.empty else float(values.sum())


def _latest(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return None if values.empty else float(values.iloc[-1])


def _metrics(current: pd.DataFrame, previous: pd.DataFrame) -> dict[str, Any]:
    current_weight = _mean(current, "weight_kg")
    previous_weight = _mean(previous, "weight_kg")
    current_fat = _mean(current, "fat_mass_kg")
    previous_fat = _mean(previous, "fat_mass_kg")

    return {
        "latest_weight": _latest(current, "weight_kg"),
        "avg_weight": current_weight,
        "weight_change_vs_prior_7d": (
            current_weight - previous_weight
            if current_weight is not None and previous_weight is not None
            else None
        ),
        "avg_fat_mass": current_fat,
        "fat_mass_change_vs_prior_7d": (
            current_fat - previous_fat
            if current_fat is not None and previous_fat is not None
            else None
        ),
        "avg_calories": _mean(current, "calories"),
        "avg_protein": _mean(current, "protein_g"),
        "avg_steps": _mean(current, "steps"),
        "avg_sleep": _mean(current, "sleep_hours"),
        "avg_rhr": _mean(current, "resting_hr"),
        "avg_hrv": _mean(current, "hrv"),
        "workouts": _sum(current, "workout_count"),
    }


def _observations(metrics: dict[str, Any], status: str) -> list[str]:
    if status == "stale":
        return [
            "Current source data is too stale for a trustworthy weekly coaching interpretation."
        ]

    observations: list[str] = []
    weight_change = metrics.get("weight_change_vs_prior_7d")
    if weight_change is not None:
        observations.append(
            f"Seven-day average weight changed by {weight_change:+.2f} kg versus the prior seven days."
        )

    fat_change = metrics.get("fat_mass_change_vs_prior_7d")
    if fat_change is not None:
        observations.append(
            f"Seven-day average fat mass changed by {fat_change:+.2f} kg versus the prior seven days."
        )

    if metrics.get("avg_steps") is not None:
        observations.append(f"Average daily steps: {metrics['avg_steps']:.0f}.")
    if metrics.get("avg_sleep") is not None:
        observations.append(f"Average sleep: {metrics['avg_sleep']:.1f} hours/night.")
    if metrics.get("workouts") is not None:
        observations.append(f"Workouts recorded in the seven-day window: {metrics['workouts']:.0f}.")

    return observations or ["Not enough current data was available for additional observations."]


def _review_items(metrics: dict[str, Any], freshness: dict[str, Any]) -> list[str]:
    status = freshness.get("overall_status", "unknown")
    if status == "stale":
        return ["Restore current source syncing before using the coaching recommendations."]

    items: list[str] = []
    checks = freshness.get("checks", {})
    for name, detail in checks.items():
        if detail.get("status") != "fresh":
            items.append(f"Review {name.replace('_', ' ')} data freshness ({detail.get('status', 'unknown')}).")

    if metrics.get("avg_calories") is None or metrics.get("avg_protein") is None:
        items.append("Nutrition coverage is incomplete; review the Google Health/Cronometer sync.")
    if metrics.get("workouts") is None:
        items.append("Training coverage is incomplete; review the Hevy sync.")

    if not items:
        items.append("All core source checks are current; compare trends across several weeks before changing the plan.")
    return items[:4]


def _build_text(
    latest_date: date | None,
    status: str,
    metrics: dict[str, Any],
    observations: list[str],
    review_items: list[str],
) -> str:
    lines = [
        "WEEKLY COACHING SUMMARY",
        "=======================",
        "",
        f"Data status: {status.upper()}",
        f"Latest complete analysis date: {latest_date.isoformat() if latest_date else 'n/a'}",
        "",
        f"Latest weight in reporting window: {_num(metrics.get('latest_weight'), 2, ' kg')}",
        f"7-day average weight: {_num(metrics.get('avg_weight'), 2, ' kg')}",
        f"Weight change vs prior 7d: {_num(metrics.get('weight_change_vs_prior_7d'), 2, ' kg')}",
        f"7-day average fat mass: {_num(metrics.get('avg_fat_mass'), 2, ' kg')}",
        f"Fat-mass change vs prior 7d: {_num(metrics.get('fat_mass_change_vs_prior_7d'), 2, ' kg')}",
        f"Average calories: {_num(metrics.get('avg_calories'), 0, ' kcal/day')}",
        f"Average protein: {_num(metrics.get('avg_protein'), 0, ' g/day')}",
        f"Average steps: {_num(metrics.get('avg_steps'), 0, '/day')}",
        f"Average sleep: {_num(metrics.get('avg_sleep'), 1, ' h/night')}",
        f"Average resting HR: {_num(metrics.get('avg_rhr'), 1, ' bpm')}",
        f"Average HRV: {_num(metrics.get('avg_hrv'), 1, ' ms')}",
        f"Workouts: {_num(metrics.get('workouts'), 0)}",
        "",
        "Observations:",
    ]
    lines.extend(f"- {item}" for item in observations)
    lines.extend(["", "Items to review:"])
    lines.extend(f"- {item}" for item in review_items)
    lines.append("")
    return "\n".join(lines)


def _build_html(
    latest_date: date | None,
    status: str,
    metrics: dict[str, Any],
    observations: list[str],
    review_items: list[str],
) -> str:
    status_message = {
        "fresh": "All core freshness checks passed.",
        "partial": "Some current data is available, but one or more source checks need attention.",
        "stale": "Current source data is too stale for a trustworthy coaching interpretation.",
    }.get(status, "Freshness could not be fully determined.")

    rows = [
        ("Latest complete analysis date", latest_date.isoformat() if latest_date else "n/a"),
        ("Latest weight in reporting window", _num(metrics.get("latest_weight"), 2, " kg")),
        ("7-day average weight", _num(metrics.get("avg_weight"), 2, " kg")),
        ("Weight change vs prior 7d", _num(metrics.get("weight_change_vs_prior_7d"), 2, " kg")),
        ("7-day average fat mass", _num(metrics.get("avg_fat_mass"), 2, " kg")),
        ("Fat-mass change vs prior 7d", _num(metrics.get("fat_mass_change_vs_prior_7d"), 2, " kg")),
        ("Average calories", _num(metrics.get("avg_calories"), 0, " kcal/day")),
        ("Average protein", _num(metrics.get("avg_protein"), 0, " g/day")),
        ("Average steps", _num(metrics.get("avg_steps"), 0, "/day")),
        ("Average sleep", _num(metrics.get("avg_sleep"), 1, " h/night")),
        ("Average resting HR", _num(metrics.get("avg_rhr"), 1, " bpm")),
        ("Average HRV", _num(metrics.get("avg_hrv"), 1, " ms")),
        ("Workouts", _num(metrics.get("workouts"), 0)),
    ]

    table_rows = "".join(
        "<tr>"
        f"<td style='padding:6px 10px;border:1px solid #ddd'><strong>{escape(label)}</strong></td>"
        f"<td style='padding:6px 10px;border:1px solid #ddd'>{escape(value)}</td>"
        "</tr>"
        for label, value in rows
    )
    observations_html = "".join(f"<li>{escape(item)}</li>" for item in observations)
    review_html = "".join(f"<li>{escape(item)}</li>" for item in review_items)

    return f"""<!DOCTYPE html>
<html>
  <body style="font-family:Arial,sans-serif;line-height:1.5;color:#222;">
    <h2>Weekly Coaching Summary</h2>
    <p><strong>Data status: {escape(status.upper())}</strong> — {escape(status_message)}</p>
    <table style="border-collapse:collapse;margin-bottom:18px;">{table_rows}</table>
    <h3>Observations</h3>
    <ul>{observations_html}</ul>
    <h3>Items to review</h3>
    <ul>{review_html}</ul>
    <p style="color:#666;font-size:0.9em;">Generated automatically from the fitness-dashboard analytics database.</p>
  </body>
</html>
"""


def main() -> None:
    freshness = _freshness()
    status = freshness.get("overall_status", "unknown")
    current, previous, latest_date = _load_window()
    metrics = _metrics(current, previous)
    observations = _observations(metrics, status)
    review_items = _review_items(metrics, freshness)

    text = _build_text(latest_date, status, metrics, observations, review_items)
    html = _build_html(latest_date, status, metrics, observations, review_items)

    OUTPUT_TXT.write_text(text, encoding="utf-8")
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(text)
    print(f"Saved: {OUTPUT_TXT}")
    print(f"Saved: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
