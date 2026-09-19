from __future__ import annotations

from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = REPORTS_DIR / "weekly_coaching_packet.txt"

SOURCE_FILES = {
    "weekly_report": REPORTS_DIR / "weekly_coaching_report.txt",
    "strength_adjusted": REPORTS_DIR / "strength_adjusted_coaching.txt",
    "calorie_recommendation": REPORTS_DIR / "adaptive_calorie_recommendation.txt",
    "adaptive_feedback": REPORTS_DIR / "adaptive_coaching_feedback.txt",
    "lean_mass_preservation": REPORTS_DIR / "lean_mass_preservation.txt",
    "personal_response": REPORTS_DIR / "personal_response_analysis.txt",
    "strength_analysis": REPORTS_DIR / "strength_progress_analysis.txt",
}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def extract_section_by_heading_lines(text: str, heading: str) -> str:
    if not text:
        return ""

    lines = text.splitlines()
    start_idx = None

    for i, line in enumerate(lines[:-1]):
        if line.strip() == heading and set(lines[i + 1].strip()) <= {"-", "="} and lines[i + 1].strip():
            start_idx = i + 2
            break

    if start_idx is None:
        return ""

    end_idx = len(lines)
    for j in range(start_idx, len(lines) - 1):
        if lines[j].strip() and set(lines[j + 1].strip()) <= {"-", "="} and lines[j + 1].strip():
            end_idx = j
            break

    return "\n".join(lines[start_idx:end_idx]).strip()


def first_nonempty(*values: str) -> str:
    for v in values:
        if v and v.strip():
            return v.strip()
    return ""


def safe_print(lines: list[str]) -> None:
    safe_output = "\n".join(lines).encode("cp1252", errors="replace").decode("cp1252")
    print(safe_output)


