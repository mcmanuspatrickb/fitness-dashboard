import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("DROP TABLE IF EXISTS analytics.weekly_metrics")

con.execute("""
CREATE TABLE analytics.weekly_metrics (
    week_start DATE,
    avg_weight DOUBLE,
    avg_fat_mass DOUBLE,
    avg_lean_mass DOUBLE,
    avg_steps DOUBLE,
    avg_sleep DOUBLE,
    avg_resting_hr DOUBLE,
    avg_hrv DOUBLE,
    weight_change DOUBLE,
    fat_mass_change DOUBLE,
    lean_mass_change DOUBLE,
    fasting_state_mode VARCHAR,
    mounjaro_mg_mode DOUBLE,
    avg_hunger_score DOUBLE
)
""")

con.close()

print("Upgraded analytics.weekly_metrics successfully.")