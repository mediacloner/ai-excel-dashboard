"""Conversational ingestion agent.

Orchestrates file analysis → LLM questioning → schema mapping → import,
streaming SSE events throughout. Uses Hermes-style tool calling.
"""

import json
import logging
import re
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import uuid4

from json_repair import repair_json

from app.chat.streaming import (
    format_sse,
    sse_ask_user,
    sse_done,
    sse_error,
    sse_ingestion_complete,
    sse_ingestion_progress,
    sse_ingestion_schema_review,
    sse_ingestion_start,
    sse_text,
    sse_tool_call_result,
    sse_tool_call_start,
)
from app.config import get_config
from app.database.chat_history import save_message
from app.ingestion.prompts import INGESTION_SYSTEM_PROMPT, SEMANTIC_ANALYSIS_PROMPT
from app.ingestion.tools import INGESTION_TOOLS
from app.llm.client import _build_chat_model

logger = logging.getLogger(__name__)


async def run_ingestion_stream(
    file_path: str,
    space_id: str,
    dataset_name: str,
) -> AsyncGenerator[str, None]:
    """Run the full conversational ingestion flow, yielding SSE events.

    This is a single-pass agent: it analyzes the file, asks questions,
    and completes in one conversation turn. For the interrupt-and-ask
    pattern, the frontend will collect the user's answer and call
    /spaces/{space_id}/ingest/answer to continue.
    """
    file_name = Path(file_path).name
    config = get_config()

    yield sse_ingestion_start(file_name, Path(file_path).stat().st_size / (1024 * 1024), 0)
    yield sse_ingestion_progress("analyzing", "Analyzing file structure...")

    # Step 1: Run structural analysis (no LLM)
    from app.ingestion.analysis import analyze_file
    try:
        analysis = analyze_file(file_path)
    except Exception as e:
        logger.error(f"File analysis failed: {e}")
        yield sse_error(f"Failed to analyze file: {e}", recoverable=False)
        yield sse_done()
        return

    yield sse_ingestion_start(file_name, analysis.file_size_mb, len(analysis.sheets))

    # Step 2: If no ambiguities, fast-track to schema mapping
    if not analysis.has_ambiguities:
        yield sse_text(f"Your file looks clean — {analysis.total_rows} rows, {analysis.total_columns} columns. Proceeding with schema mapping.\n\n")
        yield sse_ingestion_progress("mapping", "Running AI schema mapping...")

        async for event in _run_schema_and_import(
            file_path=file_path,
            space_id=space_id,
            dataset_name=dataset_name,
            sheet_name=analysis.sheets[0].name if analysis.sheets else None,
            header_row=analysis.likely_header_row,
            user_context="",
        ):
            yield event
        return

    # Step 3: Has ambiguities — use LLM to generate questions
    yield sse_ingestion_progress("questioning", "Found some things to clarify about your data...")

    async for event in _run_llm_questioning(
        file_path=file_path,
        space_id=space_id,
        dataset_name=dataset_name,
        analysis=analysis,
    ):
        yield event


