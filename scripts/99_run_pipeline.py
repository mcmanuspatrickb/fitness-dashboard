from __future__ import annotations

from pathlib import Path
import argparse
import subprocess
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
LOGS_DIR = PROJECT_ROOT / "logs"


FULL_PIPELINE_STEPS: list[tuple[str, str]] = [
    ("10_ingest_interventions.py", "Ingest interventions from Google Sheets"),
    ("12_ingest_withings_history.py", "Ingest Withings history"),
    ("14_ingest_fitbit_daily.py", "Ingest Fitbit daily data"),
    ("15_ingest_hevy.py", "Ingest Hevy workouts"),
    ("17_import_mfp_fasting_history.py", "Import MFP historical fasting history"),
    ("20_build_clean_interventions.py", "Build clean interventions table"),
    ("21_build_clean_body_composition.py", "Build clean body composition"),
    ("22_build_clean_fitbit_daily.py", "Build clean Fitbit daily"),
    ("23_build_clean_training_summary.py", "Build clean training summary"),
    ("24_build_clean_nutrition_daily.py", "Build clean nutrition daily"),
    ("30_build_daily_metrics.py", "Build analytics.daily_metrics"),
    ("31_build_daily_trends.py", "Build analytics.daily_trends"),
    ("41_build_historical_daily_metrics.py", "Build analytics.historical_daily_metrics"),
    ("40_build_weekly_metrics.py", "Build analytics.weekly_metrics"),
    ("50_generate_weekly_report.py", "Generate weekly report outputs"),
    ("51_generate_daily_status.py", "Generate daily status outputs"),
    ("43_identify_fasting_blocks.py", "Identify fasting blocks"),
    ("44_filtered_fasting_blocks.py", "Filter fasting blocks"),
    ("45_block_bodycomp_analysis.py", "Analyze fasting block body composition"),
    ("46_block_bodycomp_quality.py", "Analyze fasting block body composition quality"),
    ("47_fat_loss_efficiency.py", "Calculate fasting block fat loss efficiency"),
    ("48_estimate_tdee_blocks.py", "Estimate TDEE from fasting blocks"),
    ("52_generate_intervention_insights.py", "Generate intervention insights summary"),
]

ANALYTICS_ONLY_STEPS: list[tuple[str, str]] = [
    ("20_build_clean_interventions.py", "Build clean interventions table"),
    ("21_build_clean_body_composition.py", "Build clean body composition"),
    ("22_build_clean_fitbit_daily.py", "Build clean Fitbit daily"),
    ("23_build_clean_training_summary.py", "Build clean training summary"),
    ("24_build_clean_nutrition_daily.py", "Build clean nutrition daily"),
    ("30_build_daily_metrics.py", "Build analytics.daily_metrics"),
    ("31_build_daily_trends.py", "Build analytics.daily_trends"),
    ("41_build_historical_daily_metrics.py", "Build analytics.historical_daily_metrics"),
    ("40_build_weekly_metrics.py", "Build analytics.weekly_metrics"),
    ("50_generate_weekly_report.py", "Generate weekly report outputs"),
    ("51_generate_daily_status.py", "Generate daily status outputs"),
    ("43_identify_fasting_blocks.py", "Identify fasting blocks"),
    ("44_filtered_fasting_blocks.py", "Filter fasting blocks"),
    ("45_block_bodycomp_analysis.py", "Analyze fasting block body composition"),
    ("46_block_bodycomp_quality.py", "Analyze fasting block body composition quality"),
    ("47_fat_loss_efficiency.py", "Calculate fasting block fat loss efficiency"),
    ("48_estimate_tdee_blocks.py", "Estimate TDEE from fasting blocks"),
    ("52_generate_intervention_insights.py", "Generate intervention insights summary"),
]

REPORT_ONLY_STEPS: list[tuple[str, str]] = [
    ("50_generate_weekly_report.py", "Generate weekly report outputs"),
    ("51_generate_daily_status.py", "Generate daily status outputs"),
]

CRONOMETER_EXPORT_STEP = (
    "61_cronometer_export.py",
    "Export Daily Nutrition CSV from Cronometer",
)