def split_bullets(text: str) -> list[str]:
    if not text:
        return []

    items: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if cleaned.startswith("- "):
            cleaned = cleaned[2:].strip()
        items.append(cleaned)
    return items


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def main() -> None:
    weekly_report = read_text(SOURCE_FILES["weekly_report"])
    strength_adjusted = read_text(SOURCE_FILES["strength_adjusted"])
    calorie_reco = read_text(SOURCE_FILES["calorie_recommendation"])
    adaptive_feedback = read_text(SOURCE_FILES["adaptive_feedback"])
    lean_mass_report = read_text(SOURCE_FILES["lean_mass_preservation"])
    personal_response = read_text(SOURCE_FILES["personal_response"])
    strength_analysis = read_text(SOURCE_FILES["strength_analysis"])

    generated_at = datetime.now().isoformat(timespec="seconds")

    weekly_interpretation = extract_section_by_heading_lines(weekly_report, "Weekly Interpretation")
    next_week_focus = extract_section_by_heading_lines(weekly_report, "Next Week Focus")
    data_quality = extract_section_by_heading_lines(weekly_report, "Data Quality")
    four_week_context = extract_section_by_heading_lines(weekly_report, "4-Week Context")
    four_week_strength = extract_section_by_heading_lines(weekly_report, "4-Week Strength Context")
    body_comp = extract_section_by_heading_lines(weekly_report, "Body Composition")
    recovery = extract_section_by_heading_lines(weekly_report, "Recovery")
    nutrition = extract_section_by_heading_lines(weekly_report, "Nutrition")
    training = extract_section_by_heading_lines(weekly_report, "Training and Activity")

    strength_headline = extract_section_by_heading_lines(strength_adjusted, "Headline")
    strength_meaning = extract_section_by_heading_lines(strength_adjusted, "What This Means")
    strength_next = extract_section_by_heading_lines(strength_adjusted, "Next Week Recommendations")
    strength_snapshot = extract_section_by_heading_lines(strength_adjusted, "Strength Snapshot")

    calorie_action = extract_section_by_heading_lines(calorie_reco, "Recommendation")
    calorie_why = extract_section_by_heading_lines(calorie_reco, "Why")

    feedback_current = extract_section_by_heading_lines(adaptive_feedback, "Current Decision")
    feedback_learning = extract_section_by_heading_lines(adaptive_feedback, "Learning Status")
    feedback_recent = extract_section_by_heading_lines(adaptive_feedback, "Recent Evaluations")
    feedback_method = extract_section_by_heading_lines(adaptive_feedback, "Method Note")

    lean_personal_trend = extract_section_by_heading_lines(lean_mass_report, "Personal Trend")
    lean_interpretation = extract_section_by_heading_lines(lean_mass_report, "Interpretation")
    lean_suggestions = extract_section_by_heading_lines(lean_mass_report, "Suggestions")
    lean_method = extract_section_by_heading_lines(lean_mass_report, "Method Note")

    personal_training_active = extract_section_by_heading_lines(
        personal_response, "Training-active periods"
    )
    personal_associations = extract_section_by_heading_lines(
        personal_response, "Exploratory associations"
    )
    personal_signals = extract_section_by_heading_lines(
        personal_response, "Signals worth watching"
    )
    personal_method = extract_section_by_heading_lines(personal_response, "Method Note")

    latest_strength_snapshot = extract_section_by_heading_lines(strength_analysis, "Latest Weekly Snapshot")

    combined_focus_items = dedupe_keep_order(
        split_bullets(next_week_focus)
        + split_bullets(strength_next)
        + split_bullets(lean_suggestions)
    )

    lines: list[str] = []
    lines.append("Weekly Coaching Packet")
    lines.append("======================")
    lines.append(f"Generated: {generated_at}")
    lines.append("")

    lines.append("Top-Line Summary")
    lines.append("----------------")
    top_line = first_nonempty(
        strength_headline.splitlines()[0] if strength_headline else "",
        weekly_interpretation.splitlines()[0] if weekly_interpretation else "",
        lean_interpretation.splitlines()[0] if lean_interpretation else "",
    )
    lines.append(top_line if top_line else "No top-line summary available.")
    lines.append("")

    lines.append("Data Quality")
    lines.append("------------")
    lines.append(data_quality if data_quality else "No data-quality summary available.")
    lines.append("")

    lines.append("4-Week Context")
    lines.append("--------------")
    lines.append(four_week_context if four_week_context else "No four-week context available.")
    lines.append("")

    lines.append("4-Week Strength Context")
    lines.append("-----------------------")
    lines.append(four_week_strength if four_week_strength else "No four-week strength context available.")
    lines.append("")

    lines.append("Lean-Mass Preservation")
    lines.append("----------------------")
    if lean_personal_trend:
        lines.append("Personal Trend")
        lines.append("--------------")
        lines.append(lean_personal_trend)
        lines.append("")
    if lean_interpretation:
        lines.append("Interpretation")
        lines.append("--------------")
        lines.append(lean_interpretation)
        lines.append("")
    if lean_suggestions:
        lines.append("Suggestions")
        lines.append("-----------")
        lines.append(lean_suggestions)
        lines.append("")
    if lean_method:
        lines.append("Method Note")
        lines.append("-----------")
        lines.append(lean_method)
    if not any([lean_personal_trend, lean_interpretation, lean_suggestions, lean_method]):
        lines.append("No lean-mass preservation analysis available.")
    lines.append("")

    lines.append("Personal Response Analysis")
    lines.append("--------------------------")
    if personal_training_active:
        lines.append("Training-Active Historical Context")
        lines.append("----------------------------------")
        lines.append(personal_training_active)
        lines.append("")
    if personal_associations:
        lines.append("Exploratory Associations")
        lines.append("------------------------")
        lines.append(personal_associations)
        lines.append("")
    if personal_signals:
        lines.append("Signals Worth Watching")
        lines.append("----------------------")
        lines.append(personal_signals)
        lines.append("")
    if personal_method:
        lines.append("Evidence Guardrail")
        lines.append("------------------")
        lines.append(personal_method)
    if not any([personal_training_active, personal_associations, personal_signals, personal_method]):
        lines.append("No personal-response analysis is available yet.")
    lines.append("")

    lines.append("Adaptive Coaching Feedback")
    lines.append("--------------------------")
    if feedback_current:
        lines.append("Current Decision")
        lines.append("----------------")
        lines.append(feedback_current)
        lines.append("")
    if feedback_learning:
        lines.append("Learning Status")
        lines.append("---------------")
        lines.append(feedback_learning)
        lines.append("")
    if feedback_recent:
        lines.append("Recent Evaluations")
        lines.append("------------------")
        lines.append(feedback_recent)
        lines.append("")
    if feedback_method:
        lines.append("Method Note")
        lines.append("-----------")
        lines.append(feedback_method)
    if not any([feedback_current, feedback_learning, feedback_recent, feedback_method]):
        lines.append("No adaptive coaching feedback is available yet.")
    lines.append("")

    lines.append("Body Composition and Recovery")
    lines.append("-----------------------------")
    lines.append(body_comp if body_comp else "No body composition summary available.")
    lines.append("")
    lines.append(recovery if recovery else "No recovery summary available.")
    lines.append("")

    lines.append("Nutrition and Training")
    lines.append("----------------------")
    lines.append(nutrition if nutrition else "No nutrition summary available.")
    lines.append("")
    lines.append(training if training else "No training summary available.")
    lines.append("")

    lines.append("Strength Snapshot")
    lines.append("-----------------")
    lines.append(
        latest_strength_snapshot
        if latest_strength_snapshot
        else (strength_snapshot if strength_snapshot else "No strength snapshot available.")
    )
    lines.append("")

    lines.append("Calorie Recommendation")
    lines.append("----------------------")
    if calorie_action:
        lines.append(calorie_action)
    else:
        lines.append("No calorie recommendation available.")
    if calorie_why:
        lines.append("")
        lines.append(calorie_why)
    lines.append("")

    lines.append("Weekly Interpretation")
    lines.append("---------------------")
    lines.append(
        weekly_interpretation
        if weekly_interpretation
        else (
            strength_meaning
            if strength_meaning
            else "No integrated interpretation available."
        )
    )
    lines.append("")

    lines.append("Next Week Focus")
    lines.append("---------------")
    if combined_focus_items:
        for item in combined_focus_items[:4]:
            lines.append(f"- {item}")
    else:
        lines.append("No next-week focus items available.")
    lines.append("")

    lines.append("Source Files")
    lines.append("------------")
    for key, path in SOURCE_FILES.items():
        lines.append(f"{key}: {'found' if path.exists() else 'missing'} | {path.name}")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")

    print(f"Saved: {OUT_PATH}")
    print()
    safe_print(lines)


if __name__ == "__main__":
    main()
