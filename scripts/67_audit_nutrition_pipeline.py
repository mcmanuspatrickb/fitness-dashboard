from __future__ import annotations

from pathlib import Path
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = REPORTS_DIR / "nutrition_pipeline_audit.txt"


def main() -> None:
    con = duckdb.connect(str(DB_PATH))

    sections = []

    queries = {
        "clean.nutrition_daily_overall": """
            SELECT
                COUNT(*) AS rows,
                MIN(date) AS min_date,
                MAX(date) AS max_date,
                COUNT(calories) AS calories_days,
                COUNT(protein_g) AS protein_days,
                COUNT(carbs_g) AS carbs_days,
                COUNT(fat_g) AS fat_days,
                COUNT(fiber_g) AS fiber_days,
                COUNT(alcohol_g) AS alcohol_days
            FROM clean.nutrition_daily
        """,
        "clean.nutrition_daily_by_source": """
            SELECT
                source,
                COUNT(*) AS rows,
                MIN(date) AS min_date,
                MAX(date) AS max_date,
                COUNT(calories) AS calories_days,
                COUNT(protein_g) AS protein_days,
                COUNT(carbs_g) AS carbs_days,
                COUNT(fat_g) AS fat_days
            FROM clean.nutrition_daily
            GROUP BY source
            ORDER BY rows DESC
        """,
        "clean.nutrition_daily_recent_30d": """
            SELECT
                COUNT(*) AS rows,
                MIN(date) AS min_date,
                MAX(date) AS max_date,
                COUNT(calories) AS calories_days,
                COUNT(protein_g) AS protein_days,
                COUNT(carbs_g) AS carbs_days,
                COUNT(fat_g) AS fat_days
            FROM clean.nutrition_daily
            WHERE date >= CURRENT_DATE - 30
        """,
        "analytics.daily_metrics_recent_30d": """
            SELECT
                COUNT(*) AS rows,
                MIN(date) AS min_date,
                MAX(date) AS max_date,
                COUNT(calories) AS calories_days,
                COUNT(protein_g) AS protein_days
            FROM analytics.daily_metrics
            WHERE date >= CURRENT_DATE - 30
        """,
        "dates_with_calories_but_missing_protein_recent_60d": """
            SELECT
                n.date,
                n.source,
                n.calories,
                n.protein_g,
                n.carbs_g,
                n.fat_g
            FROM clean.nutrition_daily n
            WHERE n.date >= CURRENT_DATE - 60
              AND n.calories IS NOT NULL
              AND n.protein_g IS NULL
            ORDER BY n.date DESC
        """,
        "recent_14d_nutrition_values": """
            SELECT
                date,
                source,
                calories,
                protein_g,
                carbs_g,
                fat_g,
                fiber_g,
                alcohol_g
            FROM clean.nutrition_daily
            WHERE date >= CURRENT_DATE - 14
            ORDER BY date DESC
        """
    }

    for name, query in queries.items():
        try:
            df = con.execute(query).fetchdf()
            sections.append(name)
            sections.append("-" * len(name))
            sections.append(df.to_string(index=False))
            sections.append("")
        except Exception as e:
            sections.append(name)
            sections.append("-" * len(name))
            sections.append(f"ERROR: {e}")
            sections.append("")

    con.close()

    OUT_PATH.write_text("\n".join(sections), encoding="utf-8")
    print(f"Saved: {OUT_PATH}")
    print()
    print("\n".join(sections))


if __name__ == "__main__":
    main()