async def _run_llm_questioning(
    file_path: str,
    space_id: str,
    dataset_name: str,
    analysis,
) -> AsyncGenerator[str, None]:
    """Use the LLM to analyze the file and generate questions for the user.

    The LLM examines the structural analysis and decides what to ask.
    For the initial version, we generate all questions upfront.
    """
    config = get_config()
    model_config = config.models.ingestion_agent or config.models.schema_mapping

    # Build the conversation
    analysis_dict = analysis.to_dict()
    user_prompt = SEMANTIC_ANALYSIS_PROMPT.format(
        file_analysis=json.dumps(analysis_dict, indent=2, default=str),
    )

    messages = [
        {"role": "system", "content": INGESTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    # Stream tokens in real-time with state machine for <think> and <tool_call> tags
    llm = _build_chat_model(model_config)

    try:
        full_response = ""
        text_buffer = ""
        tag_buffer = ""  # Accumulates potential tag characters
        state = "text"  # "text" | "think" | "tool_call" | "maybe_tag"
        tool_buffer = ""
        thinking_notified = False

        async for chunk in llm.astream(messages):
            content = chunk.content if hasattr(chunk, "content") else str(chunk)
            if not content:
                continue

            full_response += content

            for char in content:
                if state == "think":
                    tag_buffer += char
                    if tag_buffer.endswith("</think>"):
                        # Thinking done — notify frontend once
                        state = "text"
                        tag_buffer = ""
                    continue

                if state == "tool_call":
                    tool_buffer += char
                    if "</tool_call>" in tool_buffer:
                        state = "text"
                        async for event in _handle_tool_buffer(
                            tool_buffer, file_path, space_id
                        ):
                            yield event
                        tool_buffer = ""
                    continue

                # State: text — accumulate and flush
                text_buffer += char

                # Detect tag openings
                if text_buffer.endswith("<think>"):
                    # Strip the tag from buffer, enter think state
                    text_before = text_buffer[: -len("<think>")].strip()
                    if text_before:
                        yield sse_text(text_before)
                    text_buffer = ""
                    state = "think"
                    tag_buffer = ""
                    if not thinking_notified:
                        yield sse_ingestion_progress("thinking", "AI is analyzing your data...")
                        thinking_notified = True
                    continue

                if text_buffer.endswith("<tool_call>"):
                    text_before = text_buffer[: -len("<tool_call>")].strip()
                    if text_before:
                        yield sse_text(text_before)
                    text_buffer = ""
                    state = "tool_call"
                    tool_buffer = "<tool_call>"
                    continue

                # Check if text_buffer is a complete raw JSON tool call
                if text_buffer.rstrip().endswith(("}", "}}")) and '"name"' in text_buffer:
                    raw_call = _try_parse_raw_tool_call(text_buffer)
                    if raw_call:
                        async for event in _handle_tool_buffer(
                            f"<tool_call>{json.dumps(raw_call)}</tool_call>",
                            file_path, space_id,
                        ):
                            yield event
                        text_buffer = ""
                        continue

                # If buffer looks like start of a JSON tool call, hold it (don't flush)
                looks_like_json = text_buffer.lstrip().startswith(("{", "{{")) and '"name"' in text_buffer
                if looks_like_json:
                    continue  # Keep accumulating until we get the closing brace

                # Flush text every ~60 chars at natural break points
                if len(text_buffer) > 60 and char in ".!?\n,;:":
                    yield sse_text(text_buffer)
                    text_buffer = ""
                # Also flush at word boundaries for long runs without punctuation
                elif len(text_buffer) > 120 and char == " ":
                    yield sse_text(text_buffer)
                    text_buffer = ""

        # Flush remaining text — check for raw JSON tool calls first
        remaining = text_buffer.strip()
        if remaining:
            raw_call = _try_parse_raw_tool_call(remaining)
            if raw_call:
                # It's a tool call without <tool_call> tags — execute it
                async for event in _handle_tool_buffer(
                    f"<tool_call>{json.dumps(raw_call)}</tool_call>",
                    file_path, space_id,
                ):
                    yield event
            else:
                yield sse_text(remaining)

        # Save full assistant message (cleaned)
        clean_text = re.sub(r"<think>.*?</think>", "", full_response, flags=re.DOTALL)
        clean_text = re.sub(r"<tool_call>.*?</tool_call>", "", clean_text, flags=re.DOTALL)
        # Also remove raw JSON tool calls
        clean_text = re.sub(r'\{+"name"\s*:\s*"(ask_user|analyze_file|read_sheet|run_schema_mapping|import_dataset|present_schema_review)".*', "", clean_text, flags=re.DOTALL).strip()
        if clean_text:
            save_message(space_id=space_id, role="assistant", content=clean_text)

        yield sse_done()

    except Exception as e:
        logger.error(f"LLM questioning failed: {e}")
        yield sse_error(f"AI analysis failed: {e}")
        yield sse_done()


TOOL_NAMES = {"ask_user", "analyze_file", "read_sheet", "run_schema_mapping", "import_dataset", "present_schema_review"}


def _try_parse_raw_tool_call(text: str) -> dict | None:
    """Try to parse raw JSON that looks like a tool call (without <tool_call> tags)."""
    text = text.strip()
    if not text:
        return None
    # Try direct parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and obj.get("name") in TOOL_NAMES:
            return obj
    except (json.JSONDecodeError, TypeError):
        pass
    # Try fixing double braces
    try:
        obj = json.loads(text.replace("{{", "{").replace("}}", "}"))
        if isinstance(obj, dict) and obj.get("name") in TOOL_NAMES:
            return obj
    except (json.JSONDecodeError, TypeError):
        pass
    # Try json_repair
    try:
        repaired = repair_json(text, return_objects=True)
        if isinstance(repaired, dict) and repaired.get("name") in TOOL_NAMES:
            return repaired
    except Exception:
        pass
    return None


def _fix_double_braces(s: str) -> str:
    """Fix LLM output that uses {{ }} instead of { } in JSON.

    The LLM sometimes mimics the prompt's Python format-string escaping.
    """
    # Only fix if double braces are present and single braces are not valid JSON
    try:
        json.loads(s)
        return s  # Already valid
    except json.JSONDecodeError:
        pass
    fixed = s.replace("{{", "{").replace("}}", "}")
    return fixed


async def _handle_tool_buffer(
    tool_buffer: str, file_path: str, space_id: str
) -> AsyncGenerator[str, None]:
    """Parse a complete <tool_call>...</tool_call> block and execute."""
    match = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", tool_buffer, re.DOTALL)
    if not match:
        # Try with greedy match for nested braces
        match = re.search(r"<tool_call>\s*([\s\S]*?)\s*</tool_call>", tool_buffer, re.DOTALL)
    if not match:
        return

    raw_json = match.group(1).strip()

    try:
        call = json.loads(raw_json)
    except json.JSONDecodeError:
        try:
            call = json.loads(raw_json.replace("{{", "{").replace("}}", "}"))
        except json.JSONDecodeError:
            try:
                repaired = repair_json(raw_json, return_objects=True)
                call = repaired if isinstance(repaired, dict) else None
            except Exception:
                call = None
    if not call:
        logger.warning(f"Failed to parse tool call: {raw_json[:300]}")
        return

    tool_name = call.get("name", "")
    tool_args = call.get("arguments", {})

    if tool_name == "ask_user":
        question = tool_args.get("question", "")
        options = tool_args.get("options", [])
        context = tool_args.get("context", "")
        checkpoint_id = str(uuid4())

        yield sse_ask_user(
            question=question,
            options=options,
            context=context,
            checkpoint_id=checkpoint_id,
        )
        save_message(
            space_id=space_id,
            role="assistant",
            content=question,
            tool_calls=[{"name": "ask_user", "args": tool_args}],
        )

    elif tool_name == "analyze_file":
        yield sse_tool_call_start("analyze_file", tool_args)
        start = time.time()
        result = await INGESTION_TOOLS["analyze_file"](tool_args.get("file_path", file_path))
        duration = int((time.time() - start) * 1000)
        yield sse_tool_call_result(
            "analyze_file",
            {"summary": f"Analyzed {result.get('total_rows', 0)} rows, {result.get('total_columns', 0)} columns"},
            duration,
        )

    elif tool_name == "run_schema_mapping":
        yield sse_tool_call_start("run_schema_mapping", tool_args)
        start = time.time()
        result = await INGESTION_TOOLS["run_schema_mapping"](
            file_path=tool_args.get("file_path", file_path),
            sheet_name=tool_args.get("sheet_name"),
            header_row=tool_args.get("header_row", 0),
            columns_to_include=tool_args.get("columns_to_include"),
            user_context=tool_args.get("user_context", ""),
        )
        duration = int((time.time() - start) * 1000)
        yield sse_tool_call_result("run_schema_mapping", {"columns": len(result.get("columns", []))}, duration)

    elif tool_name in INGESTION_TOOLS:
        yield sse_tool_call_start(tool_name, tool_args)
        start = time.time()
        result = await INGESTION_TOOLS[tool_name](**tool_args)
        duration = int((time.time() - start) * 1000)
        yield sse_tool_call_result(tool_name, result, duration)


async def continue_ingestion_stream(
    file_path: str,
    space_id: str,
    dataset_name: str,
    user_answer: str,
    conversation_history: list[dict],
    sheet_name: str | None = None,
    header_row: int = 0,
) -> AsyncGenerator[str, None]:
    """Continue the ingestion after the user answers a question.

    Takes the conversation so far + user answer, feeds it back to the LLM,
    and either asks more questions or proceeds to schema mapping.
    """
    config = get_config()
    model_config = config.models.ingestion_agent or config.models.schema_mapping

    # Save user's answer to chat
    save_message(space_id=space_id, role="user", content=user_answer)

    # Rebuild messages from history + new answer
    messages = [{"role": "system", "content": INGESTION_SYSTEM_PROMPT}]
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_answer})

    llm = _build_chat_model(model_config)

    try:
        full_response = ""
        async for chunk in llm.astream(messages):
            content = chunk.content if hasattr(chunk, "content") else str(chunk)
            if content:
                full_response += content

        parts = _parse_response(full_response)
        user_context_parts = [user_answer]

        for part in parts:
            if part["type"] == "text":
                yield sse_text(part["content"])
                save_message(space_id=space_id, role="assistant", content=part["content"])

            elif part["type"] == "tool_call":
                tool_name = part["name"]
                tool_args = part["arguments"]

                if tool_name == "ask_user":
                    question = tool_args.get("question", "")
                    options = tool_args.get("options", [])
                    context = tool_args.get("context", "")
                    checkpoint_id = str(uuid4())

                    yield sse_ask_user(question=question, options=options, context=context, checkpoint_id=checkpoint_id)
                    save_message(space_id=space_id, role="assistant", content=question, tool_calls=[{"name": "ask_user", "args": tool_args}])

                elif tool_name == "run_schema_mapping":
                    # LLM decided we have enough info — proceed to schema mapping
                    yield sse_ingestion_progress("mapping", "Running AI schema mapping...")
                    user_ctx = tool_args.get("user_context", "\n".join(user_context_parts))

                    async for event in _run_schema_and_import(
                        file_path=tool_args.get("file_path", file_path),
                        space_id=space_id,
                        dataset_name=dataset_name,
                        sheet_name=tool_args.get("sheet_name", sheet_name),
                        header_row=tool_args.get("header_row", header_row),
                        user_context=user_ctx,
                        columns_to_include=tool_args.get("columns_to_include"),
                    ):
                        yield event
                    return

                elif tool_name == "import_dataset":
                    yield sse_tool_call_start("import_dataset", tool_args)
                    start = time.time()
                    result = await INGESTION_TOOLS["import_dataset"](**tool_args)
                    duration = int((time.time() - start) * 1000)
                    yield sse_tool_call_result("import_dataset", result, duration)
                    yield sse_ingestion_complete(result["dataset_id"], result["table_name"], result["row_count"])

                elif tool_name in INGESTION_TOOLS:
                    yield sse_tool_call_start(tool_name, tool_args)
                    start = time.time()
                    result = await INGESTION_TOOLS[tool_name](**tool_args)
                    duration = int((time.time() - start) * 1000)
                    yield sse_tool_call_result(tool_name, result, duration)

        yield sse_done()

    except Exception as e:
        logger.error(f"Ingestion continuation failed: {e}")
        yield sse_error(f"Failed to continue: {e}")
        yield sse_done()


