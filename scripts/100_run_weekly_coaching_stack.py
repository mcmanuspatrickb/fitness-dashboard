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

# Adjust this list over time as your system evolves.
# Right now this focuses on the core analysis / coaching layer.
PIPELINE = [
    ("30_build_daily_metrics.py", "Build analytics.daily_metrics"),
    ("31_build_daily_trends.py", "Build analytics.daily_trends"),
    ("40_build_weekly_metrics.py", "Build analytics.weekly_metrics"),
    ("41_build_historical_daily_metrics.py", "Build analytics.historical_daily_metrics"),
    ("71_strength_progress_analysis.py", "Build strength progress analysis"),
    ("72_strength_adjusted_coaching.py", "Build strength-adjusted coaching"),
    ("73_adaptive_calorie_recommendation.py", "Build adaptive calorie recommendation"),
    ("70_should_i_fast.py", "Build fast decision"),
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
    except Exception as e:
        return False, f"[ERROR] {script_name} | {description}\nException: {e}\n"

    status = result.returncode == 0

    output = []
    output.append(f"[{'OK' if status else 'FAIL'}] {script_name} | {description}")
    if result.stdout.strip():
        output.append("STDOUT:")
        output.append(result.stdout.strip())
    if result.stderr.strip():
        output.append("STDERR:")
        output.append(result.stderr.strip())
    output.append("")

    return status, "\n".join(output)


def main() -> None:
    started_at = datetime.now()

    log_lines: list[str] = []
    log_lines.append("Weekly Coaching Stack Run")
    log_lines.append("=========================")
    log_lines.append(f"Started: {started_at.isoformat(timespec='seconds')}")
    log_lines.append("")

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

    log_lines.append("Summary")
    log_lines.append("-------")
    log_lines.append(f"Finished: {finished_at.isoformat(timespec='seconds')}")
    log_lines.append(f"Duration: {duration}")
    log_lines.append(f"Successes: {successes}")
    log_lines.append(f"Failures: {failures}")

    LOG_PATH.write_text("\n".join(log_lines), encoding="utf-8")

    print(f"Saved: {LOG_PATH}")
    print()
    print("\n".join(log_lines))


if __name__ == "__main__":
    main()