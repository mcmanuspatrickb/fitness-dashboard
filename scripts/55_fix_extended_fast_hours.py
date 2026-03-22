import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

# Build EF blocks with block_id
con.execute("""
CREATE OR REPLACE TEMP TABLE ef_blocks AS
WITH ef_days AS (
    SELECT
        date,
        LAG(date) OVER (ORDER BY date) AS prev_date
    FROM clean.interventions_daily
    WHERE fasting_state = 'extended_fast'
),
flagged AS (
    SELECT
        date,
        CASE
            WHEN prev_date IS NULL THEN 1
            WHEN date - prev_date = 1 THEN 0
            ELSE 1
        END AS new_block
    FROM ef_days
),
blocks AS (
    SELECT
        date,
        SUM(new_block) OVER (ORDER BY date ROWS UNBOUNDED PRECEDING) AS block_id
    FROM flagged
)
SELECT
    date,
    block_id
FROM blocks
""")

# Compute block durations
con.execute("""
CREATE OR REPLACE TEMP TABLE ef_block_sizes AS
SELECT
    block_id,
    COUNT(*) * 24 AS block_hours
FROM ef_blocks
GROUP BY block_id
""")

# Update clean table
con.execute("""
UPDATE clean.interventions_daily t
SET fasting_hours = b.block_hours
FROM ef_blocks e
JOIN ef_block_sizes b USING (block_id)
WHERE t.date = e.date
AND t.fasting_state = 'extended_fast'
""")

# Update raw table too (optional but recommended)
con.execute("""
UPDATE raw.interventions_daily t
SET fasting_hours = b.block_hours
FROM ef_blocks e
JOIN ef_block_sizes b USING (block_id)
WHERE t.date = e.date
AND t.fasting_state = 'extended_fast'
""")

con.close()

print("Updated extended_fast fasting_hours using block durations.")