async def run_direct_import(
    file_path: str,
    space_id: str,
    dataset_name: str,
    approved_schema: dict,
    sheet_name: str | None = None,
    header_row: int = 0,
    business_context: str = "",
) -> AsyncGenerator[str, None]:
    """Import with an already-approved schema (from schema review confirmation)."""
    yield sse_ingestion_progress("importing", "Importing data to database...")

    # Build business context from chat history if not provided
    if not business_context:
        from app.database.chat_history import get_recent_messages
        msgs = get_recent_messages(space_id, limit=50)
        qa_parts = []
        for msg in msgs:
            if msg.role == "user":
                qa_parts.append(f"User: {msg.content}")
            elif msg.role == "assistant" and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.get("name") == "ask_user":
                        qa_parts.append(f"Q: {tc.get('args', {}).get('question', '')}")
        business_context = "\n".join(qa_parts)

    try:
        start = time.time()
        result = await INGESTION_TOOLS["import_dataset"](
            file_path=file_path,
            sheet_name=sheet_name,
            header_row=header_row,
            approved_schema=approved_schema,
            dataset_name=dataset_name,
            space_id=space_id,
            business_context=business_context,
        )
        duration = int((time.time() - start) * 1000)

        yield sse_tool_call_result("import_dataset", result, duration)
        yield sse_ingestion_complete(result["dataset_id"], result["table_name"], result["row_count"])

        save_message(
            space_id=space_id,
            role="assistant",
            content=f"Successfully imported **{dataset_name}** — {result['row_count']} rows into `{result['table_name']}`.",
        )

    except Exception as e:
        logger.error(f"Direct import failed: {e}")
        yield sse_error(f"Import failed: {e}", recoverable=False)

    yield sse_done()


