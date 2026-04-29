import json
from uuid import uuid4

from app.database.connection import get_connection, get_read_connection
from app.models.schemas import ChatMessage


def save_message(
    space_id: str,
    role: str,
    content: str,
    tool_calls: list[dict] | None = None,
    tool_result: dict | None = None,
) -> ChatMessage:
    message_id = str(uuid4())
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO chat_messages (id, space_id, role, content, tool_calls, tool_result)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                message_id,
                space_id,
                role,
                content,
                json.dumps(tool_calls) if tool_calls else None,
                json.dumps(tool_result) if tool_result else None,
            ],
        )
    finally:
        conn.close()
    return get_message(message_id)


def get_message(message_id: str) -> ChatMessage | None:
    conn = get_read_connection()
    try:
        row = conn.execute(
            "SELECT id, space_id, role, content, tool_calls, tool_result, created_at FROM chat_messages WHERE id = ?",
            [message_id],
        ).fetchone()
        if row is None:
            return None
        return _row_to_message(row)
    finally:
        conn.close()


def get_chat_history(space_id: str, limit: int = 50) -> list[ChatMessage]:
    conn = get_read_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, space_id, role, content, tool_calls, tool_result, created_at
            FROM chat_messages
            WHERE space_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            [space_id, limit],
        ).fetchall()
        return [_row_to_message(r) for r in rows]
    finally:
        conn.close()


def get_recent_messages(space_id: str, limit: int = 20) -> list[ChatMessage]:
    """Get the most recent N messages, returned in chronological order."""
    conn = get_read_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM (
                SELECT id, space_id, role, content, tool_calls, tool_result, created_at
                FROM chat_messages
                WHERE space_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ) sub
            ORDER BY created_at ASC
            """,
            [space_id, limit],
        ).fetchall()
        return [_row_to_message(r) for r in rows]
    finally:
        conn.close()


def clear_chat_history(space_id: str) -> int:
    conn = get_connection()
    try:
        result = conn.execute(
            "DELETE FROM chat_messages WHERE space_id = ? RETURNING id",
            [space_id],
        ).fetchall()
        return len(result)
    finally:
        conn.close()


def _row_to_message(row: tuple) -> ChatMessage:
    tool_calls = row[4]
    if isinstance(tool_calls, str):
        tool_calls = json.loads(tool_calls)
    tool_result = row[5]
    if isinstance(tool_result, str):
        tool_result = json.loads(tool_result)

    return ChatMessage(
        id=row[0],
        space_id=row[1],
        role=row[2],
        content=row[3],
        tool_calls=tool_calls,
        tool_result=tool_result,
        created_at=str(row[6]),
    )
