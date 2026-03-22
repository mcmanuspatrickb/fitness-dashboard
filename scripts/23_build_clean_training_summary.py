from __future__ import annotations

import duckdb


DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("CREATE SCHEMA IF NOT EXISTS clean")

con.execute("""
CREATE TABLE IF NOT EXISTS clean.training_summary (
    date DATE,
    workout_count BIGINT,
    total_volume DOUBLE
)
""")

con.execute("DELETE FROM clean.training_summary")

con.execute("""
INSERT INTO clean.training_summary (
    date,
    workout_count,
    total_volume
)
WITH api_workouts AS (
    SELECT
        CAST(w.start_time AS DATE) AS date,
        w.workout_id,
        COALESCE(SUM(s.volume), 0) AS workout_volume
    FROM raw.hevy_workouts w
    LEFT JOIN raw.hevy_sets s
        ON w.workout_id = s.workout_id
    WHERE w.workout_id IS NOT NULL
      AND w.start_time IS NOT NULL
    GROUP BY 1, 2
),
api_min_date AS (
    SELECT MIN(date) AS min_api_date
    FROM api_workouts
),
historical_workouts AS (
    SELECT
        CAST(start_time AS DATE) AS date,
        workout_id,
        COALESCE(SUM(volume), 0) AS workout_volume
    FROM raw.hevy_sets_historical
    WHERE workout_id IS NOT NULL
      AND start_time IS NOT NULL
      AND (
            (SELECT min_api_date FROM api_min_date) IS NULL
            OR CAST(start_time AS DATE) < (SELECT min_api_date FROM api_min_date)
          )
    GROUP BY 1, 2
),
combined_workouts AS (
    SELECT *
    FROM historical_workouts

    UNION ALL

    SELECT *
    FROM api_workouts
)
SELECT
    date,
    COUNT(DISTINCT workout_id) AS workout_count,
    SUM(workout_volume) AS total_volume
FROM combined_workouts
GROUP BY 1
ORDER BY 1
""")

row_count = con.execute("""
    SELECT COUNT(*)
    FROM clean.training_summary
""").fetchone()[0]

preview = con.execute("""
    SELECT *
    FROM clean.training_summary
    ORDER BY date DESC
    LIMIT 20
""").fetchdf()

coverage = con.execute("""
    WITH api_workouts AS (
        SELECT DISTINCT CAST(start_time AS DATE) AS date
        FROM raw.hevy_workouts
        WHERE start_time IS NOT NULL
    ),
    api_min_date AS (
        SELECT MIN(date) AS min_api_date
        FROM api_workouts
    ),
    historical_workouts AS (
        SELECT DISTINCT CAST(start_time AS DATE) AS date
        FROM raw.hevy_sets_historical
        WHERE start_time IS NOT NULL
          AND (
                (SELECT min_api_date FROM api_min_date) IS NULL
                OR CAST(start_time AS DATE) < (SELECT min_api_date FROM api_min_date)
              )
    )
    SELECT
        (SELECT COUNT(*) FROM api_workouts) AS api_workout_days,
        (SELECT COUNT(*) FROM historical_workouts) AS historical_workout_days_used,
        (SELECT min_api_date FROM api_min_date) AS api_cutover_date
""").fetchdf()

con.close()

print(f"Built clean.training_summary with {row_count} rows.")
print()
print("Coverage:")
print(coverage.to_string(index=False))
print()
print("Preview:")
print(preview.to_string(index=False))