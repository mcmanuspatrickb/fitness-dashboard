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
    "fast_decision": REPORTS_DIR / "should_i_fast.txt",
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
    fast_decision = read_text(SOURCE_FILES["fast_decision"])
    strength_analysis = read_text(SOURCE_FILES["strength_analysis"])

    generated_at = datetime.now().isoformat(timespec="seconds")

    overall_grade = extract_section_by_heading_lines(weekly_report, "Overall Grade")
    next_week_focus = extract_section_by_heading_lines(weekly_report, "Next Week Focus")
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

    fast_decision_section = extract_section_by_heading_lines(fast_decision, "Decision")
    fast_reasons_against = extract_section_by_heading_lines(fast_decision, "Reasons Against")
    fast_reasons_for = extract_section_by_heading_lines(fast_decision, "Reasons For")

    latest_strength_snapshot = extract_section_by_heading_lines(strength_analysis, "Latest Weekly Snapshot")

    combined_focus_items = dedupe_keep_order(
        split_bullets(next_week_focus) + split_bullets(strength_next)
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
        overall_grade.splitlines()[0] if overall_grade else "",
    )
    lines.append(top_line if top_line else "No top-line summary available.")
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

    lines.append("Fast Decision")
    lines.append("-------------")
    lines.append(fast_decision_section if fast_decision_section else "No fast decision available.")
    if fast_reasons_against:
        lines.append("")
        lines.append("Reasons Against")
        lines.append("---------------")
        lines.append(fast_reasons_against)
    if fast_reasons_for:
        lines.append("")
        lines.append("Reasons For")
        lines.append("-----------")
        lines.append(fast_reasons_for)
    lines.append("")

    lines.append("What This Means")
    lines.append("---------------")
    lines.append(
        strength_meaning
        if strength_meaning
        else "No integrated interpretation available."
    )
    lines.append("")

    lines.append("Next Week Focus")
    lines.append("---------------")
    if combined_focus_items:
        for item in combined_focus_items:
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