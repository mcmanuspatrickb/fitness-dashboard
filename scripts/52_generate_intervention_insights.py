from pathlib import Path

import pandas as pd


REPORTS_DIR = Path("reports")

FILTERED_BLOCKS_PATH = REPORTS_DIR / "fasting_blocks_filtered.csv"
EFFICIENCY_PATH = REPORTS_DIR / "fat_loss_efficiency.csv"
TDEE_PATH = REPORTS_DIR / "historical_tdee_estimates.csv"

OUTPUT_CSV_PATH = REPORTS_DIR / "intervention_insights_latest.csv"
OUTPUT_TXT_PATH = REPORTS_DIR / "intervention_insights_latest.txt"


def format_number(value, decimals: int = 2) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{float(value):.{decimals}f}"


def format_integer(value) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{int(round(float(value)))}"


def safe_read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        print(f"Warning: missing file: {path}")
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception as exc:
        print(f"Warning: failed to read {path}: {exc}")
        return pd.DataFrame()


def first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def coerce_numeric_if_present(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def safe_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(df[col], errors="coerce")


def summarize_top_rows(
    df: pd.DataFrame,
    title: str,
    value_col: str,
    n: int = 5,
) -> list[str]:
    if df.empty or value_col not in df.columns:
        return [title, "-" * len(title), "No data available.", ""]

    working = df.copy()
    working[value_col] = pd.to_numeric(working[value_col], errors="coerce")
    working = working.dropna(subset=[value_col])

    if working.empty:
        return [title, "-" * len(title), "No usable data available.", ""]

    lines = [title, "-" * len(title)]

    block_id_col = first_existing_column(working, ["block_id", "block", "id"])
    fasting_type_col = first_existing_column(working, ["fasting_state", "block_type", "fasting_type"])
    start_col = first_existing_column(working, ["start_date", "block_start", "start"])
    end_col = first_existing_column(working, ["end_date", "block_end", "end"])
    duration_col = first_existing_column(working, ["duration_days", "days", "duration"])
    calories_col = first_existing_column(working, ["avg_calories", "calories", "avg_energy"])
    fat_change_col = first_existing_column(working, ["fat_change", "fat_mass_change_kg"])
    lean_change_col = first_existing_column(working, ["lean_change", "lean_mass_change_kg"])

    top = working.sort_values(value_col, ascending=False).head(n).reset_index(drop=True)

    for idx, row in top.iterrows():
        parts = [f"{idx + 1}."]

        if block_id_col:
            parts.append(f"block={row.get(block_id_col)}")
        if fasting_type_col:
            parts.append(f"type={row.get(fasting_type_col)}")
        if start_col and end_col:
            parts.append(f"dates={row.get(start_col)}→{row.get(end_col)}")
        if duration_col:
            parts.append(f"days={format_number(row.get(duration_col), 1)}")
        if calories_col:
            parts.append(f"avg_cal={format_number(row.get(calories_col), 0)}")
        if fat_change_col:
            parts.append(f"fat_change={format_number(row.get(fat_change_col), 2)}")
        if lean_change_col:
            parts.append(f"lean_change={format_number(row.get(lean_change_col), 2)}")

        parts.append(f"{value_col}={format_number(row.get(value_col), 2)}")
        lines.append(" | ".join(parts))

    lines.append("")
    return lines


def build_summary_table(
    filtered_df: pd.DataFrame,
    efficiency_df: pd.DataFrame,
    tdee_df: pd.DataFrame,
) -> pd.DataFrame:
    filtered_df = coerce_numeric_if_present(filtered_df, ["fat_change", "lean_change", "fat_loss_percent"])
    efficiency_df = coerce_numeric_if_present(
        efficiency_df,
        ["fat_loss_per_1000kcal", "fat_loss_kg", "total_deficit"],
    )
    tdee_df = coerce_numeric_if_present(tdee_df, ["estimated_tdee"])

    summary = {
        "filtered_block_count": len(filtered_df),
        "efficiency_row_count": len(efficiency_df),
        "tdee_row_count": len(tdee_df),
        "blocks_with_fat_change": int(filtered_df["fat_change"].notna().sum()) if "fat_change" in filtered_df.columns else pd.NA,
        "blocks_with_lean_change": int(filtered_df["lean_change"].notna().sum()) if "lean_change" in filtered_df.columns else pd.NA,
        "best_fat_loss_per_1000kcal": safe_series(efficiency_df, "fat_loss_per_1000kcal").max(),
        "median_fat_loss_per_1000kcal": safe_series(efficiency_df, "fat_loss_per_1000kcal").median(),
        "mean_fat_loss_per_1000kcal": safe_series(efficiency_df, "fat_loss_per_1000kcal").mean(),
        "median_estimated_tdee": safe_series(tdee_df, "estimated_tdee").median(),
        "mean_estimated_tdee": safe_series(tdee_df, "estimated_tdee").mean(),
        "min_estimated_tdee": safe_series(tdee_df, "estimated_tdee").min(),
        "max_estimated_tdee": safe_series(tdee_df, "estimated_tdee").max(),
    }

    return pd.DataFrame([summary])


def infer_key_takeaways(
    filtered_df: pd.DataFrame,
    efficiency_df: pd.DataFrame,
    tdee_df: pd.DataFrame,
) -> list[str]:
    filtered_df = coerce_numeric_if_present(filtered_df, ["fat_loss_percent"])
    efficiency_df = coerce_numeric_if_present(efficiency_df, ["fat_loss_per_1000kcal"])
    tdee_df = coerce_numeric_if_present(tdee_df, ["estimated_tdee"])

    takeaways: list[str] = []

    fasting_type_col = first_existing_column(
        efficiency_df, ["fasting_state", "block_type", "fasting_type"]
    )

    if (
        fasting_type_col
        and "fat_loss_per_1000kcal" in efficiency_df.columns
        and not efficiency_df.empty
    ):
        grouped_source = efficiency_df.dropna(subset=["fat_loss_per_1000kcal"]).copy()
        if fasting_type_col in grouped_source.columns and not grouped_source.empty:
            grouped = (
                grouped_source.groupby(fasting_type_col, dropna=False)["fat_loss_per_1000kcal"]
                .mean()
                .sort_values(ascending=False)
            )
            if not grouped.empty:
                best_type = grouped.index[0]
                best_value = grouped.iloc[0]
                takeaways.append(
                    f"Best average fat-loss efficiency appears in '{best_type}' blocks "
                    f"at about {format_number(best_value, 2)} kg per 1000 kcal deficit."
                )

    if "fat_loss_percent" in filtered_df.columns and not filtered_df.empty:
        valid = pd.to_numeric(filtered_df["fat_loss_percent"], errors="coerce").dropna()
        if not valid.empty:
            takeaways.append(
                f"Median fat-loss percentage across usable blocks is {format_number(valid.median(), 1)}%."
            )

    if "estimated_tdee" in tdee_df.columns and not tdee_df.empty:
        tdee_valid = pd.to_numeric(tdee_df["estimated_tdee"], errors="coerce").dropna()
        if not tdee_valid.empty:
            takeaways.append(
                f"Estimated TDEE centers around {format_integer(tdee_valid.median())} kcal/day "
                f"(range {format_integer(tdee_valid.min())}–{format_integer(tdee_valid.max())})."
            )

    if not takeaways:
        takeaways.append("Not enough data yet to generate reliable intervention takeaways.")

    return takeaways


def main() -> None:
    filtered_df = safe_read_csv(FILTERED_BLOCKS_PATH)
    efficiency_df = safe_read_csv(EFFICIENCY_PATH)
    tdee_df = safe_read_csv(TDEE_PATH)

    print("\nLoaded files:")
    print(f" - filtered blocks: {len(filtered_df)} rows, columns={list(filtered_df.columns)}")
    print(f" - efficiency:      {len(efficiency_df)} rows, columns={list(efficiency_df.columns)}")
    print(f" - tdee:            {len(tdee_df)} rows, columns={list(tdee_df.columns)}")

    summary_df = build_summary_table(filtered_df, efficiency_df, tdee_df)
    summary_df.to_csv(OUTPUT_CSV_PATH, index=False)
    print(f"\nSaved intervention insights CSV to: {OUTPUT_CSV_PATH}")

    lines: list[str] = [
        "Intervention Insights",
        "=====================",
        "",
        "Coverage",
        "--------",
        f"filtered_block_count: {format_integer(summary_df.loc[0, 'filtered_block_count'])}",
        f"efficiency_row_count: {format_integer(summary_df.loc[0, 'efficiency_row_count'])}",
        f"tdee_row_count: {format_integer(summary_df.loc[0, 'tdee_row_count'])}",
        f"blocks_with_fat_change: {format_integer(summary_df.loc[0, 'blocks_with_fat_change'])}",
        f"blocks_with_lean_change: {format_integer(summary_df.loc[0, 'blocks_with_lean_change'])}",
        "",
        "Efficiency Overview",
        "-------------------",
        f"best_fat_loss_per_1000kcal: {format_number(summary_df.loc[0, 'best_fat_loss_per_1000kcal'])}",
        f"median_fat_loss_per_1000kcal: {format_number(summary_df.loc[0, 'median_fat_loss_per_1000kcal'])}",
        f"mean_fat_loss_per_1000kcal: {format_number(summary_df.loc[0, 'mean_fat_loss_per_1000kcal'])}",
        "",
        "TDEE Overview",
        "-------------",
        f"median_estimated_tdee: {format_integer(summary_df.loc[0, 'median_estimated_tdee'])}",
        f"mean_estimated_tdee: {format_integer(summary_df.loc[0, 'mean_estimated_tdee'])}",
        f"min_estimated_tdee: {format_integer(summary_df.loc[0, 'min_estimated_tdee'])}",
        f"max_estimated_tdee: {format_integer(summary_df.loc[0, 'max_estimated_tdee'])}",
        "",
    ]

    lines.extend(
        summarize_top_rows(
            efficiency_df,
            title="Top Fat-Loss Efficiency Blocks",
            value_col="fat_loss_per_1000kcal",
            n=5,
        )
    )

    if "fat_loss_percent" in filtered_df.columns:
        lines.extend(
            summarize_top_rows(
                filtered_df,
                title="Best Lean-Mass Preservation / Fat-Loss Quality Blocks",
                value_col="fat_loss_percent",
                n=5,
            )
        )

    lines.extend(["Key Takeaways", "-------------"])
    for takeaway in infer_key_takeaways(filtered_df, efficiency_df, tdee_df):
        lines.append(f"- {takeaway}")

    OUTPUT_TXT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved intervention insights TXT to: {OUTPUT_TXT_PATH}")

    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()