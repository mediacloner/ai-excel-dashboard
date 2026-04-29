"""SSE event formatting helpers."""

import json
from typing import Any


def format_sse(event: str, data: dict[str, Any]) -> str:
    """Format a Server-Sent Event string."""
    json_data = json.dumps(data, default=str)
    return f"event: {event}\ndata: {json_data}\n\n"


def sse_text(content: str) -> str:
    return format_sse("text", {"content": content})


def sse_thinking(content: str = "") -> str:
    return format_sse("thinking", {"content": content})


def sse_tool_call_start(tool: str, args: dict) -> str:
    return format_sse("tool_call_start", {"tool": tool, "args": args})


def sse_tool_call_result(tool: str, result: Any, duration_ms: int = 0) -> str:
    return format_sse("tool_call_result", {"tool": tool, "result": result, "duration_ms": duration_ms})


def sse_widget_create(widget: dict) -> str:
    return format_sse("widget_create", {"widget": widget})


def sse_widget_update(widget_id: str, widget: dict) -> str:
    return format_sse("widget_update", {"widget_id": widget_id, "widget": widget})


def sse_ask_user(question: str, options: list[str] | None = None, context: str = "", checkpoint_id: str = "") -> str:
    return format_sse("ask_user", {
        "question": question,
        "options": options or [],
        "context": context,
        "checkpoint_id": checkpoint_id,
    })


def sse_ingestion_start(file_name: str, file_size: float, sheets_found: int) -> str:
    return format_sse("ingestion_start", {
        "file_name": file_name,
        "file_size_mb": file_size,
        "sheets_found": sheets_found,
    })


def sse_ingestion_progress(step: str, message: str) -> str:
    return format_sse("ingestion_progress", {"step": step, "message": message})


def sse_ingestion_schema_review(
    file_id: str,
    schema: dict,
    file_path: str = "",
    sheet_name: str | None = None,
    header_row: int = 0,
) -> str:
    return format_sse("ingestion_schema_review", {
        "file_id": file_id,
        "schema": schema,
        "file_path": file_path,
        "sheet_name": sheet_name,
        "header_row": header_row,
    })


def sse_ingestion_complete(dataset_id: str, table_name: str, row_count: int) -> str:
    return format_sse("ingestion_complete", {
        "dataset_id": dataset_id,
        "table_name": table_name,
        "row_count": row_count,
    })


def sse_error(message: str, recoverable: bool = True) -> str:
    return format_sse("error", {"message": message, "recoverable": recoverable})


def sse_done(message_id: str = "") -> str:
    return format_sse("done", {"message_id": message_id})
