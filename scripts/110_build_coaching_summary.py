from __future__ import annotations

from pathlib import Path
from typing import Optional
import math

import pandas as pd


REPORTS_DIR = Path("reports")
OUTPUT_TXT = REPORTS_DIR / "weekly_coaching_summary.txt"
OUTPUT_HTML = REPORTS_DIR / "weekly_coaching_summary.html"


DATE_CANDIDATES = [
    "date",
    "day",
    "log_date",
    "measurement_date",
    "timestamp",
    "datetime",
]

WEIGHT_CANDIDATES = [
    "weight",
    "body_weight",
    "weight_kg",
    "mass",
]

CALORIE_CANDIDATES = [
    "calories",
    "kcal",
    "energy",
    "energy_kcal",
    "calories_consumed",
]

PROTEIN_CANDIDATES = [
    "protein",
    "protein_g",
]

STEPS_CANDIDATES = [
    "steps",
    "step_count",
]

SLEEP_CANDIDATES = [
    "sleep_hours",
    "sleep_duration",
    "sleep",
    "minutes_asleep",
]

WORKOUT_CANDIDATES = [
    "workout",
    "worked_out",
    "training",
    "lifted",
    "exercise",
    "session",
]

BOOLEAN_TRUE_VALUES = {"1", "true", "yes", "y", "done", "completed"}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [
        str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in out.columns
    ]
    return out


def find_first_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def try_parse_dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def to_boolish_count(series: pd.Series) -> int:
    s = (
        series.astype(str)
        .str.strip()
        .str.lower()
    )
    return int(s.isin(BOOLEAN_TRUE_VALUES).sum())


def load_csvs(reports_dir: Path) -> list[pd.DataFrame]:
    dataframes: list[pd.DataFrame] = []
    for path in sorted(reports_dir.rglob("*.csv")):
        try:
            df = pd.read_csv(path)
            if not df.empty:
                df = normalize_columns(df)
                df.attrs["source_path"] = str(path)
                dataframes.append(df)
        except Exception:
            continue
    return dataframes


def best_dated_dataframe(dataframes: list[pd.DataFrame]) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    best_df = None
    best_date_col = None
    best_count = -1

    for df in dataframes:
        date_col = find_first_column(df, DATE_CANDIDATES)
        if not date_col:
            continue

        parsed = try_parse_dates(df[date_col])
        count = int(parsed.notna().sum())
        if count > best_count:
            candidate = df.copy()
            candidate[date_col] = parsed
            best_df = candidate
            best_date_col = date_col
            best_count = count

    return best_df, best_date_col


def restrict_to_latest_week(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    dated = df[df[date_col].notna()].copy()
    if dated.empty:
        return df.copy()

    latest_date = dated[date_col].max()
    start_date = latest_date - pd.Timedelta(days=6)
    return dated[(dated[date_col] >= start_date) & (dated[date_col] <= latest_date)].copy()


def mean_or_none(series: pd.Series) -> Optional[float]:
    s = to_numeric(series).dropna()
    if s.empty:
        return None
    return float(s.mean())


def latest_minus_earliest(series: pd.Series) -> Optional[float]:
    s = to_numeric(series).dropna()
    if len(s) < 2:
        return None
    return float(s.iloc[-1] - s.iloc[0])


def format_num(value: Optional[float], decimals: int = 1, suffix: str = "") -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value:.{decimals}f}{suffix}"


def extract_metrics(df: pd.DataFrame) -> dict:
    metrics: dict = {}

    weight_col = find_first_column(df, WEIGHT_CANDIDATES)
    calories_col = find_first_column(df, CALORIE_CANDIDATES)
    protein_col = find_first_column(df, PROTEIN_CANDIDATES)
    steps_col = find_first_column(df, STEPS_CANDIDATES)
    sleep_col = find_first_column(df, SLEEP_CANDIDATES)
    workout_col = find_first_column(df, WORKOUT_CANDIDATES)

    metrics["days_in_window"] = len(df)

    if weight_col:
        weight_series = to_numeric(df[weight_col]).dropna()
        metrics["weight_avg"] = float(weight_series.mean()) if not weight_series.empty else None
        metrics["weight_change"] = latest_minus_earliest(weight_series)
        metrics["weight_latest"] = float(weight_series.iloc[-1]) if not weight_series.empty else None
    else:
        metrics["weight_avg"] = None
        metrics["weight_change"] = None
        metrics["weight_latest"] = None

    if calories_col:
        metrics["calories_avg"] = mean_or_none(df[calories_col])
    else:
        metrics["calories_avg"] = None

    if protein_col:
        protein_series = to_numeric(df[protein_col]).dropna()
        metrics["protein_avg"] = float(protein_series.mean()) if not protein_series.empty else None
        metrics["protein_days_over_100"] = int((protein_series >= 100).sum()) if not protein_series.empty else 0
    else:
        metrics["protein_avg"] = None
        metrics["protein_days_over_100"] = 0

    if steps_col:
        metrics["steps_avg"] = mean_or_none(df[steps_col])
    else:
        metrics["steps_avg"] = None

    if sleep_col:
        sleep_series = to_numeric(df[sleep_col]).dropna()
        if not sleep_series.empty:
            if sleep_series.mean() > 100:
                sleep_series = sleep_series / 60.0
            metrics["sleep_avg_hours"] = float(sleep_series.mean())
        else:
            metrics["sleep_avg_hours"] = None
    else:
        metrics["sleep_avg_hours"] = None

    if workout_col and workout_col in df.columns:
        col = df[workout_col]
        if pd.api.types.is_numeric_dtype(col):
            metrics["training_sessions"] = int((to_numeric(col).fillna(0) > 0).sum())
        else:
            metrics["training_sessions"] = to_boolish_count(col)
    else:
        metrics["training_sessions"] = None

    return metrics


