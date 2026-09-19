from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = REPORTS_DIR / "personal_response_blocks.csv"
OUT_TXT = REPORTS_DIR / "personal_response_analysis.txt"

BLOCK_DAYS = 14
MIN_BODY_DAYS = 6
MIN_NUTRITION_DAYS = 10
MIN_BLOCKS_FOR_ASSOCIATION = 8
MIN_WORKOUTS_FOR_TRAINING_ACTIVE = 2


def _slope_change(frame: pd.DataFrame, column: str) -> float | None:
    local = frame[["date", column]].copy()
    local[column] = pd.to_numeric(local[column], errors="coerce")
    local = local.dropna().sort_values("date")
    if len(local) < MIN_BODY_DAYS:
        return None
    x = (local["date"] - local["date"].min()).dt.days.astype(float)
    y = local[column].astype(float)
    x_centered = x - x.mean()
    denominator = float((x_centered ** 2).sum())
    if denominator <= 0:
        return None
    slope = float((x_centered * (y - y.mean())).sum() / denominator)
    return slope * (BLOCK_DAYS - 1)


def _mean(frame: pd.DataFrame, column: str) -> float | None:
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return None if values.empty else float(values.mean())


def load_daily() -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        frame = con.execute(
            """
            SELECT
                dm.date,
                b.weight_kg,
                b.fat_mass_kg,
                b.lean_mass_kg,
                n.calories,
                n.protein_g,
                f.steps,
                f.sleep_hours,
                f.resting_hr,
                f.hrv,
                COALESCE(t.workout_count, 0) AS workout_count
            FROM analytics.daily_metrics dm
            LEFT JOIN clean.body_composition b ON dm.date = b.date
            LEFT JOIN clean.nutrition_daily n ON dm.date = n.date
            LEFT JOIN clean.fitbit_daily f ON dm.date = f.date
            LEFT JOIN clean.training_summary t ON dm.date = t.date
            ORDER BY dm.date
            """
        ).fetchdf()
    finally:
        con.close()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame.dropna(subset=["date"])


