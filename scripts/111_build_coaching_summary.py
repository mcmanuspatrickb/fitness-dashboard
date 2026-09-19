from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
OUTPUT_TXT = REPORTS_DIR / "weekly_coaching_summary.txt"
OUTPUT_HTML = REPORTS_DIR / "weekly_coaching_summary.html"
FRESHNESS_JSON = REPORTS_DIR / "data_freshness.json"
SNAPSHOT_JSON = REPORTS_DIR / "canonical_coaching_snapshot.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _num(value: Any, digits: int = 1, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "n/a"


def _int(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        return "n/a"


def _state(value: Any) -> str:
    return str(value or "n/a").replace("_", " ").title()


def _build_unavailable(status: str, message: str) -> tuple[str, str]:
    text = (
        "WEEKLY COACHING SUMMARY\n"
        "=======================\n\n"
        f"Data status: {status.upper()}\n"
        f"{message}\n"
    )
    html = (
        "<html><body style='font-family:Arial,sans-serif;line-height:1.5;color:#222;'>"
        "<h2>Weekly Coaching Summary</h2>"
        f"<p><strong>Data status: {escape(status.upper())}</strong></p>"
        f"<p>{escape(message)}</p></body></html>"
    )
    return text, html


def _build(status: str, snapshot: dict[str, Any]) -> tuple[str, str]:
    if status != "fresh":
        return _build_unavailable(
            status,
            "Current source data is not fully fresh enough for a trustworthy coaching recommendation. Review the attached freshness/source diagnostics before changing the plan.",
        )
    if not snapshot:
        return _build_unavailable(
            status,
            "The source data are fresh, but the canonical coaching snapshot was not generated. Review the attached coaching packet/diagnostics.",
        )

    states = snapshot.get("states", {})
    body = snapshot.get("body", {})
    energy = snapshot.get("energy", {})
    nutrition = snapshot.get("nutrition", {})
    adherence = snapshot.get("adherence", {})
    strength = snapshot.get("strength", {})
    training = snapshot.get("training_dose", {})
    recovery = snapshot.get("recovery", {})
    performance = snapshot.get("performance", {})
    decision = snapshot.get("decision", {})
    personal = snapshot.get("personal_response", {})
    feedback = snapshot.get("adaptive_feedback", {})
    priorities = snapshot.get("priorities", []) or []
    interpretation = snapshot.get("interpretation", []) or []

    e28 = energy.get("window_28", {})
    e42 = energy.get("window_42", {})
    lifts = strength.get("lifts", []) or []
    groups = [row for row in training.get("groups", []) if row.get("muscle_group") != "Other / unmapped"]

    target_low = nutrition.get("protein_target_low_g")
    target_high = nutrition.get("protein_target_high_g")
    target_text = (
        f"{_num(target_low, 0)}-{_num(target_high, 0)} g/day"
        if target_low is not None and target_high is not None
        else "n/a"
    )
    tdee_range = (
        f"{_num(energy.get('planning_range_low'), 0)}-{_num(energy.get('planning_range_high'), 0)} kcal/day"
        if energy.get("planning_range_low") is not None and energy.get("planning_range_high") is not None
        else "n/a"
    )

    lines = [
        "WEEKLY COACHING SUMMARY",
        "=======================",
        "",
        f"Data status: {status.upper()}",
        f"Analysis date: {snapshot.get('analysis_date', 'n/a')}",
        f"Phase: {_state(snapshot.get('phase'))}",
        "",
        "CANONICAL STATUS",
        "----------------",
        f"Fat loss: {_state(states.get('fat_loss'))}",
        f"Muscle preservation: {_state(states.get('muscle_preservation'))}",
        f"Recovery: {_state(states.get('recovery'))}",
        f"Training: {_state(states.get('training'))}",
        "",
        "THIS WEEK'S PLAN",
        "----------------",
        f"Calories: {_state(decision.get('action'))} {_num(decision.get('calorie_adjustment'), 0, ' kcal/day')} | model target {_num(decision.get('target_intake'), 0, ' kcal/day')}",
        f"Protein: {target_text}",
        "Resistance training: 2 productive sessions",
        "Movement: ~7,000 steps/day floor; ~8,000+ preferred when recovery allows",
        "Sleep: work toward 7+ h/night",
        "",
        "BODY / PERFORMANCE",
        "------------------",
        f"Weight change across comparison window: {_num(body.get('weight_change_window_kg'), 2, ' kg')}",
        f"BIA fat-mass change: {_num(body.get('fat_change_window_kg'), 2, ' kg')} | BIA lean-mass change: {_num(body.get('bia_lean_change_window_kg'), 2, ' kg')}",
        f"Loss pace: {_num(body.get('loss_rate_pct_week'), 2, '%/week')}",
        f"Strength: {strength.get('up', 0)} up / {strength.get('flat', 0)} flat / {strength.get('down', 0)} down",
        f"Waist: {_num(body.get('latest_waist_cm'), 1, ' cm')} latest | change {_num(body.get('waist_change_cm'), 1, ' cm')}",
        f"Grip: {_num(performance.get('latest_grip_kg'), 1, ' kg')} latest | n={performance.get('grip_measurement_count', 0)} | trend {_num(performance.get('grip_trend_pct'), 1, '%')}",
        "",
        "ENERGY MODEL",
        "------------",
        f"28-day maintenance estimate: {_num(e28.get('estimated_tdee'), 0, ' kcal/day')}",
        f"42-day maintenance estimate: {_num(e42.get('estimated_tdee'), 0, ' kcal/day')}",
        f"Planning maintenance: {_num(energy.get('planning_tdee'), 0, ' kcal/day')} | range {tdee_range}",
        f"28/42-day agreement: {_state(energy.get('stability'))}",
        "",
        "ADHERENCE / RECOVERY",
        "--------------------",
        f"Protein target days: {adherence.get('protein_days_met', 0)}/{adherence.get('protein_days_logged', 0)} logged days",
        f"7+ hour sleep nights: {adherence.get('sleep_7h_days', 0)}/{adherence.get('sleep_days_logged', 0)} logged nights",
        f"Step floor: {adherence.get('steps_7000_days', 0)}/{adherence.get('steps_days_logged', 0)} days >=7k; preferred target: {adherence.get('steps_8000_days', 0)}/{adherence.get('steps_days_logged', 0)} days >=8k",
        f"Resistance workouts: {_num(adherence.get('workouts_7d'), 0)} in latest 7 days",
        f"RHR: {_num(recovery.get('rhr_recent'), 1, ' bpm')} recent median vs {_num(recovery.get('rhr_baseline'), 1, ' bpm')} personal baseline | {_state(recovery.get('rhr_state'))}",
        f"HRV: {_num(recovery.get('hrv_recent'), 1, ' ms')} recent median vs {_num(recovery.get('hrv_baseline'), 1, ' ms')} personal baseline | {_state(recovery.get('hrv_state'))}",
        "",
        "TRAINING DOSE — PRIMARY MUSCLE WORKING SETS",
        "-------------------------------------------",
    ]
    if groups:
        for row in groups:
            lines.append(
                f"{row.get('muscle_group')}: {row.get('working_sets_7d', 0)} sets / 7d | {row.get('working_sets_28d', 0)} sets / 28d | RPE>=7.5 sets: {row.get('hard_sets_7d', 0)} / 7d"
            )
    else:
        lines.append("No mapped working-set dose available.")

    if lifts:
        lines.extend(["", "EXACT-LIFT STRENGTH CROSS-CHECK", "-------------------------------"])
        for lift in lifts:
            lines.append(
                f"{lift.get('label', lift.get('target_lift', 'Lift'))}: {_num(lift.get('current_best_e1rm'), 1, ' kg')} vs {_num(lift.get('prior_best_e1rm'), 1, ' kg')} | {_state(lift.get('direction'))}"
            )

    lines.extend([
        "",
        "PERSONAL LEARNING",
        "-----------------",
        f"Comparable 14-day blocks: {personal.get('comparable_blocks', 0)} | evidence tier: {_state(personal.get('evidence_tier'))}",
        f"Minimum before personal-response associations may alter calorie decisions: {personal.get('adjustment_minimum', 12)} blocks",
        f"Adaptive feedback events: {feedback.get('history_events', 0)} | matured 21-28 day effectiveness outcomes: {feedback.get('mature_28d_events', 0)}",
        "",
        "INTERPRETATION",
        "--------------",
    ])
    lines.extend(f"- {item}" for item in interpretation) if interpretation else lines.append("- No integrated interpretation available.")
    lines.extend(["", "NEXT-WEEK PRIORITIES", "--------------------"])
    lines.extend(f"- {item}" for item in priorities) if priorities else lines.append("- Maintain the current plan.")
    lines.extend([
        "",
        "Notes: BIA fat-free mass is supporting evidence, not a direct muscle measurement. The weekly email and Streamlit coaching status now use the same canonical snapshot. Seven-day feedback is primarily an adherence/recovery check; later 21-28 day windows are used for intervention effectiveness.",
    ])
    text = "\n".join(lines)

    def li(items: list[str]) -> str:
        return "".join(f"<li>{escape(str(item))}</li>" for item in items)

    group_rows = "".join(
        "<tr>"
        f"<td>{escape(str(row.get('muscle_group')))}</td>"
        f"<td>{row.get('working_sets_7d', 0)}</td>"
        f"<td>{row.get('working_sets_28d', 0)}</td>"
        f"<td>{row.get('hard_sets_7d', 0)}</td>"
        "</tr>"
        for row in groups
    ) or "<tr><td colspan='4'>No mapped working-set dose available.</td></tr>"

    lift_rows = "".join(
        "<tr>"
        f"<td>{escape(str(lift.get('label', lift.get('target_lift', 'Lift'))))}</td>"
        f"<td>{escape(_num(lift.get('current_best_e1rm'), 1, ' kg'))}</td>"
        f"<td>{escape(_num(lift.get('prior_best_e1rm'), 1, ' kg'))}</td>"
        f"<td>{escape(_state(lift.get('direction')))}</td>"
        "</tr>"
        for lift in lifts
    ) or "<tr><td colspan='4'>No comparable exact-lift history available.</td></tr>"

    html = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;line-height:1.45;color:#222;max-width:900px;margin:auto;">
<h2>Weekly Coaching Summary</h2>
<p><strong>Data status:</strong> {escape(status.upper())}<br>
<strong>Analysis date:</strong> {escape(str(snapshot.get('analysis_date', 'n/a')))}<br>
<strong>Phase:</strong> {escape(_state(snapshot.get('phase')))}</p>

<h3>Canonical status</h3>
<ul>
<li><strong>Fat loss:</strong> {escape(_state(states.get('fat_loss')))}</li>
<li><strong>Muscle preservation:</strong> {escape(_state(states.get('muscle_preservation')))}</li>
<li><strong>Recovery:</strong> {escape(_state(states.get('recovery')))}</li>
<li><strong>Training:</strong> {escape(_state(states.get('training')))}</li>
</ul>

<h3>This week's plan</h3>
<ul>
<li><strong>Calories:</strong> {escape(_state(decision.get('action')))} {escape(_num(decision.get('calorie_adjustment'), 0, ' kcal/day'))}; model target {escape(_num(decision.get('target_intake'), 0, ' kcal/day'))}</li>
<li><strong>Protein:</strong> {escape(target_text)}</li>
<li><strong>Resistance training:</strong> 2 productive sessions</li>
<li><strong>Movement:</strong> ~7,000/day floor; ~8,000+ preferred when recovery allows</li>
<li><strong>Sleep:</strong> work toward 7+ h/night</li>
</ul>

<h3>Body / performance</h3>
<ul>
<li>Weight change across comparison window: {escape(_num(body.get('weight_change_window_kg'), 2, ' kg'))}</li>
<li>BIA fat-mass change: {escape(_num(body.get('fat_change_window_kg'), 2, ' kg'))}; BIA lean-mass change: {escape(_num(body.get('bia_lean_change_window_kg'), 2, ' kg'))}</li>
<li>Loss pace: {escape(_num(body.get('loss_rate_pct_week'), 2, '%/week'))}</li>
<li>Strength: {strength.get('up', 0)} up / {strength.get('flat', 0)} flat / {strength.get('down', 0)} down</li>
<li>Waist: {escape(_num(body.get('latest_waist_cm'), 1, ' cm'))}; change {escape(_num(body.get('waist_change_cm'), 1, ' cm'))}</li>
<li>Grip: {escape(_num(performance.get('latest_grip_kg'), 1, ' kg'))}; n={performance.get('grip_measurement_count', 0)}; trend {escape(_num(performance.get('grip_trend_pct'), 1, '%'))}</li>
</ul>

<h3>Energy model</h3>
<p>28-day maintenance: <strong>{escape(_num(e28.get('estimated_tdee'), 0, ' kcal/day'))}</strong><br>
42-day maintenance: <strong>{escape(_num(e42.get('estimated_tdee'), 0, ' kcal/day'))}</strong><br>
Planning maintenance: <strong>{escape(_num(energy.get('planning_tdee'), 0, ' kcal/day'))}</strong> ({escape(tdee_range)})<br>
28/42-day agreement: <strong>{escape(_state(energy.get('stability')))}</strong></p>

<h3>Adherence / recovery</h3>
<ul>
<li>Protein target days: {adherence.get('protein_days_met', 0)}/{adherence.get('protein_days_logged', 0)}</li>
<li>7+ hour sleep nights: {adherence.get('sleep_7h_days', 0)}/{adherence.get('sleep_days_logged', 0)}</li>
<li>Steps: {adherence.get('steps_7000_days', 0)}/{adherence.get('steps_days_logged', 0)} days >=7k; {adherence.get('steps_8000_days', 0)}/{adherence.get('steps_days_logged', 0)} days >=8k</li>
<li>RHR: {escape(_num(recovery.get('rhr_recent'), 1, ' bpm'))} vs personal baseline {escape(_num(recovery.get('rhr_baseline'), 1, ' bpm'))} — {escape(_state(recovery.get('rhr_state')))}</li>
<li>HRV: {escape(_num(recovery.get('hrv_recent'), 1, ' ms'))} vs personal baseline {escape(_num(recovery.get('hrv_baseline'), 1, ' ms'))} — {escape(_state(recovery.get('hrv_state')))}</li>
</ul>

<h3>Training dose — primary muscle working sets</h3>
<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;">
<tr><th>Muscle group</th><th>7d sets</th><th>28d sets</th><th>7d RPE>=7.5</th></tr>{group_rows}
</table>

<h3>Exact-lift strength cross-check</h3>
<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;">
<tr><th>Lift</th><th>Current 4w best</th><th>Prior 4w best</th><th>Direction</th></tr>{lift_rows}
</table>

<h3>Personal learning</h3>
<p>Comparable blocks: <strong>{personal.get('comparable_blocks', 0)}</strong>; evidence tier: <strong>{escape(_state(personal.get('evidence_tier')))}</strong>.<br>
Personal-response associations cannot change calories until at least {personal.get('adjustment_minimum', 12)} comparable blocks exist.<br>
Adaptive feedback history: {feedback.get('history_events', 0)} events; {feedback.get('mature_28d_events', 0)} matured 21-28 day effectiveness outcomes.</p>

<h3>Interpretation</h3><ul>{li(interpretation or ['No integrated interpretation available.'])}</ul>
<h3>Next-week priorities</h3><ul>{li(priorities or ['Maintain the current plan.'])}</ul>
<p style="color:#666;font-size:0.9em;">BIA fat-free mass is supporting evidence, not a direct muscle measurement. The email and Streamlit coaching status use the same canonical snapshot. Seven-day follow-up is mainly an adherence/recovery check; later 21-28 day windows are used for intervention effectiveness.</p>
</body></html>"""
    return text, html


def main() -> None:
    freshness = _load_json(FRESHNESS_JSON)
    status = str(freshness.get("overall_status", "unknown"))
    snapshot = _load_json(SNAPSHOT_JSON)
    text, html = _build(status, snapshot)
    OUTPUT_TXT.write_text(text, encoding="utf-8")
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(text)
    print(f"Saved: {OUTPUT_TXT}")
    print(f"Saved: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
