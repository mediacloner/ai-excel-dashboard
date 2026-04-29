import json
from uuid import uuid4

from app.database.connection import get_connection, get_read_connection
from app.models.schemas import DatasetMetadata, Space


def create_space(name: str, description: str = "") -> Space:
    space_id = str(uuid4())
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO spaces (id, name, description) VALUES (?, ?, ?)",
            [space_id, name, description],
        )
    finally:
        conn.close()
    return get_space(space_id)


def get_space(space_id: str) -> Space | None:
    conn = get_read_connection()
    try:
        row = conn.execute(
            "SELECT id, name, description, created_at, updated_at FROM spaces WHERE id = ?",
            [space_id],
        ).fetchone()
        if row is None:
            return None
        return Space(
            id=row[0],
            name=row[1],
            description=row[2],
            created_at=str(row[3]),
            updated_at=str(row[4]),
        )
    finally:
        conn.close()


def list_spaces() -> list[Space]:
    conn = get_read_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, description, created_at, updated_at FROM spaces ORDER BY updated_at DESC"
        ).fetchall()
        return [
            Space(id=r[0], name=r[1], description=r[2], created_at=str(r[3]), updated_at=str(r[4]))
            for r in rows
        ]
    finally:
        conn.close()


def update_space(space_id: str, name: str | None = None, description: str | None = None) -> Space | None:
    space = get_space(space_id)
    if space is None:
        return None

    conn = get_connection()
    try:
        new_name = name if name is not None else space.name
        new_desc = description if description is not None else space.description
        conn.execute(
            "UPDATE spaces SET name = ?, description = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [new_name, new_desc, space_id],
        )
    finally:
        conn.close()
    return get_space(space_id)


def delete_space(space_id: str) -> bool:
    space = get_space(space_id)
    if space is None:
        return False

    conn = get_connection()
    try:
        # Delete widgets belonging to this space's dashboards
        conn.execute(
            "DELETE FROM widgets WHERE dashboard_id IN (SELECT id FROM dashboards WHERE space_id = ?)",
            [space_id],
        )
        conn.execute("DELETE FROM dashboards WHERE space_id = ?", [space_id])
        conn.execute("DELETE FROM chat_messages WHERE space_id = ?", [space_id])
        conn.execute("DELETE FROM space_datasets WHERE space_id = ?", [space_id])
        conn.execute("DELETE FROM spaces WHERE id = ?", [space_id])
        return True
    finally:
        conn.close()


def link_dataset(space_id: str, dataset_id: str) -> bool:
    conn = get_connection()
    try:
        # Check if already linked
        existing = conn.execute(
            "SELECT 1 FROM space_datasets WHERE space_id = ? AND dataset_id = ?",
            [space_id, dataset_id],
        ).fetchone()
        if existing:
            return False
        conn.execute(
            "INSERT INTO space_datasets (space_id, dataset_id) VALUES (?, ?)",
            [space_id, dataset_id],
        )
        return True
    finally:
        conn.close()


def unlink_dataset(space_id: str, dataset_id: str) -> bool:
    conn = get_connection()
    try:
        result = conn.execute(
            "DELETE FROM space_datasets WHERE space_id = ? AND dataset_id = ? RETURNING *",
            [space_id, dataset_id],
        ).fetchone()
        return result is not None
    finally:
        conn.close()


def get_space_datasets(space_id: str) -> list[DatasetMetadata]:
    conn = get_read_connection()
    try:
        rows = conn.execute(
            """
            SELECT dm.id, dm.dataset_name, dm.original_filename, dm.column_dictionary,
                   dm.business_context, dm.table_name, dm.row_count, dm.upload_date
            FROM dataset_metadata dm
            JOIN space_datasets sd ON dm.id = sd.dataset_id
            WHERE sd.space_id = ?
            ORDER BY sd.added_at DESC
            """,
            [space_id],
        ).fetchall()

        datasets = []
        for row in rows:
            col_dict = row[3]
            if isinstance(col_dict, str):
                col_dict = json.loads(col_dict)
            datasets.append(DatasetMetadata(
                id=row[0],
                dataset_name=row[1],
                original_filename=row[2],
                column_dictionary=col_dict,
                business_context=row[4] or "",
                table_name=row[5],
                row_count=row[6],
                upload_date=str(row[7]),
            ))
        return datasets
    finally:
        conn.close()
