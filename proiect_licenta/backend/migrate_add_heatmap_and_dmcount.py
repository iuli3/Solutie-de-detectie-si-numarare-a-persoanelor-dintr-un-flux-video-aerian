"""
DB migration script for Video fields used by DM-Count + heatmap overlay.
Run with: python migrate_add_heatmap_and_dmcount.py
"""

import psycopg2


DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "database": "licenta_db",
    "user": "admin",
    "password": "parola_sigura",
}


COLUMNS_TO_ADD = [
    ("heatmap_video_path", "VARCHAR(500)"),
    ("max_people_in_frame", "INTEGER DEFAULT 0"),
    ("avg_people_per_frame", "DOUBLE PRECISION DEFAULT 0.0"),
    ("dm_model_used", "VARCHAR(50)"),
]


def column_exists(cursor, table_name, column_name):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table_name, column_name),
    )
    return cursor.fetchone() is not None


def add_column_if_missing(cursor, table_name, column_name, sql_type):
    if column_exists(cursor, table_name, column_name):
        print(f"[SKIP] Column already exists: {table_name}.{column_name}")
        return

    sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}"
    print(f"[MIGRATE] {sql}")
    cursor.execute(sql)
    print(f"[OK] Added column: {table_name}.{column_name}")


def migrate():
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        cursor = conn.cursor()

        print("[START] Applying DB migration for DM-Count + heatmap fields...")
        for column_name, sql_type in COLUMNS_TO_ADD:
            add_column_if_missing(cursor, "video", column_name, sql_type)

        print("[DONE] Migration completed successfully.")
    except Exception as exc:
        print(f"[ERROR] Migration failed: {exc}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    migrate()
