from __future__ import annotations

import os
from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
NEW_PATH = PROJECT_ROOT / "db" / "fitness.sanitized.duckdb"

SENSITIVE_COLUMN_NAMES = {
    "access_token",
    "refresh_token",
    "client_secret",
    "password",
    "cookie",
    "cookies",
    "storage_state",
}


def q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(DB_PATH)

    if NEW_PATH.exists():
        NEW_PATH.unlink()

    con = duckdb.connect(str(NEW_PATH))
    try:
        source_sql_path = str(DB_PATH).replace("'", "''")
        con.execute(f"ATTACH '{source_sql_path}' AS src (READ_ONLY)")

        tables = con.execute(
            """
            SELECT schema_name, table_name, sql
            FROM duckdb_tables()
            WHERE database_name = 'src'
              AND internal = FALSE
            ORDER BY schema_name, table_name
            """
        ).fetchall()

        source_columns = con.execute(
            """
            SELECT schema_name, table_name, column_name
            FROM duckdb_columns()
            WHERE database_name = 'src'
              AND internal = FALSE
            ORDER BY schema_name, table_name, column_index
            """
        ).fetchall()

        columns_by_table: dict[tuple[str, str], list[str]] = {}
        for schema_name, table_name, column_name in source_columns:
            columns_by_table.setdefault((schema_name, table_name), []).append(column_name)

        schemas = sorted({schema for schema, _, _ in tables})
        for schema_name in schemas:
            con.execute(f"CREATE SCHEMA IF NOT EXISTS {q(schema_name)}")

        sanitized_tables: list[str] = []
        copied_tables: list[str] = []

        for schema_name, table_name, create_sql in tables:
            if not create_sql:
                raise RuntimeError(f"Missing CREATE SQL for {schema_name}.{table_name}")

            con.execute(create_sql)

            column_names = {
                name.lower() for name in columns_by_table.get((schema_name, table_name), [])
            }
            contains_sensitive_columns = bool(column_names & SENSITIVE_COLUMN_NAMES)

            if contains_sensitive_columns:
                sanitized_tables.append(f"{schema_name}.{table_name}")
                continue

            con.execute(
                f"INSERT INTO {q(schema_name)}.{q(table_name)} "
                f"SELECT * FROM src.{q(schema_name)}.{q(table_name)}"
            )
            copied_tables.append(f"{schema_name}.{table_name}")

        views = con.execute(
            """
            SELECT schema_name, view_name, sql
            FROM duckdb_views()
            WHERE database_name = 'src'
              AND internal = FALSE
            ORDER BY schema_name, view_name
            """
        ).fetchall()
        recreated_views: list[str] = []
        for schema_name, view_name, view_sql in views:
            if not view_sql:
                continue
            cleaned_sql = view_sql.replace("CREATE VIEW src.", "CREATE VIEW ")
            try:
                con.execute(cleaned_sql)
                recreated_views.append(f"{schema_name}.{view_name}")
            except Exception as exc:
                print(f"Warning: view not recreated: {schema_name}.{view_name}: {exc}")

        indexes = con.execute(
            """
            SELECT schema_name, index_name, sql
            FROM duckdb_indexes()
            WHERE database_name = 'src'
            ORDER BY schema_name, index_name
            """
        ).fetchall()
        recreated_indexes: list[str] = []
        for schema_name, index_name, index_sql in indexes:
            if not index_sql:
                continue
            cleaned_sql = index_sql.replace(" ON src.", " ON ")
            try:
                con.execute(cleaned_sql)
                recreated_indexes.append(f"{schema_name}.{index_name}")
            except Exception as exc:
                print(f"Warning: index not recreated: {schema_name}.{index_name}: {exc}")

        con.execute("CHECKPOINT")
        con.execute("DETACH src")

        remaining_sensitive = con.execute(
            """
            SELECT schema_name, table_name, column_name
            FROM duckdb_columns()
            WHERE database_name = current_database()
              AND internal = FALSE
              AND lower(column_name) IN (
                  'access_token', 'refresh_token', 'client_secret',
                  'password', 'cookie', 'cookies', 'storage_state'
              )
            ORDER BY schema_name, table_name, column_name
            """
        ).fetchall()

        for schema_name, table_name, _ in remaining_sensitive:
            count = con.execute(
                f"SELECT COUNT(*) FROM {q(schema_name)}.{q(table_name)}"
            ).fetchone()[0]
            if count != 0:
                raise RuntimeError(
                    f"Sensitive table still contains rows: {schema_name}.{table_name} ({count})"
                )

        print(f"Copied data tables: {len(copied_tables)}")
        print(f"Sanitized credential-bearing tables: {len(sanitized_tables)}")
        for name in sanitized_tables:
            print(f"  emptied: {name}")
        print(f"Recreated views: {len(recreated_views)}")
        print(f"Recreated indexes: {len(recreated_indexes)}")
    finally:
        con.close()

    old_size = DB_PATH.stat().st_size
    new_size = NEW_PATH.stat().st_size
    os.replace(NEW_PATH, DB_PATH)
    print(f"Replaced seed database with sanitized copy: {DB_PATH}")
    print(f"Size: {old_size} -> {new_size} bytes")


if __name__ == "__main__":
    main()