CRONOMETER_IMPORT_STEP = (
    "62_import_cronometer_export.py",
    "Import latest Cronometer CSV into raw.nutrition_daily",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the fitness dashboard pipeline."
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--full",
        action="store_true",
        help="Run the full pipeline including ingestion, clean, analytics, and reports.",
    )
    mode_group.add_argument(
        "--analytics-only",
        action="store_true",
        help="Skip external ingestion and rebuild clean, analytics, and reports only.",
    )
    mode_group.add_argument(
        "--report-only",
        action="store_true",
        help="Only regenerate the weekly and daily report outputs.",
    )

    parser.add_argument(
        "--with-cronometer",
        action="store_true",
        help="Include Cronometer export/import before the selected pipeline mode.",
    )
    parser.add_argument(
        "--cronometer-import-only",
        action="store_true",
        help="Import the latest Cronometer CSV before the selected pipeline mode, without browser export.",
    )
    parser.add_argument(
        "--skip-report",
        action="store_true",
        help="Skip report scripts for full or analytics-only runs.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Keep running remaining steps after a failed script.",
    )
    parser.add_argument(
        "--from-step",
        type=str,
        help=(
            "Start from a specific script name or numeric prefix. "
            "Examples: --from-step 30 or --from-step 30_build_daily_metrics.py"
        ),
    )
    parser.add_argument(
        "--list-steps",
        action="store_true",
        help="Print the resolved steps for the selected mode and exit.",
    )

    return parser.parse_args()


def resolve_steps(args: argparse.Namespace) -> list[tuple[str, str]]:
    if args.report_only:
        steps = REPORT_ONLY_STEPS.copy()
    elif args.analytics_only:
        steps = ANALYTICS_ONLY_STEPS.copy()
    else:
        steps = FULL_PIPELINE_STEPS.copy()

    if args.skip_report:
        steps = [
            step
            for step in steps
            if step[0] not in {"50_generate_weekly_report.py", "51_generate_daily_status.py"}
        ]

    return steps


def prepend_cronometer_steps(
    steps: list[tuple[str, str]],
    args: argparse.Namespace,
) -> list[tuple[str, str]]:
    prefixed_steps: list[tuple[str, str]] = []

    if args.with_cronometer:
        prefixed_steps.append(CRONOMETER_EXPORT_STEP)
        prefixed_steps.append(CRONOMETER_IMPORT_STEP)
    elif args.cronometer_import_only:
        prefixed_steps.append(CRONOMETER_IMPORT_STEP)

    return prefixed_steps + steps


def normalize_step_token(value: str) -> str:
    value = value.strip()
    if value.endswith(".py"):
        value = value[:-3]
    return value.lower()


def filter_from_step(
    steps: list[tuple[str, str]],
    from_step: str | None,
) -> list[tuple[str, str]]:
    if not from_step:
        return steps

    token = normalize_step_token(from_step)
    start_index: int | None = None

    for idx, (script_name, _) in enumerate(steps):
        normalized_name = normalize_step_token(script_name)
        numeric_prefix = normalized_name.split("_", 1)[0]

        if token == normalized_name or token == numeric_prefix:
            start_index = idx
            break

    if start_index is None:
        available = ", ".join(script_name for script_name, _ in steps)
        raise ValueError(
            f"Could not find step '{from_step}'. Available steps: {available}"
        )

    return steps[start_index:]


def print_plan(steps: list[tuple[str, str]]) -> None:
    print("\nPlanned steps:")
    for idx, (script_name, description) in enumerate(steps, start=1):
        print(f"{idx:>2}. {script_name}  —  {description}")


def ensure_logs_dir() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def write_run_summary(summary_path: Path, lines: list[str]) -> None:
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_script(
    script_name: str,
    description: str,
    run_id: str,
) -> tuple[float, Path]:
    script_path = SCRIPTS_DIR / script_name

    if not script_path.exists():
        raise FileNotFoundError(f"Missing script: {script_path}")

    step_log_path = LOGS_DIR / f"{run_id}_{script_name.replace('.py', '')}.log"

    print(f"\n{'=' * 80}")
    print(f"RUNNING: {script_name}")
    print(f"TASK:    {description}")
    print(f"LOG:     {step_log_path}")
    print(f"{'=' * 80}")

    started = time.time()
    started_text = time.strftime("%Y-%m-%d %H:%M:%S")

    with step_log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"script: {script_name}\n")
        log_file.write(f"description: {description}\n")
        log_file.write(f"started_at: {started_text}\n")
        log_file.write(f"python: {sys.executable}\n")
        log_file.write(f"project_root: {PROJECT_ROOT}\n")
        log_file.write("=" * 80 + "\n\n")

        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=PROJECT_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )

        elapsed = time.time() - started
        finished_text = time.strftime("%Y-%m-%d %H:%M:%S")
        log_file.write("\n" + "=" * 80 + "\n")
        log_file.write(f"finished_at: {finished_text}\n")
        log_file.write(f"elapsed_seconds: {elapsed:.2f}\n")
        log_file.write(f"return_code: {result.returncode}\n")

    if result.returncode != 0:
        raise RuntimeError(
            f"Script failed: {script_name} (exit code {result.returncode}). "
            f"See log: {step_log_path}"
        )

    print(f"Completed {script_name} in {elapsed:.1f}s")
    return elapsed, step_log_path


