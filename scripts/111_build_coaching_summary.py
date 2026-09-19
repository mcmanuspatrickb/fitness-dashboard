from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

from report_context import load_report_context


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
OUTPUT_TXT = REPORTS_DIR / "weekly_coaching_summary.txt"
OUTPUT_HTML = REPORTS_DIR / "weekly_coaching_summary.html"
FRESHNESS_JSON = REPORTS_DIR / "data_freshness.json"

REPORT_FILES = {
    "phase": REPORTS_DIR / "phase_detection.txt",
    "guardrail": REPORTS_DIR / "cut_stress_guardrail.txt",
    "calorie": REPORTS_DIR / "adaptive_calorie_recommendation.txt",
    "feedback": REPORTS_DIR / "adaptive_coaching_feedback.txt",
    "lean": REPORTS_DIR / "lean_mass_preservation.txt",
    "weekly": REPORTS_DIR / "weekly_coaching_report.txt",
}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""
    except Exception:
        return ""


def _freshness() -> dict[str, Any]:
    if not FRESHNESS_JSON.exists():
        return {"overall_status": "unknown", "checks": {}}
    try:
        return json.loads(FRESHNESS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"overall_status": "unknown", "checks": {}}


def _line(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.strip().lower().startswith(prefix.lower()):
            return line.strip()
    return ""


def _section(text: str, heading: str) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    for i, line in enumerate(lines[:-1]):
        underline = lines[i + 1].strip()
        if line.strip() == heading and underline and set(underline) <= {"-", "="}:
            start = i + 2
            end = len(lines)
            for j in range(start, len(lines) - 1):
                nxt = lines[j + 1].strip()
                if lines[j].strip() and nxt and set(nxt) <= {"-", "="}:
                    end = j
                    break
            return "\n".join(lines[start:end]).strip()
    return ""


def _num(value: Any, digits: int = 1, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}{suffix}"


def _compact_bullets(text: str, limit: int = 4) -> list[str]:
    items = []
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned.startswith("- "):
            cleaned = cleaned[2:].strip()
        if cleaned and cleaned not in items:
            items.append(cleaned)
    return items[:limit]


def _extract_adjustment(calorie_text: str) -> str:
    action = _line(calorie_text, "Action:")
    adjustment = _line(calorie_text, "Calorie adjustment:")
    target = _line(calorie_text, "model target intake:")
    maintenance = _line(calorie_text, "rolling 28-day estimated maintenance:")
    return " | ".join(x for x in [action, adjustment, target, maintenance] if x)


def _build(status: str) -> tuple[str, str]:
    context = load_report_context()
    latest_date = context.get("analysis_end_date")
    weekly = context.get("weekly", {})
    trend = context.get("trend_4w", {})
    strength = context.get("strength_4w", [])
    performance = context.get("performance", {})
    texts = {key: _read(path) for key, path in REPORT_FILES.items()}

    if status == "stale":
        text = (
            "WEEKLY COACHING SUMMARY\n"
            "=======================\n\n"
            "Data status: STALE\n"
            "Current source data is too stale for a trustworthy coaching recommendation. "
            "Review the attached freshness and source-refresh diagnostics before using the plan.\n"
        )
        html = "<html><body><h2>Weekly Coaching Summary</h2><p><strong>Data status: STALE.</strong> Current source data is too stale for a trustworthy coaching recommendation. Review the attached diagnostics.</p></body></html>"
        return text, html

    phase = _line(texts["phase"], "current phase:") or "current phase: n/a"
    phase_suggestion = _line(texts["phase"], "suggestion:")
    guardrail = _line(texts["guardrail"], "status:") or "status: n/a"
    guardrail_interpretation = _line(texts["guardrail"], "interpretation:")
    calorie_summary = _extract_adjustment(texts["calorie"])
    feedback_learning = _section(texts["feedback"], "Learning Status")
    feedback_recent = _section(texts["feedback"], "Recent Evaluations")
    lean_interpretation = _section(texts["lean"], "Interpretation")
    next_focus = _compact_bullets(_section(texts["weekly"], "Next Week Focus"), 4)

    up = sum(1 for item in strength if item.get("direction") == "up")
    flat = sum(1 for item in strength if item.get("direction") == "flat")
    down = sum(1 for item in strength if item.get("direction") == "down")

    marker_lines = [
        f"Grip: {_num(performance.get('latest_grip_overall_kg'), 1, ' kg')} latest; "
        f"{performance.get('grip_measurement_count', 0)} measurement(s); "
        f"trend {_num(performance.get('grip_trend_pct'), 1, '%')}",
        f"Waist: {_num(performance.get('latest_waist_cm'), 1, ' cm')} latest; "
        f"change {_num(performance.get('waist_change_cm'), 1, ' cm')}",
    ]

    lines = [
        "WEEKLY COACHING SUMMARY",
        "=======================",
        "",
        f"Data status: {status.upper()}",
        f"Latest complete analysis date: {latest_date.isoformat() if latest_date else 'n/a'}",
        "",
        "COACHING STATUS",
        "---------------",
        phase,
        phase_suggestion,
        f"recovery guardrail: {guardrail.replace('status:', '').strip()}",
        guardrail_interpretation,
        "",
        "THIS WEEK'S CALORIE DECISION",
        "----------------------------",
        calorie_summary or "No current calorie decision available.",
        "",
        "BODY / PERFORMANCE SNAPSHOT",
        "---------------------------",
        f"7-day avg weight: {_num(weekly.get('recent_weight'), 2, ' kg')} | change vs prior 7d: {_num(weekly.get('weight_delta'), 2, ' kg')}",
        f"4-week fat-mass change: {_num(trend.get('fat_delta'), 2, ' kg')} | BIA lean-mass change: {_num(trend.get('lean_delta'), 2, ' kg')}",
        f"4-week strength: {up} up / {flat} flat / {down} down",
        marker_lines[0],
        marker_lines[1],
        "",
        "RECOVERY / ADHERENCE",
        "--------------------",
        f"Protein: {_num(weekly.get('recent_protein'), 0, ' g/day')} | Sleep: {_num(weekly.get('recent_sleep'), 1, ' h/night')} | Steps: {_num(weekly.get('recent_steps'), 0, '/day')} | Workouts: {_num(weekly.get('recent_workouts'), 0)}",
    ]

    if feedback_learning:
        lines.extend(["", "Feedback learning:", feedback_learning])
    if feedback_recent and "No follow-up window has matured yet." not in feedback_recent:
        lines.extend(["", "Recent tested outcomes:", feedback_recent])
    if lean_interpretation:
        lean_bullets = _compact_bullets(lean_interpretation, 3)
        if lean_bullets:
            lines.extend(["", "MUSCLE-PRESERVATION INTERPRETATION", "----------------------------------"])
            lines.extend(f"- {item}" for item in lean_bullets)
    lines.extend(["", "NEXT WEEK FOCUS", "---------------"])
    lines.extend(f"- {item}" for item in next_focus) if next_focus else lines.append("- No specific focus items available.")
    lines.extend([
        "",
        "Notes: Withings lean mass is a BIA estimate and can move with hydration/glycogen. "
        "Grip is only treated as a trend after enough repeated measurements. The adaptive feedback loop separates adherence from effectiveness.",
    ])
    text = "\n".join(line for line in lines if line is not None)

    def li(items: list[str]) -> str:
        return "".join(f"<li>{escape(item)}</li>" for item in items)

    html = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;line-height:1.5;color:#222;">
<h2>Weekly Coaching Summary</h2>
<p><strong>Data status: {escape(status.upper())}</strong><br>Latest complete analysis date: {escape(latest_date.isoformat() if latest_date else 'n/a')}</p>
<h3>Coaching status</h3>
<p>{escape(phase)}<br>{escape(phase_suggestion)}<br><strong>Recovery guardrail:</strong> {escape(guardrail.replace('status:', '').strip())}<br>{escape(guardrail_interpretation)}</p>
<h3>This week's calorie decision</h3><p>{escape(calorie_summary or 'No current calorie decision available.')}</p>
<h3>Body / performance snapshot</h3>
<ul>
<li>7-day avg weight: {escape(_num(weekly.get('recent_weight'), 2, ' kg'))}; change vs prior 7d: {escape(_num(weekly.get('weight_delta'), 2, ' kg'))}</li>
<li>4-week fat-mass change: {escape(_num(trend.get('fat_delta'), 2, ' kg'))}; BIA lean-mass change: {escape(_num(trend.get('lean_delta'), 2, ' kg'))}</li>
<li>4-week strength: {up} up / {flat} flat / {down} down</li>
<li>{escape(marker_lines[0])}</li><li>{escape(marker_lines[1])}</li>
</ul>
<h3>Recovery / adherence</h3>
<p>Protein: {escape(_num(weekly.get('recent_protein'), 0, ' g/day'))} | Sleep: {escape(_num(weekly.get('recent_sleep'), 1, ' h/night'))} | Steps: {escape(_num(weekly.get('recent_steps'), 0, '/day'))} | Workouts: {escape(_num(weekly.get('recent_workouts'), 0))}</p>
<h3>Next week focus</h3><ul>{li(next_focus or ['No specific focus items available.'])}</ul>
<p style="color:#666;font-size:0.9em;">Withings lean mass is a BIA estimate. Grip is only interpreted as a trend after repeated measurements. The adaptive feedback loop separates adherence from effectiveness.</p>
</body></html>"""
    return text, html


def main() -> None:
    freshness = _freshness()
    status = freshness.get("overall_status", "unknown")
    text, html = _build(status)
    OUTPUT_TXT.write_text(text, encoding="utf-8")
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(text)
    print(f"Saved: {OUTPUT_TXT}")
    print(f"Saved: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
