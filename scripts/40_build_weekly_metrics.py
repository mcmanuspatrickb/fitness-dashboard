import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("DELETE FROM analytics.weekly_metrics")

con.execute("""
INSERT INTO analytics.weekly_metrics (
    week_start,
    avg_weight,
    avg_fat_mass,
    avg_lean_mass,
    avg_steps,
    avg_sleep,
    avg_resting_hr,
    avg_hrv,
    weight_change,
    fat_mass_change,
    lean_mass_change,
    fasting_state_mode,
    mounjaro_mg_mode,
    avg_hunger_score
)
WITH daily AS (
    SELECT
        date,
        DATE_TRUNC('week', date) AS week_start,
        weight_kg,
        fat_mass_kg,
        lean_mass_kg,
        steps,
        sleep_hours,
        resting_hr,
        hrv,
        workout_count,
        training_volume,
        fasting_state,
        mounjaro_mg,
        hunger_score
    FROM analytics.daily_metrics
),
weekly_base AS (
    SELECT
        week_start,
        AVG(weight_kg) AS avg_weight,
        AVG(fat_mass_kg) AS avg_fat_mass,
        AVG(lean_mass_kg) AS avg_lean_mass,
        AVG(steps) AS avg_steps,
        AVG(sleep_hours) AS avg_sleep,
        AVG(resting_hr) AS avg_resting_hr,
        AVG(hrv) AS avg_hrv,
        AVG(hunger_score) AS avg_hunger_score
    FROM daily
    GROUP BY week_start
),
first_last_weight AS (
    SELECT
        week_start,
        FIRST_VALUE(weight_kg) OVER w AS first_weight,
        LAST_VALUE(weight_kg) OVER w AS last_weight,
        ROW_NUMBER() OVER (PARTITION BY week_start ORDER BY date DESC) AS rn
    FROM daily
    WHERE weight_kg IS NOT NULL
    WINDOW w AS (
        PARTITION BY week_start
        ORDER BY date
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    )
),
first_last_fat AS (
    SELECT
        week_start,
        FIRST_VALUE(fat_mass_kg) OVER w AS first_fat,
        LAST_VALUE(fat_mass_kg) OVER w AS last_fat,
        ROW_NUMBER() OVER (PARTITION BY week_start ORDER BY date DESC) AS rn
    FROM daily
    WHERE fat_mass_kg IS NOT NULL
    WINDOW w AS (
        PARTITION BY week_start
        ORDER BY date
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    )
),
first_last_lean AS (
    SELECT
        week_start,
        FIRST_VALUE(lean_mass_kg) OVER w AS first_lean,
        LAST_VALUE(lean_mass_kg) OVER w AS last_lean,
        ROW_NUMBER() OVER (PARTITION BY week_start ORDER BY date DESC) AS rn
    FROM daily
    WHERE lean_mass_kg IS NOT NULL
    WINDOW w AS (
        PARTITION BY week_start
        ORDER BY date
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    )
),
weekly_change AS (
    SELECT
        b.week_start,
        (w.last_weight - w.first_weight) AS weight_change,
        (f.last_fat - f.first_fat) AS fat_mass_change,
        (l.last_lean - l.first_lean) AS lean_mass_change
    FROM weekly_base b
    LEFT JOIN (
        SELECT week_start, first_weight, last_weight
        FROM first_last_weight
        WHERE rn = 1
    ) w ON b.week_start = w.week_start
    LEFT JOIN (
        SELECT week_start, first_fat, last_fat
        FROM first_last_fat
        WHERE rn = 1
    ) f ON b.week_start = f.week_start
    LEFT JOIN (
        SELECT week_start, first_lean, last_lean
        FROM first_last_lean
        WHERE rn = 1
    ) l ON b.week_start = l.week_start
),
fasting_ranked AS (
    SELECT
        week_start,
        fasting_state,
        COUNT(*) AS cnt,
        ROW_NUMBER() OVER (
            PARTITION BY week_start
            ORDER BY COUNT(*) DESC, fasting_state
        ) AS rn
    FROM daily
    WHERE fasting_state IS NOT NULL
    GROUP BY week_start, fasting_state
),
mounjaro_ranked AS (
    SELECT
        week_start,
        mounjaro_mg,
        COUNT(*) AS cnt,
        ROW_NUMBER() OVER (
            PARTITION BY week_start
            ORDER BY COUNT(*) DESC, mounjaro_mg
        ) AS rn
    FROM daily
    WHERE mounjaro_mg IS NOT NULL
    GROUP BY week_start, mounjaro_mg
)
SELECT
    b.week_start,
    b.avg_weight,
    b.avg_fat_mass,
    b.avg_lean_mass,
    b.avg_steps,
    b.avg_sleep,
    b.avg_resting_hr,
    b.avg_hrv,
    c.weight_change,
    c.fat_mass_change,
    c.lean_mass_change,
    f.fasting_state AS fasting_state_mode,
    m.mounjaro_mg AS mounjaro_mg_mode,
    b.avg_hunger_score
FROM weekly_base b
LEFT JOIN weekly_change c
    ON b.week_start = c.week_start
LEFT JOIN (
    SELECT week_start, fasting_state
    FROM fasting_ranked
    WHERE rn = 1
) f
    ON b.week_start = f.week_start
LEFT JOIN (
    SELECT week_start, mounjaro_mg
    FROM mounjaro_ranked
    WHERE rn = 1
) m
    ON b.week_start = m.week_start
ORDER BY b.week_start
""")

row_count = con.execute("SELECT COUNT(*) FROM analytics.weekly_metrics").fetchone()[0]
preview = con.execute("""
SELECT *
FROM analytics.weekly_metrics
ORDER BY week_start DESC
LIMIT 10
""").fetchdf()

con.close()

print(f"Built analytics.weekly_metrics with {row_count} rows.")
print(preview)