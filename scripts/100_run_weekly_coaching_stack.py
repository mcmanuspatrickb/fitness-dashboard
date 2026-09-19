from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

LOG_PATH = REPORTS_DIR / "weekly_coaching_stack_log.txt"

# Raw source refresh happens separately in 05_refresh_current_sources.py.
# This stack rebuilds the clean/analytics layers from whatever current source
# data is available, then generates the routine fat-loss / muscle-preservation
# coaching outputs. Fasting analysis remains available as an on-demand tool,
# but it is intentionally not part of the automatic weekly decision path.
# Personal-response evidence is built before the adaptive calorie model so the
# calorie decision always sees the newest qualifying historical blocks.
# The feedback step then evaluates prior calorie decisions and logs the current
# one before the packet is assembled.
PIPELINE = [
    ("20_build_clean_interventions.py", "Build clean interventions"),
    ("21_build_clean_body_composition.py", "Build clean body composition"),
    ("22_build_clean_fitbit_daily.py", "Build clean activity/recovery data"),
    ("23_build_clean_training_summary.py", "Build clean training summary"),
    ("24_build_clean_nutrition_daily.py", "Build clean nutrition data"),
    ("30_build_daily_metrics.py", "Build analytics.daily_metrics"),
    ("31_build_daily_trends.py", "Build analytics.daily_trends"),
    ("40_build_weekly_metrics.py", "Build analytics.weekly_metrics"),
    ("41_build_historical_daily_metrics.py", "Build analytics.historical_daily_metrics"),
    ("71_strength_progress_analysis.py", "Build strength progress analysis"),
    ("72_strength_adjusted_coaching.py", "Build strength-adjusted coaching"),
    ("75_personal_response_analysis.py", "Build personal response analysis"),
    ("73_adaptive_calorie_recommendation.py", "Build adaptive calorie recommendation"),
    ("76_adaptive_coaching_feedback.py", "Update adaptive coaching feedback loop"),
    ("74_lean_mass_preservation.py", "Build lean-mass preservation analysis"),
    ("80_weekly_coaching_report.py", "Build weekly coaching report"),
    ("81_build_weekly_coaching_packet.py", "Build weekly coaching packet"),
]


def run_script(script_name: str, description: str) -> tuple[bool, str]:
    script_path = SCRIPTS_DIR / script_name

    if not script_path.exists():
        return False, f"[MISSING] {script_name} | {description}\n"

    cmd = [sys.executable, str(script_path)]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return False, f"[ERROR] {script_name} | {description}\nException: {exc}\n"

    status = result.returncode == 0

    output = [f"[{'OK' if status else 'FAIL'}] {script_name} | {description}"]
    if result.stdout.strip():
        output.extend(["STDOUT:", result.stdout.strip()])
    if result.stderr.strip():
        output.extend(["STDERR:", result.stderr.strip()])
    output.append("")

    return status, "\n".join(output)


def main() -> None:
    started_at = datetime.now()

    log_lines: list[str] = [
        "Weekly Coaching Stack Run",
        "=========================",
        f"Started: {started_at.isoformat(timespec='seconds')}",
        "",
    ]

    successes = 0
    failures = 0

    for script_name, description in PIPELINE:
        ok, text = run_script(script_name, description)
        log_lines.append(text)
        if ok:
            successes += 1
        else:
            failures += 1

    finished_at = datetime.now()
    duration = finished_at - started_at

    log_lines.extend(
        [
            "Summary",
            "-------",
            f"Finished: {finished_at.isoformat(timespec='seconds')}",
            f"Duration: {duration}",
            f"Successes: {successes}",
            f"Failures: {failures}",
        ]
    )

    LOG_PATH.write_text("\n".join(log_lines), encoding="utf-8")

    print(f"Saved: {LOG_PATH}")
    print()
    print("\n".join(log_lines))

    # The old version always exited 0, even when internal scripts failed.
    # A real pipeline failure should now make the workflow fail visibly.
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
