from pathlib import Path

import duckdb

from app.config import get_config


def get_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    config = get_config()
    db_path = Path(config.database.path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path), read_only=read_only)


def get_read_connection() -> duckdb.DuckDBPyConnection:
    return get_connection(read_only=True)


def sync_dataset_aliases() -> int:
    """Create / refresh DuckDB views that alias dataset_name → real table_name.

    Lets the LLM write `SELECT … FROM customers` and have it resolve to the
    actual `dataset_4bb65ae2_…` table behind the scenes. Idempotent — runs
    `CREATE OR REPLACE VIEW`. Skip if the friendly name collides with a real
    table (the underlying dataset table itself, or a system table).

    Returns count of views created/refreshed.
    """
    import re as _re

    conn = get_connection()
    created = 0
    try:
        # Existing real (non-view) tables we must NOT shadow with views.
        real_tables = {
            r[0] for r in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='main' AND table_type='BASE TABLE'"
            ).fetchall()
        }
        rows = conn.execute(
            "SELECT dataset_name, table_name FROM dataset_metadata"
        ).fetchall()
        for dataset_name, table_name in rows:
            if not dataset_name or not table_name:
                continue
            # Sanitize alias to a SQL-safe identifier (lowercase, underscores)
            alias = _re.sub(r"\W+", "_", dataset_name.strip().lower()).strip("_")
            if not alias or alias[0].isdigit():
                continue
            if alias in real_tables:
                continue
            try:
                conn.execute(f'CREATE OR REPLACE VIEW "{alias}" AS SELECT * FROM "{table_name}"')
                created += 1
            except Exception:
                # A name collision or other DDL error — skip silently, the
                # LLM will still see the canonical table_name in the prompt.
                pass
    finally:
        conn.close()
    return created


def init_database() -> None:
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dataset_metadata (
                id VARCHAR PRIMARY KEY,
                dataset_name VARCHAR NOT NULL,
                original_filename VARCHAR NOT NULL,
                column_dictionary JSON,
                business_context TEXT DEFAULT '',
                table_name VARCHAR NOT NULL,
                row_count INTEGER NOT NULL,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: add business_context to existing tables
        try:
            conn.execute("ALTER TABLE dataset_metadata ADD COLUMN business_context TEXT DEFAULT ''")
        except Exception:
            pass  # Column already exists

        conn.execute("""
            CREATE TABLE IF NOT EXISTS spaces (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                description VARCHAR DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS space_datasets (
                space_id VARCHAR NOT NULL,
                dataset_id VARCHAR NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (space_id, dataset_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS dashboards (
                id VARCHAR PRIMARY KEY,
                space_id VARCHAR NOT NULL,
                name VARCHAR NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS widgets (
                id VARCHAR PRIMARY KEY,
                dashboard_id VARCHAR NOT NULL,
                widget_type VARCHAR NOT NULL,
                title VARCHAR NOT NULL,
                config JSON NOT NULL,
                sql_query VARCHAR,
                layout JSON NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id VARCHAR PRIMARY KEY,
                space_id VARCHAR NOT NULL,
                role VARCHAR NOT NULL,
                content TEXT NOT NULL,
                tool_calls JSON,
                tool_result JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS widget_versions (
                id VARCHAR PRIMARY KEY,
                widget_id VARCHAR NOT NULL,
                dashboard_id VARCHAR NOT NULL,
                title VARCHAR NOT NULL,
                widget_type VARCHAR NOT NULL,
                config JSON NOT NULL,
                layout JSON NOT NULL,
                sql_query VARCHAR,
                change_type VARCHAR NOT NULL,
                user_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                id VARCHAR PRIMARY KEY,
                space_id VARCHAR NOT NULL,
                filename VARCHAR NOT NULL,
                mime VARCHAR NOT NULL,
                path VARCHAR NOT NULL,
                url VARCHAR NOT NULL,
                tags JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    finally:
        conn.close()
