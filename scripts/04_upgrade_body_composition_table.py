import duckdb

DB_PATH = "db/fitness.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("DROP TABLE IF EXISTS clean.body_composition")

con.execute("""
CREATE TABLE clean.body_composition (
    date DATE,
    weight_kg DOUBLE,
    fat_mass_kg DOUBLE,
    lean_mass_kg DOUBLE,
    body_fat_percent DOUBLE,
    muscle_mass_kg DOUBLE,
    muscle_percent DOUBLE,
    body_water_percent DOUBLE,
    visceral_fat DOUBLE,
    bone_mass_kg DOUBLE
)
""")

con.close()

print("Upgraded clean.body_composition successfully.")