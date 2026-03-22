from __future__ import annotations

from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_DETAIL_CSV = REPORTS_DIR / "strength_progress_detail.csv"
OUT_WEEKLY_CSV = REPORTS_DIR / "strength_progress_weekly.csv"
OUT_TXT = REPORTS_DIR / "strength_progress_analysis.txt"


TARGET_LIFTS = {
    "deadlift": [
        "deadlift",
        "barbell deadlift",
        "deadlift (barbell)",
    ],
    "squat": [
        "squat",
        "barbell squat",
        "squat (barbell)",
        "barbell deep squat",
        "deep squat",
    ],
    "bench_press": [
        "bench press",
        "bench press (barbell)",
        "barbell bench press",
        "bench press (dumbbell)",
        "dumbbell bench press",
    ],
    "row": [
        "row",
        "seated cable row",
        "seated cable row - bar grip",
        "cable seated row",
        "bent over row",
        "barbell row",
    ],
    "pull_up": [
        "pull up",
        "pull-up",
        "lat pulldown",
        "lat pulldown (cable)",
        "cable lat pulldown (wide grip)",
    ],
    "overhead_press": [
        "overhead press",
        "shoulder press",
        "seated overhead press (dumbbell)",
        "dumbbell seated shoulder press",
        "upright row (barbell)",  # included only if that's part of your chosen proxy
    ],
}


def normalize_text(x: str) -> str:
    return " ".join(str(x).strip().lower().replace("-", " ").split())


def match_lift(exercise_title: str) -> str | None:
    title = normalize_text(exercise_title)
    for lift, patterns in TARGET_LIFTS.items():
        for pattern in patterns:
            if normalize_text(pattern) in title:
                return lift
    return None


def estimate_1rm(weight_kg: float | None, reps: float | None) -> float | None:
    if weight_kg is None or reps is None:
        return None
    if pd.isna(weight_kg) or pd.isna(reps):
        return None
    if reps <= 0 or weight_kg <= 0:
        return None
    return float(weight_kg) * (1.0 + float(reps) / 30.0)


def classify_set(row: pd.Series) -> bool:
    weight = row.get("weight_kg")
    reps = row.get("reps")
    if pd.isna(weight) or pd.isna(reps):
        return False
    if weight <= 0 or reps <= 0:
        return False
    return True


