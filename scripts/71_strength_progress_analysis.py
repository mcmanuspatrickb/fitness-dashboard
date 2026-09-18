from __future__ import annotations

import re
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

# Match only genuinely comparable movement variants. The old version used broad
# substring matching (for example, lat pulldowns counted as pull-ups and
# dumbbell bench counted as barbell bench), which made week-to-week e1RM trends
# misleading. After a strict title match, the script selects one current Hevy
# exercise_template_id per lift and uses only that identity for the full trend.
TARGET_LIFTS = {
    "deadlift": {
        "include": r"\b(deadlift|conventional\s*deadlift|sumo\s*deadlift)\b",
        "exclude": r"\b(romanian|rdl|stiff|single[ -]?leg)\b",
    },
    "squat": {
        "include": r"\b(back\s*squat|barbell\s*squat|squat\s*\(barbell\)|barbell\s*deep\s*squat|deep\s*squat)\b",
        "exclude": r"\b(front|goblet|hack|split|bulgarian)\b",
    },
    "bench_press": {
        "include": r"\b(bench\s*press|barbell\s*bench|bench\s*\(barbell\))\b",
        "exclude": r"\b(dumbbell|incline|decline|machine|smith)\b",
    },
    "row": {
        "include": r"\b(cable\s*seated\s*row|seated\s*cable\s*row|cable\s*row(?:\s*\(seated\))?|seated\s*row\s*\(cable\))\b",
        "exclude": r"\b(single[ -]?arm|one[ -]?arm|unilateral)\b",
    },
    "pull_up": {
        "include": r"\b(pull[ -]?ups?|chin[ -]?ups?)\b",
        "exclude": None,
    },
    "overhead_press": {
        "include": r"\b(overhead\s*press|military\s*press|shoulder\s*press\s*\(barbell\)|barbell\s*overhead)\b",
        "exclude": r"\b(dumbbell|machine|smith|seated|upright)\b",
    },
}

EXCLUDED_SET_TYPES = {
    "warmup",
    "warm-up",
    "warm_up",
    "dropset",
    "drop-set",
    "drop_set",
    "drop set",
}
MAX_E1RM_REPS = 12


def normalize_text(x: str) -> str:
    return " ".join(str(x).strip().lower().split())


def match_lift(exercise_title: str) -> str | None:
    title = normalize_text(exercise_title)
    for lift, spec in TARGET_LIFTS.items():
        if not re.search(spec["include"], title, flags=re.IGNORECASE):
            continue
        exclude = spec.get("exclude")
        if exclude and re.search(exclude, title, flags=re.IGNORECASE):
            continue
        return lift
    return None


def estimate_1rm(weight_kg: float | None, reps: float | None) -> float | None:
    if weight_kg is None or reps is None:
        return None
    if pd.isna(weight_kg) or pd.isna(reps):
        return None
    if reps <= 0 or weight_kg <= 0 or reps > MAX_E1RM_REPS:
        return None
    return float(weight_kg) * (1.0 + float(reps) / 30.0)


def classify_set(row: pd.Series) -> bool:
    weight = row.get("weight_kg")
    reps = row.get("reps")
    if pd.isna(weight) or pd.isna(reps):
        return False
    if weight <= 0 or reps <= 0 or reps > MAX_E1RM_REPS:
        return False

    set_type = normalize_text(row.get("set_type", "normal"))
    if set_type in EXCLUDED_SET_TYPES:
        return False
    return True