async def _run_schema_and_import(
    file_path: str,
    space_id: str,
    dataset_name: str,
    sheet_name: str | None,
    header_row: int,
    user_context: str,
    columns_to_include: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """Run schema mapping and present for review."""
    try:
        yield sse_tool_call_start("run_schema_mapping", {"file": Path(file_path).name})
        start = time.time()

        from app.ingestion.tools import tool_run_schema_mapping
        schema = await tool_run_schema_mapping(
            file_path=file_path,
            sheet_name=sheet_name,
            header_row=header_row,
            columns_to_include=columns_to_include,
            user_context=user_context,
        )

        duration = int((time.time() - start) * 1000)
        yield sse_tool_call_result("run_schema_mapping", {"columns": len(schema["columns"])}, duration)

        # Present schema for review
        file_id = Path(file_path).stem
        yield sse_ingestion_schema_review(
            file_id, schema,
            file_path=file_path,
            sheet_name=sheet_name,
            header_row=header_row,
        )

        # Store the schema context for when the user approves
        save_message(
            space_id=space_id,
            role="assistant",
            content="Here's the proposed schema for your data. Review and confirm to import.",
            tool_calls=[{
                "name": "present_schema_review",
                "args": {
                    "schema": schema,
                    "file_path": file_path,
                    "sheet_name": sheet_name,
                    "header_row": header_row,
                    "dataset_name": dataset_name,
                },
            }],
        )

        yield sse_text("I've mapped your columns and generated descriptions. Please review the schema above and confirm to import.\n")

    except Exception as e:
        logger.error(f"Schema mapping failed: {e}")
        yield sse_error(f"Schema mapping failed: {e}")


def _parse_response(text: str) -> list[dict]:
    """Parse LLM response into text chunks and tool calls.

    Handles Hermes-style <tool_call> tags and also Qwen3's /no_think mode.
    """
    parts = []

    # Strip thinking tags if present
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Split on tool_call tags
    pattern = r"<tool_call>\s*(\{.*?\})\s*</tool_call>"
    segments = re.split(pattern, text, flags=re.DOTALL)

    for i, segment in enumerate(segments):
        segment = segment.strip()
        if not segment:
            continue

        # Even indices are text, odd indices are tool call JSON
        if i % 2 == 0:
            # This is text
            if segment:
                parts.append({"type": "text", "content": segment})
        else:
            # This is a tool call JSON
            try:
                call = json.loads(segment)
                parts.append({
                    "type": "tool_call",
                    "name": call.get("name", ""),
                    "arguments": call.get("arguments", {}),
                })
            except json.JSONDecodeError:
                # If we can't parse it, treat as text
                parts.append({"type": "text", "content": segment})

    return parts