def build_observations(metrics: dict) -> list[str]:
    obs: list[str] = []

    weight_change = metrics.get("weight_change")
    if weight_change is not None:
        if weight_change < -0.2:
            obs.append(
                f"Weight trend moved down by {abs(weight_change):.2f} kg over the last week, which is consistent with fat-loss progress."
            )
        elif weight_change > 0.2:
            obs.append(
                f"Weight trend moved up by {weight_change:.2f} kg over the last week."
            )
        else:
            obs.append(
                "Weight stayed relatively stable over the last week."
            )

    calories_avg = metrics.get("calories_avg")
    if calories_avg is not None:
        obs.append(f"Average calories were {calories_avg:.0f} kcal/day.")

    protein_avg = metrics.get("protein_avg")
    if protein_avg is not None:
        obs.append(f"Average protein intake was {protein_avg:.0f} g/day.")

    steps_avg = metrics.get("steps_avg")
    if steps_avg is not None:
        obs.append(f"Average daily steps were {steps_avg:.0f}.")

    sleep_avg = metrics.get("sleep_avg_hours")
    if sleep_avg is not None:
        obs.append(f"Average sleep was {sleep_avg:.1f} hours/night.")

    training_sessions = metrics.get("training_sessions")
    if training_sessions is not None:
        obs.append(f"Training sessions logged this week: {training_sessions}.")

    return obs


def build_recommendations(metrics: dict) -> list[str]:
    recs: list[str] = []

    weight_change = metrics.get("weight_change")
    protein_avg = metrics.get("protein_avg")
    steps_avg = metrics.get("steps_avg")
    sleep_avg = metrics.get("sleep_avg_hours")
    training_sessions = metrics.get("training_sessions")

    if weight_change is not None and weight_change > 0.2:
        recs.append(
            "Weight is trending up. Tighten calories slightly or add consistent daily movement before making aggressive changes."
        )
    elif weight_change is not None and weight_change < -1.0:
        recs.append(
            "Weight is dropping quickly. Make sure protein is high and training performance is holding so muscle retention stays on track."
        )
    elif weight_change is not None and -1.0 <= weight_change <= -0.2:
        recs.append(
            "Fat-loss pace looks reasonable. Keep the plan steady and avoid changing too many variables at once."
        )

    if protein_avg is not None and protein_avg < 120:
        recs.append(
            "Protein looks a bit low for a cut. Aim for a stronger daily protein floor to support satiety and muscle retention."
        )

    if steps_avg is not None and steps_avg < 7000:
        recs.append(
            "Daily movement is modest. Increasing steps is a low-friction way to support fat loss without cutting food harder."
        )

    if sleep_avg is not None and sleep_avg < 7.0:
        recs.append(
            "Sleep is on the low side. Improving sleep can help recovery, hunger control, and training quality."
        )

    if training_sessions is not None and training_sessions < 3:
        recs.append(
            "Training frequency looks light. Keeping resistance training consistent will help preserve muscle while losing fat."
        )

    if not recs:
        recs.append(
            "No major red flags detected this week. Keep focusing on consistency and compare trends over multiple weeks, not single days."
        )

    return recs[:3]


def build_summary_text(metrics: dict, observations: list[str], recommendations: list[str]) -> str:
    lines = [
        "WEEKLY COACHING SUMMARY",
        "=======================",
        "",
        f"Days included: {metrics.get('days_in_window', 'n/a')}",
        f"Latest weight: {format_num(metrics.get('weight_latest'), 2, ' kg')}",
        f"Weight change: {format_num(metrics.get('weight_change'), 2, ' kg')}",
        f"Average calories: {format_num(metrics.get('calories_avg'), 0, ' kcal')}",
        f"Average protein: {format_num(metrics.get('protein_avg'), 0, ' g')}",
        f"Average steps: {format_num(metrics.get('steps_avg'), 0)}",
        f"Average sleep: {format_num(metrics.get('sleep_avg_hours'), 1, ' h')}",
        f"Training sessions: {metrics.get('training_sessions', 'n/a')}",
        "",
        "Key observations:",
    ]

    lines.extend([f"- {item}" for item in observations] or ["- No observations available."])
    lines.append("")
    lines.append("Coaching recommendations:")
    lines.extend([f"- {item}" for item in recommendations] or ["- No recommendations available."])
    lines.append("")

    return "\n".join(lines)


