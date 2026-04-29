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
