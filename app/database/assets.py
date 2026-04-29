"""Asset storage — space-scoped images/SVGs referenced by widget layers."""

import json
from uuid import uuid4

from app.database.connection import get_connection, get_read_connection
from app.models.schemas import Asset


def _row_to_asset(row: tuple) -> Asset:
    tags = row[5]
    if isinstance(tags, str):
        tags = json.loads(tags) if tags else []
    return Asset(
        id=row[0],
        space_id=row[1],
        filename=row[2],
        mime=row[3],
        url=row[4],
        tags=tags or [],
        created_at=str(row[6]),
    )


def create_asset(
    space_id: str,
    filename: str,
    mime: str,
    path: str,
    url: str,
    tags: list[str] | None = None,
) -> Asset:
    asset_id = str(uuid4())
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO assets (id, space_id, filename, mime, path, url, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [asset_id, space_id, filename, mime, path, url, json.dumps(tags or [])],
        )
    finally:
        conn.close()
    return get_asset(asset_id)


def get_asset(asset_id: str) -> Asset | None:
    conn = get_read_connection()
    try:
        row = conn.execute(
            "SELECT id, space_id, filename, mime, url, tags, created_at FROM assets WHERE id = ?",
            [asset_id],
        ).fetchone()
        return _row_to_asset(row) if row else None
    finally:
        conn.close()


def get_asset_path(asset_id: str) -> str | None:
    conn = get_read_connection()
    try:
        row = conn.execute(
            "SELECT path FROM assets WHERE id = ?", [asset_id],
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def list_space_assets(space_id: str) -> list[Asset]:
    conn = get_read_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, space_id, filename, mime, url, tags, created_at
            FROM assets WHERE space_id = ? ORDER BY created_at DESC
            """,
            [space_id],
        ).fetchall()
        return [_row_to_asset(r) for r in rows]
    finally:
        conn.close()


def delete_asset(asset_id: str) -> str | None:
    """Delete an asset record. Returns the filesystem path so the caller can unlink it."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT path FROM assets WHERE id = ?", [asset_id]).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM assets WHERE id = ?", [asset_id])
        return row[0]
    finally:
        conn.close()
