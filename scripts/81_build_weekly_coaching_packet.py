from __future__ import annotations

from datetime import datetime
from pathlib import Path

from report_context import load_report_context


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = REPORTS_DIR / "weekly_coaching_packet.txt"

SOURCE_FILES = {
    "phase": REPORTS_DIR / "phase_detection.txt",
    "guardrail": REPORTS_DIR / "cut_stress_guardrail.txt",
    "calorie_recommendation": REPORTS_DIR / "adaptive_calorie_recommendation.txt",
    "adaptive_feedback": REPORTS_DIR / "adaptive_coaching_feedback.txt",
    "weekly_report": REPORTS_DIR / "weekly_coaching_report.txt",
    "lean_mass_preservation": REPORTS_DIR / "lean_mass_preservation.txt",
    "personal_response": REPORTS_DIR / "personal_response_analysis.txt",
    "strength_adjusted": REPORTS_DIR / "strength_adjusted_coaching.txt",
    "strength_analysis": REPORTS_DIR / "strength_progress_analysis.txt",
}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def section(text: str, heading: str) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    for i, line in enumerate(lines[:-1]):
        underline = lines[i + 1].strip()
        if line.strip() == heading and underline and set(underline) <= {"-", "="}:
            start = i + 2
            end = len(lines)
            for j in range(start, len(lines) - 1):
                next_line = lines[j + 1].strip()
                if lines[j].strip() and next_line and set(next_line) <= {"-", "="}:
                    end = j
                    break
            return "\n".join(lines[start:end]).strip()
    return ""


def add_block(lines: list[str], heading: str, body: str, fallback: str) -> None:
    lines.extend([heading, "-" * len(heading), body if body else fallback, ""])


def fmt(value, digits: int = 1, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{digits}f}{suffix}"


def main() -> None:
    texts = {key: read_text(path) for key, path in SOURCE_FILES.items()}
    context = load_report_context()
    performance = context.get("performance", {})

    phase_body = section(texts["phase"], "Current Context")
    phase_head = "\n".join([
        line for line in texts["phase"].splitlines()
        if line.startswith("current phase:") or line.startswith("suggestion:")
    ])
    guardrail_body = section(texts["guardrail"], "Signals of Concern")
    guardrail_reassuring = section(texts["guardrail"], "Reassuring Signals")
    guardrail_head = "\n".join([
        line for line in texts["guardrail"].splitlines()
        if line.startswith("status:") or line.startswith("interpretation:")
    ])
    calorie = section(texts["calorie_recommendation"], "Recommendation")
    calorie_why = section(texts["calorie_recommendation"], "Why")
    feedback_current = section(texts["adaptive_feedback"], "Current Decision")
    feedback_learning = section(texts["adaptive_feedback"], "Learning Status")
    feedback_recent = section(texts["adaptive_feedback"], "Recent Evaluations")
    weekly_interpretation = section(texts["weekly_report"], "Weekly Interpretation")
    next_week_focus = section(texts["weekly_report"], "Next Week Focus")
    four_week = section(texts["weekly_report"], "4-Week Context")
    four_week_strength = section(texts["weekly_report"], "4-Week Strength Context")
    lean_trend = section(texts["lean_mass_preservation"], "Personal Trend")
    lean_interpretation = section(texts["lean_mass_preservation"], "Interpretation")
    lean_suggestions = section(texts["lean_mass_preservation"], "Suggestions")
    personal_active = section(texts["personal_response"], "Training-active periods")
    personal_assoc = section(texts["personal_response"], "Exploratory associations")

    performance_lines = [
        f"latest grip: {fmt(performance.get('latest_grip_overall_kg'), 1, ' kg')} ({performance.get('latest_grip_date') or 'n/a'})",
        f"left/right grip: {fmt(performance.get('latest_grip_left_kg'), 1, ' kg')} / {fmt(performance.get('latest_grip_right_kg'), 1, ' kg')}",
        f"grip asymmetry: {fmt(performance.get('latest_grip_asymmetry_pct'), 1, '%')}",
        f"grip measurements available: {performance.get('grip_measurement_count', 0)}",
        f"grip short-term trend: {fmt(performance.get('grip_trend_pct'), 1, '%')}",
        f"latest waist: {fmt(performance.get('latest_waist_cm'), 1, ' cm')} ({performance.get('latest_waist_date') or 'n/a'})",
        f"waist change vs prior measurement: {fmt(performance.get('waist_change_cm'), 1, ' cm')}",
    ]

    lines = [
        "Weekly Coaching Packet",
        "======================",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
    ]
    add_block(lines, "Phase", "\n".join(x for x in [phase_head, phase_body] if x), "No phase analysis available.")
    add_block(lines, "Recovery Guardrail", "\n".join(x for x in [guardrail_head, guardrail_body, guardrail_reassuring] if x), "No recovery guardrail available.")
    add_block(lines, "Calorie Recommendation", "\n\n".join(x for x in [calorie, calorie_why] if x), "No calorie recommendation available.")
    add_block(lines, "Adaptive Coaching Feedback", "\n\n".join(x for x in [feedback_current, feedback_learning, feedback_recent] if x), "No adaptive feedback available yet.")
    add_block(lines, "Performance Markers", "\n".join(performance_lines), "No grip or waist data available.")
    add_block(lines, "4-Week Context", four_week, "No four-week context available.")
    add_block(lines, "4-Week Strength Context", four_week_strength, "No four-week strength context available.")
    add_block(lines, "Lean-Mass Preservation", "\n\n".join(x for x in [lean_trend, lean_interpretation, lean_suggestions] if x), "No lean-mass analysis available.")
    add_block(lines, "Personal Response Analysis", "\n\n".join(x for x in [personal_active, personal_assoc] if x), "Personal-response evidence is still building.")
    add_block(lines, "Weekly Interpretation", weekly_interpretation, "No integrated interpretation available.")
    add_block(lines, "Next Week Focus", next_week_focus, "No next-week focus items available.")

    lines.extend(["Source Files", "------------"])
    for key, path in SOURCE_FILES.items():
        lines.append(f"{key}: {'found' if path.exists() else 'missing'} | {path.name}")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {OUT_PATH}")
    print()
    print("\n".join(lines).encode("cp1252", errors="replace").decode("cp1252"))


if __name__ == "__main__":
    main()
