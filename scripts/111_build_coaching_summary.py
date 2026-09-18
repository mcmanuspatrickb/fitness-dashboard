from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

from report_context import load_report_context


PROJECT_ROOT = Path(__file__).resolve().parent.parent
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


def _observations(weekly: dict[str, Any], status: str) -> list[str]:
    if status == "stale":
        return ["Current source data is too stale for a trustworthy weekly coaching interpretation."]

    observations: list[str] = []
    if weekly.get("weight_delta") is not None:
        observations.append(
            f"Seven-day average weight changed by {weekly['weight_delta']:+.2f} kg versus the prior seven days."
        )
    if weekly.get("fat_delta") is not None:
        observations.append(
            f"Seven-day average fat mass changed by {weekly['fat_delta']:+.2f} kg versus the prior seven days."
        )
    if weekly.get("recent_steps") is not None:
        observations.append(f"Average daily steps: {weekly['recent_steps']:.0f}.")
    if weekly.get("recent_sleep") is not None:
        observations.append(f"Average sleep: {weekly['recent_sleep']:.1f} hours/night.")
    if weekly.get("recent_workouts") is not None:
        observations.append(f"Workouts recorded in the seven-day window: {weekly['recent_workouts']:.0f}.")
    return observations or ["Not enough current data was available for additional observations."]


def _review_items(
    weekly: dict[str, Any], coverage: dict[str, Any], freshness: dict[str, Any]
) -> list[str]:
    status = freshness.get("overall_status", "unknown")
    if status == "stale":
        return ["Restore current source syncing before using the coaching recommendations."]

    items: list[str] = []
    for name, detail in freshness.get("checks", {}).items():
        if detail.get("status") != "fresh":
            items.append(
                f"Review {name.replace('_', ' ')} data freshness ({detail.get('status', 'unknown')})."
            )

    if coverage.get("confidence") == "LOW":
        items.append("Data coverage is low; avoid changing the plan from this week alone.")
    elif coverage.get("confidence") == "MEDIUM":
        items.append("Data coverage is moderate; interpret smaller week-to-week changes cautiously.")

    if weekly.get("recent_calories") is None or weekly.get("recent_protein") is None:
        items.append("Nutrition coverage is incomplete; review the Google Health/Cronometer sync.")
    if weekly.get("recent_workouts") is None:
        items.append("Training coverage is incomplete; review the Hevy sync.")

    if not items:
        items.append("All core source checks are current; compare trends across several weeks before changing the plan.")
    return items[:4]


def _coverage_rows(coverage: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        (
            "Coverage confidence",
            f"{coverage.get('confidence', 'UNKNOWN')} (coverage-based; not device accuracy)",
        ),
        ("Body composition", f"{coverage.get('body_composition_days', 0)}/7 days"),
        ("Nutrition", f"{coverage.get('nutrition_days', 0)}/7 days"),
        ("Steps", f"{coverage.get('steps_days', 0)}/7 days"),
        ("Sleep", f"{coverage.get('sleep_days', 0)}/7 days"),
        ("Recovery (RHR + HRV)", f"{coverage.get('recovery_days', 0)}/7 days"),
        ("Training", f"{coverage.get('workouts', 0)} workouts recorded"),
    ]


def _trend_rows(trend: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        ("Weight change: latest 7d avg vs first 7d avg", _num(trend.get("weight_delta"), 2, " kg")),
        ("Fat-mass change: latest 7d avg vs first 7d avg", _num(trend.get("fat_delta"), 2, " kg")),
        ("Lean-mass change: latest 7d avg vs first 7d avg", _num(trend.get("lean_delta"), 2, " kg")),
        ("28-day average calories", _num(trend.get("avg_calories"), 0, " kcal/day")),
        ("28-day average protein", _num(trend.get("avg_protein"), 0, " g/day")),
        ("28-day average steps", _num(trend.get("avg_steps"), 0, "/day")),
        ("28-day average sleep", _num(trend.get("avg_sleep"), 1, " h/night")),
        ("28-day workouts", _num(trend.get("workouts"), 0)),
    ]


def _strength_lines(strength_4w: list[dict[str, Any]]) -> list[str]:
    if not strength_4w:
        return ["Not enough repeated lift observations in the four-week window."]
    return [
        f"{item['label']}: {item['change_e1rm']:+.1f} kg e1RM ({item['direction']}; {item['observations']} weekly observations)"
        for item in strength_4w
    ]


def _build_text(
    latest_date,
    status: str,
    weekly: dict[str, Any],
    coverage: dict[str, Any],
    trend: dict[str, Any],
    strength_4w: list[dict[str, Any]],
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
        "7-Day Summary",
        "-------------",
        f"Latest weight in reporting window: {_num(weekly.get('latest_weight'), 2, ' kg')}",
        f"7-day average weight: {_num(weekly.get('recent_weight'), 2, ' kg')}",
        f"Weight change vs prior 7d: {_num(weekly.get('weight_delta'), 2, ' kg')}",
        f"7-day average fat mass: {_num(weekly.get('recent_fat'), 2, ' kg')}",
        f"Fat-mass change vs prior 7d: {_num(weekly.get('fat_delta'), 2, ' kg')}",
        f"Average calories: {_num(weekly.get('recent_calories'), 0, ' kcal/day')}",
        f"Average protein: {_num(weekly.get('recent_protein'), 0, ' g/day')}",
        f"Average steps: {_num(weekly.get('recent_steps'), 0, '/day')}",
        f"Average sleep: {_num(weekly.get('recent_sleep'), 1, ' h/night')}",
        f"Average resting HR: {_num(weekly.get('recent_rhr'), 1, ' bpm')}",
        f"Average HRV: {_num(weekly.get('recent_hrv'), 1, ' ms')}",
        f"Workouts: {_num(weekly.get('recent_workouts'), 0)}",
        "",
        "Data Quality",
        "------------",
    ]
    lines.extend(f"{label}: {value}" for label, value in _coverage_rows(coverage))
    lines.extend(["", "4-Week Context", "--------------"])
    lines.extend(f"{label}: {value}" for label, value in _trend_rows(trend))
    lines.extend(["", "4-Week Strength Context", "-----------------------"])
    lines.extend(f"- {item}" for item in _strength_lines(strength_4w))
    lines.extend(["", "Observations:"])
    lines.extend(f"- {item}" for item in observations)
    lines.extend(["", "Items to review:"])
    lines.extend(f"- {item}" for item in review_items)
    lines.append("")
    return "\n".join(lines)