def choose_tracked_identities(df: pd.DataFrame) -> dict[str, dict[str, str]]:
    """Choose one current Hevy identity per target lift.

    Preference is the template ID used most recently. Ties are broken by the
    number of distinct workouts and then the number of qualifying sets. If an
    old row has no template ID, exact normalized title is used as a fallback.
    """
    identities: dict[str, dict[str, str]] = {}

    for lift, sub in df.groupby("target_lift"):
        with_id = sub[
            sub["exercise_template_id"].notna()
            & sub["exercise_template_id"].astype(str).str.strip().ne("")
        ].copy()

        if not with_id.empty:
            stats = (
                with_id.groupby("exercise_template_id", as_index=False)
                .agg(
                    latest_date=("date", "max"),
                    workout_count=("workout_id", "nunique"),
                    set_count=("workout_id", "size"),
                )
                .sort_values(
                    ["latest_date", "workout_count", "set_count"],
                    ascending=[False, False, False],
                )
            )
            template_id = str(stats.iloc[0]["exercise_template_id"])
            chosen = with_id[with_id["exercise_template_id"].astype(str) == template_id]
            latest_row = chosen.sort_values("date").iloc[-1]
            identities[lift] = {
                "kind": "template_id",
                "value": template_id,
                "title": str(latest_row["exercise_title"]),
            }
            continue

        title_stats = (
            sub.groupby("exercise_title_norm", as_index=False)
            .agg(
                latest_date=("date", "max"),
                workout_count=("workout_id", "nunique"),
                set_count=("workout_id", "size"),
            )
            .sort_values(
                ["latest_date", "workout_count", "set_count"],
                ascending=[False, False, False],
            )
        )
        title_norm = str(title_stats.iloc[0]["exercise_title_norm"])
        chosen = sub[sub["exercise_title_norm"] == title_norm]
        latest_row = chosen.sort_values("date").iloc[-1]
        identities[lift] = {
            "kind": "title",
            "value": title_norm,
            "title": str(latest_row["exercise_title"]),
        }

    return identities


def filter_to_tracked_identities(
    df: pd.DataFrame,
    identities: dict[str, dict[str, str]],
) -> pd.DataFrame:
    masks = []
    for lift, identity in identities.items():
        lift_mask = df["target_lift"] == lift
        if identity["kind"] == "template_id":
            identity_mask = df["exercise_template_id"].astype(str) == identity["value"]
        else:
            identity_mask = df["exercise_title_norm"] == identity["value"]
        masks.append(lift_mask & identity_mask)

    if not masks:
        return df.iloc[0:0].copy()

    combined = masks[0]
    for mask in masks[1:]:
        combined = combined | mask
    return df[combined].copy()


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

    join_key = "workout_id" if "workout_id" in set_cols and "workout_id" in workout_cols else None

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
            "Could not find workout join key between raw.hevy_sets and raw.hevy_workouts."
        )

    template_id_expr = (
        "s.exercise_template_id"
        if "exercise_template_id" in set_cols
        else "NULL::VARCHAR"
    )

    query = f"""
        SELECT
            s.{join_key} AS workout_id,
            CAST(w.{workout_date_col} AS DATE) AS date,
            s.{exercise_title_col} AS exercise_title,
            {template_id_expr} AS exercise_template_id,
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
        raise RuntimeError("No strict target-lift matches found in raw.hevy_sets.")

    df["is_strength_set"] = df.apply(classify_set, axis=1)
    df = df[df["is_strength_set"]].copy()

    if df.empty:
        raise RuntimeError(
            "Target lifts were found, but no comparable working sets in the 1-12 rep range were available."
        )

    identities = choose_tracked_identities(df)
    df = filter_to_tracked_identities(df, identities)

    if df.empty:
        raise RuntimeError("No sets remained after selecting tracked Hevy exercise identities.")

    df["estimated_1rm"] = df.apply(
        lambda r: estimate_1rm(r["weight_kg"], r["reps"]),
        axis=1,
    )
    df = df[df["estimated_1rm"].notna()].copy()

    detail = (
        df.sort_values(
            ["date", "target_lift", "estimated_1rm", "weight_kg", "reps"],
            ascending=[True, True, False, False, False],
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
            "exercise_template_id",
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

    weekly = (
        detail.sort_values(
            ["week_start", "target_lift", "estimated_1rm", "weight_kg", "reps"],
            ascending=[True, True, False, False, False],
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
    lines.append("Tracked Exercise Identities")
    lines.append("---------------------------")
    for lift in sorted(identities):
        identity = identities[lift]
        if identity["kind"] == "template_id":
            lines.append(
                f"{lift}: {identity['title']} | Hevy template={identity['value']}"
            )
        else:
            lines.append(
                f"{lift}: {identity['title']} | exact-title fallback"
            )

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
    lines.append("Method Notes")
    lines.append("------------")
    lines.append("- each lift uses one current Hevy exercise identity; unlike variants are not mixed")
    lines.append("- warm-up and drop sets are excluded")
    lines.append(f"- e1RM uses working sets of 1-{MAX_E1RM_REPS} reps")
    lines.append("- weekly trend is a best-set e1RM proxy, not a substitute for an actual max test")

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