def build_blocks(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    start = frame["date"].min().normalize()
    last_date = frame["date"].max().normalize()

    while start + pd.Timedelta(days=BLOCK_DAYS - 1) <= last_date:
        end = start + pd.Timedelta(days=BLOCK_DAYS - 1)
        block = frame[frame["date"].between(start, end)].copy()
        body_days = int(block["weight_kg"].notna().sum())
        nutrition_days = int(block[["calories", "protein_g"]].notna().all(axis=1).sum())

        if body_days >= MIN_BODY_DAYS and nutrition_days >= MIN_NUTRITION_DAYS:
            rows.append(
                {
                    "start_date": start.date(),
                    "end_date": end.date(),
                    "body_days": body_days,
                    "nutrition_days": nutrition_days,
                    "activity_days": int(block["steps"].notna().sum()),
                    "sleep_days": int(block["sleep_hours"].notna().sum()),
                    "recovery_days": int(block[["resting_hr", "hrv"]].notna().all(axis=1).sum()),
                    "weight_change_kg": _slope_change(block, "weight_kg"),
                    "fat_change_kg": _slope_change(block, "fat_mass_kg"),
                    "lean_change_kg": _slope_change(block, "lean_mass_kg"),
                    "avg_calories": _mean(block, "calories"),
                    "avg_protein_g": _mean(block, "protein_g"),
                    "avg_steps": _mean(block, "steps"),
                    "avg_sleep_h": _mean(block, "sleep_hours"),
                    "avg_rhr": _mean(block, "resting_hr"),
                    "avg_hrv": _mean(block, "hrv"),
                    "workouts": float(
                        pd.to_numeric(block["workout_count"], errors="coerce")
                        .fillna(0)
                        .sum()
                    ),
                }
            )
        start += pd.Timedelta(days=BLOCK_DAYS)

    output = pd.DataFrame(rows)
    if not output.empty:
        output["fat_loss_kg"] = -pd.to_numeric(output["fat_change_kg"], errors="coerce")
        output["lean_retention_kg"] = pd.to_numeric(output["lean_change_kg"], errors="coerce")
    return output


def _spearman(blocks: pd.DataFrame, x: str, y: str) -> tuple[float | None, int]:
    """Spearman correlation without scipy: Pearson correlation of rank values."""
    pair = blocks[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
    n = len(pair)
    if n < MIN_BLOCKS_FOR_ASSOCIATION:
        return None, n
    if pair[x].nunique() < 3 or pair[y].nunique() < 3:
        return None, n
    ranked_x = pair[x].rank(method="average")
    ranked_y = pair[y].rank(method="average")
    value = ranked_x.corr(ranked_y)
    return (None if pd.isna(value) else float(value)), n


def _fmt(value, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}"


def main() -> None:
    blocks = build_blocks(load_daily())
    blocks.to_csv(OUT_CSV, index=False)

    lines = [
        "Personal Response Analysis",
        "==========================",
        "",
        "Purpose",
        "-------",
        "Exploratory N=1 analysis of complete 14-day periods. It looks for associations between protein, calories, steps, sleep, recovery, and resistance-training frequency versus fat-loss and BIA lean-mass outcomes.",
        "These are associations, not causal effects. BIA lean mass is hydration-sensitive and historical logging quality varies.",
        "",
        f"Qualifying 14-day blocks: {len(blocks)}",
    ]

    if blocks.empty:
        lines.extend(["", "Not enough complete historical blocks are available yet."])
    else:
        usable = blocks.dropna(subset=["fat_change_kg", "lean_change_kg"]).copy()
        compatible = usable[
            (usable["fat_change_kg"] < 0)
            & (usable["lean_change_kg"] >= -0.30)
        ].copy()
        training_active = blocks[
            pd.to_numeric(blocks["workouts"], errors="coerce").fillna(0)
            >= MIN_WORKOUTS_FOR_TRAINING_ACTIVE
        ].copy()
        active_usable = training_active.dropna(
            subset=["fat_change_kg", "lean_change_kg"]
        ).copy()
        active_compatible = active_usable[
            (active_usable["fat_change_kg"] < 0)
            & (active_usable["lean_change_kg"] >= -0.30)
        ].copy()

        lines.extend(
            [
                f"Blocks with both fat and lean outcome estimates: {len(usable)}",
                f"Blocks with fat down and BIA lean change >= -0.30 kg: {len(compatible)}",
                f"Training-active blocks (>= {MIN_WORKOUTS_FOR_TRAINING_ACTIVE} resistance workouts / 14d): {len(training_active)}",
                f"Training-active blocks compatible with the current goal: {len(active_compatible)}",
                "",
                "All qualifying historical blocks",
                "--------------------------------",
                f"Calories: {_fmt(blocks['avg_calories'].median(), 0)} kcal/day",
                f"Protein: {_fmt(blocks['avg_protein_g'].median(), 0)} g/day",
                f"Steps: {_fmt(blocks['avg_steps'].median(), 0)} /day",
                f"Sleep: {_fmt(blocks['avg_sleep_h'].median(), 1)} h/night",
                f"Workouts: {_fmt(blocks['workouts'].median(), 0)} per 14 days",
            ]
        )

        if not compatible.empty:
            lines.extend(
                [
                    "",
                    "Periods compatible with the current goal",
                    "----------------------------------------",
                    "These periods had declining BIA fat mass while BIA lean change was no worse than -0.30 kg across the 14-day trend window.",
                    f"Median calories: {_fmt(compatible['avg_calories'].median(), 0)} kcal/day",
                    f"Median protein: {_fmt(compatible['avg_protein_g'].median(), 0)} g/day",
                    f"Median steps: {_fmt(compatible['avg_steps'].median(), 0)} /day",
                    f"Median sleep: {_fmt(compatible['avg_sleep_h'].median(), 1)} h/night",
                    f"Median workouts: {_fmt(compatible['workouts'].median(), 0)} per 14 days",
                ]
            )

        if not training_active.empty:
            lines.extend(
                [
                    "",
                    "Training-active periods",
                    "-----------------------",
                    "This is the more relevant cohort for a muscle-preservation goal because periods with little or no resistance training are excluded.",
                    f"Median calories: {_fmt(training_active['avg_calories'].median(), 0)} kcal/day",
                    f"Median protein: {_fmt(training_active['avg_protein_g'].median(), 0)} g/day",
                    f"Median steps: {_fmt(training_active['avg_steps'].median(), 0)} /day",
                    f"Median sleep: {_fmt(training_active['avg_sleep_h'].median(), 1)} h/night",
                    f"Median workouts: {_fmt(training_active['workouts'].median(), 0)} per 14 days",
                ]
            )
            if not active_compatible.empty:
                lines.extend(
                    [
                        "",
                        "Training-active periods compatible with the goal",
                        "------------------------------------------------",
                        f"Median calories: {_fmt(active_compatible['avg_calories'].median(), 0)} kcal/day",
                        f"Median protein: {_fmt(active_compatible['avg_protein_g'].median(), 0)} g/day",
                        f"Median steps: {_fmt(active_compatible['avg_steps'].median(), 0)} /day",
                        f"Median sleep: {_fmt(active_compatible['avg_sleep_h'].median(), 1)} h/night",
                        f"Median workouts: {_fmt(active_compatible['workouts'].median(), 0)} per 14 days",
                    ]
                )

        predictors = [
            ("avg_protein_g", "Protein"),
            ("avg_calories", "Calories"),
            ("avg_steps", "Steps"),
            ("avg_sleep_h", "Sleep"),
            ("avg_rhr", "Resting HR"),
            ("avg_hrv", "HRV"),
            ("workouts", "Resistance workouts"),
        ]
        lines.extend(
            [
                "",
                "Exploratory associations",
                "------------------------",
                f"Associations below use only training-active periods (>= {MIN_WORKOUTS_FOR_TRAINING_ACTIVE} resistance workouts / 14d). Positive fat-loss correlation means higher values tended to accompany more BIA fat loss; positive lean-retention correlation means higher values tended to accompany better BIA lean retention.",
            ]
        )

        associations = []
        for column, label in predictors:
            fat_r, fat_n = _spearman(training_active, column, "fat_loss_kg")
            lean_r, lean_n = _spearman(training_active, column, "lean_retention_kg")
            associations.append((label, fat_r, fat_n, lean_r, lean_n))
            lines.append(
                f"- {label}: fat-loss r={_fmt(fat_r)} (n={fat_n}); lean-retention r={_fmt(lean_r)} (n={lean_n})"
            )

        lines.extend(["", "Signals worth watching", "---------------------"])
        notable = []
        for label, fat_r, fat_n, lean_r, lean_n in associations:
            if fat_r is not None and abs(fat_r) >= 0.35:
                notable.append(
                    f"{label} has a moderate exploratory association with fat-loss outcome (Spearman r={fat_r:+.2f}, n={fat_n})."
                )
            if lean_r is not None and abs(lean_r) >= 0.35:
                notable.append(
                    f"{label} has a moderate exploratory association with BIA lean-retention outcome (Spearman r={lean_r:+.2f}, n={lean_n})."
                )
        if notable:
            lines.extend(f"- {item}" for item in notable)
        else:
            lines.append(
                "No predictor currently shows a moderate association (|r| >= 0.35) with enough comparable blocks to flag for follow-up."
            )

    lines.extend(
        [
            "",
            "Method Note",
            "-----------",
            f"Blocks are non-overlapping {BLOCK_DAYS}-day calendar periods and require at least {MIN_BODY_DAYS} body-composition days and {MIN_NUTRITION_DAYS} complete nutrition days.",
            "Body outcomes use a within-block linear trend rather than first/last single readings to reduce day-to-day noise.",
            f"Associations are reported only with at least {MIN_BLOCKS_FOR_ASSOCIATION} training-active comparable blocks and use Spearman rank correlation. They should be treated as hypotheses to test, not prescriptions.",
        ]
    )

    text = "\n".join(lines)
    OUT_TXT.write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved: {OUT_CSV}")
    print(f"Saved: {OUT_TXT}")


if __name__ == "__main__":
    main()