def _html_table(rows: list[tuple[str, str]]) -> str:
    return "".join(
        "<tr>"
        f"<td style='padding:6px 10px;border:1px solid #ddd'><strong>{escape(label)}</strong></td>"
        f"<td style='padding:6px 10px;border:1px solid #ddd'>{escape(value)}</td>"
        "</tr>"
        for label, value in rows
    )


def _build_html(
    latest_date,
    status: str,
    weekly: dict[str, Any],
    coverage: dict[str, Any],
    trend: dict[str, Any],
    strength_4w: list[dict[str, Any]],
    observations: list[str],
    review_items: list[str],
) -> str:
    status_message = {
        "fresh": "All core freshness checks passed.",
        "partial": "Some current data is available, but one or more source checks need attention.",
        "stale": "Current source data is too stale for a trustworthy coaching interpretation.",
    }.get(status, "Freshness could not be fully determined.")

    summary_rows = [
        ("Latest complete analysis date", latest_date.isoformat() if latest_date else "n/a"),
        ("Latest weight in reporting window", _num(weekly.get("latest_weight"), 2, " kg")),
        ("7-day average weight", _num(weekly.get("recent_weight"), 2, " kg")),
        ("Weight change vs prior 7d", _num(weekly.get("weight_delta"), 2, " kg")),
        ("7-day average fat mass", _num(weekly.get("recent_fat"), 2, " kg")),
        ("Fat-mass change vs prior 7d", _num(weekly.get("fat_delta"), 2, " kg")),
        ("Average calories", _num(weekly.get("recent_calories"), 0, " kcal/day")),
        ("Average protein", _num(weekly.get("recent_protein"), 0, " g/day")),
        ("Average steps", _num(weekly.get("recent_steps"), 0, "/day")),
        ("Average sleep", _num(weekly.get("recent_sleep"), 1, " h/night")),
        ("Average resting HR", _num(weekly.get("recent_rhr"), 1, " bpm")),
        ("Average HRV", _num(weekly.get("recent_hrv"), 1, " ms")),
        ("Workouts", _num(weekly.get("recent_workouts"), 0)),
    ]

    observations_html = "".join(f"<li>{escape(item)}</li>" for item in observations)
    review_html = "".join(f"<li>{escape(item)}</li>" for item in review_items)
    strength_html = "".join(f"<li>{escape(item)}</li>" for item in _strength_lines(strength_4w))

    return f"""<!DOCTYPE html>
<html>
  <body style="font-family:Arial,sans-serif;line-height:1.5;color:#222;">
    <h2>Weekly Coaching Summary</h2>
    <p><strong>Data status: {escape(status.upper())}</strong> — {escape(status_message)}</p>
    <h3>7-Day Summary</h3>
    <table style="border-collapse:collapse;margin-bottom:18px;">{_html_table(summary_rows)}</table>
    <h3>Data Quality</h3>
    <table style="border-collapse:collapse;margin-bottom:18px;">{_html_table(_coverage_rows(coverage))}</table>
    <h3>4-Week Context</h3>
    <table style="border-collapse:collapse;margin-bottom:18px;">{_html_table(_trend_rows(trend))}</table>
    <h3>4-Week Strength Context</h3>
    <ul>{strength_html}</ul>
    <h3>Observations</h3>
    <ul>{observations_html}</ul>
    <h3>Items to review</h3>
    <ul>{review_html}</ul>
    <p style="color:#666;font-size:0.9em;">Coverage confidence reflects completeness of the reporting window, not device measurement accuracy. Generated automatically from the fitness-dashboard analytics database.</p>
  </body>
</html>
"""


def main() -> None:
    freshness = _freshness()
    status = freshness.get("overall_status", "unknown")
    context = load_report_context()
    latest_date = context.get("analysis_end_date")
    weekly = context.get("weekly", {})
    coverage = context.get("coverage", {})
    trend = context.get("trend_4w", {})
    strength_4w = context.get("strength_4w", [])

    observations = _observations(weekly, status)
    review_items = _review_items(weekly, coverage, freshness)

    text = _build_text(
        latest_date,
        status,
        weekly,
        coverage,
        trend,
        strength_4w,
        observations,
        review_items,
    )
    html = _build_html(
        latest_date,
        status,
        weekly,
        coverage,
        trend,
        strength_4w,
        observations,
        review_items,
    )

    OUTPUT_TXT.write_text(text, encoding="utf-8")
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(text)
    print(f"Saved: {OUTPUT_TXT}")
    print(f"Saved: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
