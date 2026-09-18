import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("CREATE SCHEMA IF NOT EXISTS clean")

# The legacy table name raw.fitbit_daily is retained for compatibility, but
# current scheduled data is now written there by the Google Health importer.
raw_fitbit_cols = {
    row[0]
    for row in con.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'raw'
          AND table_name = 'fitbit_daily'
    """).fetchall()
}
if "source" not in raw_fitbit_cols:
    con.execute("ALTER TABLE raw.fitbit_daily ADD COLUMN source VARCHAR")

con.execute("""
CREATE TABLE IF NOT EXISTS clean.fitbit_daily (
    date DATE,
    steps DOUBLE,
    calories_burned DOUBLE,
    resting_hr DOUBLE,
    hrv DOUBLE,
    sleep_hours DOUBLE,
    active_minutes DOUBLE,
    sleep_efficiency DOUBLE,
    deep_sleep_minutes DOUBLE,
    rem_sleep_minutes DOUBLE,
    wake_minutes DOUBLE,
    sleep_score DOUBLE,
    sleep_restlessness DOUBLE,
    source VARCHAR
)
""")

existing_cols = {
    row[0]
    for row in con.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'clean'
          AND table_name = 'fitbit_daily'
    """).fetchall()
}

wanted_cols = {
    "date": "DATE",
    "steps": "DOUBLE",
    "calories_burned": "DOUBLE",
    "resting_hr": "DOUBLE",
    "hrv": "DOUBLE",
    "sleep_hours": "DOUBLE",
    "active_minutes": "DOUBLE",
    "sleep_efficiency": "DOUBLE",
    "deep_sleep_minutes": "DOUBLE",
    "rem_sleep_minutes": "DOUBLE",
    "wake_minutes": "DOUBLE",
    "sleep_score": "DOUBLE",
    "sleep_restlessness": "DOUBLE",
    "source": "VARCHAR",
}

for col, dtype in wanted_cols.items():
    if col not in existing_cols:
        con.execute(f"ALTER TABLE clean.fitbit_daily ADD COLUMN {col} {dtype}")

con.execute("DELETE FROM clean.fitbit_daily")

con.execute("""
INSERT INTO clean.fitbit_daily (
    date,
    steps,
    calories_burned,
    resting_hr,
    hrv,
    sleep_hours,
    active_minutes,
    sleep_efficiency,
    deep_sleep_minutes,
    rem_sleep_minutes,
    wake_minutes,
    sleep_score,
    sleep_restlessness,
    source
)
WITH sleep_hist AS (
    SELECT
        date,
        AVG(duration_hours) AS duration_hours,
        AVG(efficiency) AS efficiency,
        AVG(deep_minutes) AS deep_minutes,
        AVG(rem_minutes) AS rem_minutes,
        AVG(wake_minutes) AS wake_minutes
    FROM raw.fitbit_sleep_history
    GROUP BY date
),
hrv_hist AS (
    SELECT
        date,
        AVG(rmssd) AS rmssd
    FROM raw.fitbit_hrv_history
    GROUP BY date
),
sleep_score_hist AS (
    SELECT
        date,
        AVG(overall_score) AS overall_score,
        AVG(nightly_resting_hr) AS nightly_resting_hr,
        AVG(restlessness) AS restlessness
    FROM raw.fitbit_sleep_score
    GROUP BY date
),
hist_steps AS (
    SELECT
        date,
        steps
    FROM raw.fitbit_steps_historical
),
all_fitbit_dates AS (
    SELECT date FROM raw.fitbit_daily
    UNION
    SELECT date FROM raw.fitbit_sleep_history
    UNION
    SELECT date FROM raw.fitbit_hrv_history
    UNION
    SELECT date FROM raw.fitbit_sleep_score
    UNION
    SELECT date FROM raw.fitbit_steps_historical
)
SELECT
    d.date,
    COALESCE(f.steps, hs.steps) AS steps,
    f.calories_burned,
    COALESCE(f.resting_hr, ss.nightly_resting_hr) AS resting_hr,
    COALESCE(f.hrv, h.rmssd) AS hrv,
    COALESCE(f.sleep_hours, s.duration_hours) AS sleep_hours,
    f.active_minutes,
    COALESCE(f.sleep_efficiency, s.efficiency) AS sleep_efficiency,
    COALESCE(f.deep_sleep_minutes, s.deep_minutes) AS deep_sleep_minutes,
    COALESCE(f.rem_sleep_minutes, s.rem_minutes) AS rem_sleep_minutes,
    COALESCE(f.wake_minutes, s.wake_minutes) AS wake_minutes,
    COALESCE(f.sleep_score, ss.overall_score) AS sleep_score,
    COALESCE(f.sleep_restlessness, ss.restlessness) AS sleep_restlessness,
    CASE
        WHEN f.date IS NOT NULL THEN COALESCE(NULLIF(f.source, ''), 'fitbit_api_recent')
        WHEN hs.date IS NOT NULL THEN 'fitbit_takeout_steps'
        ELSE 'fitbit_sleep_hrv_only'
    END AS source
FROM all_fitbit_dates d
LEFT JOIN raw.fitbit_daily f
    ON d.date = f.date
LEFT JOIN hist_steps hs
    ON d.date = hs.date
LEFT JOIN sleep_hist s
    ON d.date = s.date
LEFT JOIN hrv_hist h
    ON d.date = h.date
LEFT JOIN sleep_score_hist ss
    ON d.date = ss.date
WHERE d.date IS NOT NULL
ORDER BY d.date
""")