def build_summary_html(metrics: dict, observations: list[str], recommendations: list[str]) -> str:
    obs_html = "".join(f"<li>{pd.io.common.escape(str(item))}</li>" for item in observations)
    rec_html = "".join(f"<li>{pd.io.common.escape(str(item))}</li>" for item in recommendations)

    return f"""<!DOCTYPE html>
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.5; color: #222;">
    <h2>Weekly Coaching Summary</h2>

    <table style="border-collapse: collapse; margin-bottom: 18px;">
      <tr><td style="padding: 6px 12px; border: 1px solid #ddd;"><strong>Days included</strong></td><td style="padding: 6px 12px; border: 1px solid #ddd;">{metrics.get('days_in_window', 'n/a')}</td></tr>
      <tr><td style="padding: 6px 12px; border: 1px solid #ddd;"><strong>Latest weight</strong></td><td style="padding: 6px 12px; border: 1px solid #ddd;">{format_num(metrics.get('weight_latest'), 2, ' kg')}</td></tr>
      <tr><td style="padding: 6px 12px; border: 1px solid #ddd;"><strong>Weight change</strong></td><td style="padding: 6px 12px; border: 1px solid #ddd;">{format_num(metrics.get('weight_change'), 2, ' kg')}</td></tr>
      <tr><td style="padding: 6px 12px; border: 1px solid #ddd;"><strong>Average calories</strong></td><td style="padding: 6px 12px; border: 1px solid #ddd;">{format_num(metrics.get('calories_avg'), 0, ' kcal')}</td></tr>
      <tr><td style="padding: 6px 12px; border: 1px solid #ddd;"><strong>Average protein</strong></td><td style="padding: 6px 12px; border: 1px solid #ddd;">{format_num(metrics.get('protein_avg'), 0, ' g')}</td></tr>
      <tr><td style="padding: 6px 12px; border: 1px solid #ddd;"><strong>Average steps</strong></td><td style="padding: 6px 12px; border: 1px solid #ddd;">{format_num(metrics.get('steps_avg'), 0)}</td></tr>
      <tr><td style="padding: 6px 12px; border: 1px solid #ddd;"><strong>Average sleep</strong></td><td style="padding: 6px 12px; border: 1px solid #ddd;">{format_num(metrics.get('sleep_avg_hours'), 1, ' h')}</td></tr>
      <tr><td style="padding: 6px 12px; border: 1px solid #ddd;"><strong>Training sessions</strong></td><td style="padding: 6px 12px; border: 1px solid #ddd;">{metrics.get('training_sessions', 'n/a')}</td></tr>
    </table>

    <h3>Key observations</h3>
    <ul>{obs_html or '<li>No observations available.</li>'}</ul>

    <h3>Coaching recommendations</h3>
    <ul>{rec_html or '<li>No recommendations available.</li>'}</ul>
  </body>
</html>
"""


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    dataframes = load_csvs(REPORTS_DIR)
    if not dataframes:
        text = (
            "WEEKLY COACHING SUMMARY\n"
            "=======================\n\n"
            "No CSV report files were found in the reports directory.\n"
        )
        html = """<!DOCTYPE html><html><body><h2>Weekly Coaching Summary</h2><p>No CSV report files were found in the reports directory.</p></body></html>"""
        OUTPUT_TXT.write_text(text, encoding="utf-8")
        OUTPUT_HTML.write_text(html, encoding="utf-8")
        print("No CSV files found. Wrote fallback summary files.")
        return

    dated_df, date_col = best_dated_dataframe(dataframes)

    if dated_df is not None and date_col is not None:
        working_df = restrict_to_latest_week(dated_df, date_col).sort_values(date_col).reset_index(drop=True)
    else:
        working_df = dataframes[0].copy()

    metrics = extract_metrics(working_df)
    observations = build_observations(metrics)
    recommendations = build_recommendations(metrics)

    text_summary = build_summary_text(metrics, observations, recommendations)
    html_summary = build_summary_html(metrics, observations, recommendations)

    OUTPUT_TXT.write_text(text_summary, encoding="utf-8")
    OUTPUT_HTML.write_text(html_summary, encoding="utf-8")

    print(f"Wrote {OUTPUT_TXT}")
    print(f"Wrote {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
