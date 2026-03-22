import duckdb

con = duckdb.connect("db/fitness.duckdb")

con.execute("""
UPDATE raw.interventions_daily
SET fasting_state = 'extended_fast'
WHERE lower(fasting_state) = 'ef'
""")

con.execute("""
UPDATE clean.interventions_daily
SET fasting_state = 'extended_fast'
WHERE lower(fasting_state) = 'ef'
""")

con.execute("""
UPDATE raw.interventions_daily
SET fasting_state = 'baseline'
WHERE lower(coalesce(notes, '')) LIKE '%baseline%'
""")

con.execute("""
UPDATE clean.interventions_daily
SET fasting_state = 'baseline'
WHERE lower(coalesce(notes, '')) LIKE '%baseline%'
""")

con.close()
print("Updated intervention labels.")