def main() -> None:
    con = duckdb.connect(str(DB_PATH))

    tables = con.execute("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN ('raw', 'clean', 'analytics')
        ORDER BY table_schema, table_name
    """).fetchdf()

    raw_tables = set(
        f"{r.table_schema}.{r.table_name}"
        for _, r in tables.iterrows()
    )

    if "raw.hevy_sets" not in raw_tables or "raw.hevy_workouts" not in raw_tables:
        raise RuntimeError(
            "This script requires raw.hevy_sets and raw.hevy_workouts."
        )

    set_cols = con.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'raw' AND table_name = 'hevy_sets'
        ORDER BY ordinal_position
    """).fetchdf()["column_name"].tolist()

    workout_cols = con.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'raw' AND table_name = 'hevy_workouts'
        ORDER BY ordinal_position
    """).fetchdf()["column_name"].tolist()

    # Try to adapt to your actual schema
    exercise_title_col = None
    for c in ["exercise_title", "title", "exercise_name"]:
        if c in set_cols:
            exercise_title_col = c
            break

    workout_date_col = None
    for c in ["start_time", "workout_date", "date", "created_at"]:
        if c in workout_cols:
            workout_date_col = c
            break

    join_key = None
    for c in ["workout_id"]:
        if c in set_cols and c in workout_cols:
            join_key = c
            break

    if exercise_title_col is None:
        raise RuntimeError(
            f"Could not find exercise title column in raw.hevy_sets. Found: {set_cols}"
        )

    if workout_date_col is None:
        raise RuntimeError(
            f"Could not find workout date column in raw.hevy_workouts. Found: {workout_cols}"
        )

    if join_key is None:
        raise RuntimeError(
            f"Could not find workout join key between raw.hevy_sets and raw.hevy_workouts."
        )

    query = f"""
        SELECT
            s.{join_key} AS workout_id,
            CAST(w.{workout_date_col} AS DATE) AS date,
            s.{exercise_title_col} AS exercise_title,
            s.weight_kg,
            s.reps,
            s.set_index,
            s.set_type
        FROM raw.hevy_sets s
        LEFT JOIN raw.hevy_workouts w
            ON s.{join_key} = w.{join_key}
        WHERE w.{workout_date_col} IS NOT NULL
        ORDER BY CAST(w.{workout_date_col} AS DATE), s.{exercise_title_col}, s.set_index
    """

    df = con.execute(query).fetchdf()
    con.close()

    if df.empty:
        raise RuntimeError("No Hevy set data found after joining sets to workouts.")

    df["exercise_title_norm"] = df["exercise_title"].astype(str).map(normalize_text)
    df["target_lift"] = df["exercise_title"].astype(str).map(match_lift)
    df = df[df["target_lift"].notna()].copy()

    if df.empty:
        raise RuntimeError("No target lift matches found in raw.hevy_sets.")

    df["is_strength_set"] = df.apply(classify_set, axis=1)
    df = df[df["is_strength_set"]].copy()

    if df.empty:
        raise RuntimeError("Matched lifts found, but no usable weighted-rep strength sets were available.")

    df["estimated_1rm"] = df.apply(
        lambda r: estimate_1rm(r["weight_kg"], r["reps"]),
        axis=1
    )

    # Per-workout best set for each lift
    detail = (
        df.sort_values(
            ["date", "target_lift", "estimated_1rm", "weight_kg", "reps"],
            ascending=[True, True, False, False, False]
        )
        .groupby(["date", "workout_id", "target_lift"], as_index=False)
        .first()
    )

    detail = detail[
        [
            "date",
            "workout_id",
            "target_lift",
            "exercise_title",
            "weight_kg",
            "reps",
            "estimated_1rm",
            "set_index",
            "set_type",
        ]
    ].sort_values(["date", "target_lift"])

    detail["week_start"] = pd.to_datetime(detail["date"]) - pd.to_timedelta(
        pd.to_datetime(detail["date"]).dt.weekday, unit="D"
    )
    detail["week_start"] = detail["week_start"].dt.date

    # Weekly best set / weekly best e1RM
    weekly = (
        detail.sort_values(
            ["week_start", "target_lift", "estimated_1rm", "weight_kg", "reps"],
            ascending=[True, True, False, False, False]
        )
        .groupby(["week_start", "target_lift"], as_index=False)
        .first()
    )

    weekly["prev_e1rm"] = weekly.groupby("target_lift")["estimated_1rm"].shift(1)
    weekly["e1rm_change_vs_prev"] = weekly["estimated_1rm"] - weekly["prev_e1rm"]

    def trend_label(x):
        if pd.isna(x):
            return "first_observation"
        if x >= 2.5:
            return "up"
        if x <= -2.5:
            return "down"
        return "flat"

    weekly["trend"] = weekly["e1rm_change_vs_prev"].map(trend_label)

    detail.to_csv(OUT_DETAIL_CSV, index=False)
    weekly.to_csv(OUT_WEEKLY_CSV, index=False)

    lines: list[str] = []
    lines.append("Strength Progress Analysis")
    lines.append("==========================")
    lines.append("")

    lines.append("Latest Weekly Snapshot")
    lines.append("----------------------")

    latest_week = weekly["week_start"].max()
    latest = weekly[weekly["week_start"] == latest_week].copy()

    for _, row in latest.sort_values("target_lift").iterrows():
        lines.append(
            f"{row['target_lift']}: "
            f"best_set={row['weight_kg']} x {int(row['reps'])} | "
            f"e1RM={row['estimated_1rm']:.1f} | "
            f"trend={row['trend']} | "
            f"change_vs_prev={fmt_change(row['e1rm_change_vs_prev'])}"
        )

    lines.append("")
    lines.append("All Lift Summaries")
    lines.append("------------------")

    for lift in sorted(weekly["target_lift"].unique()):
        sub = weekly[weekly["target_lift"] == lift].sort_values("week_start")
        first = sub.iloc[0]
        last = sub.iloc[-1]
        overall_change = last["estimated_1rm"] - first["estimated_1rm"]
        lines.append(
            f"{lift}: "
            f"first={first['estimated_1rm']:.1f} ({first['week_start']}) | "
            f"latest={last['estimated_1rm']:.1f} ({last['week_start']}) | "
            f"overall_change={fmt_change(overall_change)}"
        )

    lines.append("")
    lines.append("Coaching Notes")
    lines.append("-------------")
    lines.append("With 2 strength sessions per week, the goal is not maximum volume. It is high-quality progression.")
    lines.append("Focus on:")
    lines.append("- one strong top set per target movement or close variation")
    lines.append("- enough calories to support training quality")
    lines.append("- high protein consistency")
    lines.append("- low junk fatigue outside the gym")
    lines.append("- steady weekly progression, not dramatic jumps")

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")

    print(f"Saved: {OUT_DETAIL_CSV}")
    print(f"Saved: {OUT_WEEKLY_CSV}")
    print(f"Saved: {OUT_TXT}")
    print()
    print("\n".join(lines))


def fmt_change(x) -> str:
    if pd.isna(x):
        return "N/A"
    sign = "+" if float(x) > 0 else ""
    return f"{sign}{float(x):.1f}"


if __name__ == "__main__":
    main()