row_count = con.execute("SELECT COUNT(*) FROM clean.fitbit_daily").fetchone()[0]

coverage = con.execute("""
SELECT
    MIN(date) AS earliest_date,
    MAX(date) AS latest_date,
    SUM(CASE WHEN steps IS NOT NULL THEN 1 ELSE 0 END) AS step_days,
    SUM(CASE WHEN resting_hr IS NOT NULL THEN 1 ELSE 0 END) AS resting_hr_days,
    SUM(CASE WHEN hrv IS NOT NULL THEN 1 ELSE 0 END) AS hrv_days,
    SUM(CASE WHEN sleep_hours IS NOT NULL THEN 1 ELSE 0 END) AS sleep_days,
    SUM(CASE WHEN sleep_efficiency IS NOT NULL THEN 1 ELSE 0 END) AS sleep_efficiency_days,
    SUM(CASE WHEN deep_sleep_minutes IS NOT NULL THEN 1 ELSE 0 END) AS deep_sleep_days,
    SUM(CASE WHEN rem_sleep_minutes IS NOT NULL THEN 1 ELSE 0 END) AS rem_sleep_days,
    SUM(CASE WHEN wake_minutes IS NOT NULL THEN 1 ELSE 0 END) AS wake_days,
    SUM(CASE WHEN sleep_score IS NOT NULL THEN 1 ELSE 0 END) AS sleep_score_days,
    SUM(CASE WHEN active_minutes IS NOT NULL THEN 1 ELSE 0 END) AS active_minutes_days
FROM clean.fitbit_daily
""").fetchdf()

preview = con.execute("""
SELECT
    date,
    steps,
    resting_hr,
    hrv,
    sleep_hours,
    active_minutes,
    sleep_efficiency,
    deep_sleep_minutes,
    rem_sleep_minutes,
    wake_minutes,
    sleep_score,
    sleep_restlessness,
    source
FROM clean.fitbit_daily
ORDER BY date DESC
LIMIT 20
""").fetchdf()

con.close()

print(f"Built clean.fitbit_daily with {row_count} rows.")
print("\nCoverage:")
print(coverage.to_string(index=False))
print("\nPreview:")
print(preview.to_string(index=False))