def main() -> None:
    args = parse_args()

    print("Fitness dashboard pipeline runner")
    print(f"Project root: {PROJECT_ROOT}")

    ensure_logs_dir()
    run_id = time.strftime("%Y%m%d_%H%M%S")
    run_summary_path = LOGS_DIR / f"{run_id}_pipeline_summary.log"

    steps = resolve_steps(args)
    steps = prepend_cronometer_steps(steps, args)
    steps = filter_from_step(steps, args.from_step)

    if not steps:
        print("No steps to run.")
        return

    print_plan(steps)

    summary_lines = [
        "FITNESS DASHBOARD PIPELINE RUN",
        "=" * 80,
        f"run_id: {run_id}",
        f"started_at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"project_root: {PROJECT_ROOT}",
        f"python: {sys.executable}",
        "",
        "planned_steps:",
    ]
    for idx, (script_name, description) in enumerate(steps, start=1):
        summary_lines.append(f"{idx:>2}. {script_name} — {description}")

    write_run_summary(run_summary_path, summary_lines)

    if args.list_steps:
        print(f"\nStep list written to: {run_summary_path}")
        return

    failures: list[str] = []
    pipeline_started = time.time()

    for script_name, description in steps:
        try:
            elapsed, log_path = run_script(script_name, description, run_id)
            summary_lines.append(
                f"SUCCESS: {script_name} | {elapsed:.1f}s | log={log_path.name}"
            )
            write_run_summary(run_summary_path, summary_lines)
        except Exception as exc:
            message = f"{script_name}: {exc}"
            failures.append(message)
            summary_lines.append(f"FAILED: {message}")
            write_run_summary(run_summary_path, summary_lines)

            print(f"\nFAILED: {message}")

            if not args.continue_on_error:
                total_elapsed = time.time() - pipeline_started
                summary_lines.append("")
                summary_lines.append(f"finished_at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                summary_lines.append(f"total_elapsed_seconds: {total_elapsed:.2f}")
                summary_lines.append("result: FAILED")
                write_run_summary(run_summary_path, summary_lines)

                print("\nPipeline stopped on first failure.")
                print(f"Run summary: {run_summary_path}")
                sys.exit(1)

    total_elapsed = time.time() - pipeline_started

    summary_lines.append("")
    summary_lines.append(f"finished_at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    summary_lines.append(f"total_elapsed_seconds: {total_elapsed:.2f}")

    print(f"\n{'=' * 80}")
    print("PIPELINE COMPLETE")
    print(f"{'=' * 80}")

    if failures:
        summary_lines.append("result: COMPLETED_WITH_FAILURES")
        write_run_summary(run_summary_path, summary_lines)

        print("Completed with failures:")
        for failure in failures:
            print(f" - {failure}")
        print(f"Run summary: {run_summary_path}")
        sys.exit(1)

    summary_lines.append("result: SUCCESS")
    write_run_summary(run_summary_path, summary_lines)

    print("All steps completed successfully.")
    print(f"Run summary: {run_summary_path}")
    print("Key outputs:")
    print(f" - {PROJECT_ROOT / 'db' / 'fitness.duckdb'}")
    print(f" - {PROJECT_ROOT / 'reports' / 'weekly_metrics_latest.csv'}")
    print(f" - {PROJECT_ROOT / 'reports' / 'chart_weight_trend.png'}")
    print(f" - {PROJECT_ROOT / 'reports' / 'chart_steps_trend.png'}")
    print(f" - {PROJECT_ROOT / 'reports' / 'chart_resting_hr_trend.png'}")
    print(f" - {PROJECT_ROOT / 'reports' / 'daily_status_latest.csv'}")
    print(f" - {PROJECT_ROOT / 'reports' / 'daily_status_latest.txt'}")
    print(f" - {PROJECT_ROOT / 'reports' / 'fasting_blocks_analysis.csv'}")
    print(f" - {PROJECT_ROOT / 'reports' / 'fasting_blocks_filtered.csv'}")
    print(f" - {PROJECT_ROOT / 'reports' / 'fat_loss_efficiency.csv'}")
    print(f" - {PROJECT_ROOT / 'reports' / 'historical_tdee_estimates.csv'}")
    print(f" - {PROJECT_ROOT / 'reports' / 'intervention_insights_latest.csv'}")
    print(f" - {PROJECT_ROOT / 'reports' / 'intervention_insights_latest.txt'}")


if __name__ == "__main__":
    main()