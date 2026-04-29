"""Dashboard-building agent.

Orchestrates the LLM conversation for creating dashboard widgets.
Streams SSE events as it queries data and creates visualizations.
"""

import json
import logging
import re
from collections.abc import AsyncGenerator
from uuid import uuid4

from json_repair import repair_json

from app.chat.dashboard_prompts import build_dashboard_system_prompt, build_datasets_context
from app.chat.streaming import sse_done, sse_error, sse_text, sse_thinking
from app.chat.tools import execute_tool, format_tool_result_for_llm, parse_llm_response
from app.config import get_config
from app.database.chat_history import get_recent_messages, save_message
from app.database.dashboards import create_dashboard, get_dashboard, list_dashboards, set_current_user_message
from app.database.metadata import get_table_schema
from app.database.spaces import get_space_datasets
from app.llm.client import _build_chat_model

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 12  # Max tool-call rounds. Multi-widget requests can need
# 2 rounds per widget (query_data + create_*_widget) plus retries. We also
# enforce REPEAT_FAILURE_THRESHOLD below to catch tight retry loops earlier
# than the round budget.

# If the LLM emits the same tool name with errors this many times in a row,
# we abort the loop and surface a clear error to the user. Catches Qwen3's
# "retry the same broken create_composed_widget forever" failure mode.
REPEAT_FAILURE_THRESHOLD = 2


async def run_dashboard_chat_stream(
    space_id: str,
    user_message: str,
    dashboard_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Run a dashboard chat turn, yielding SSE events.

    The agent loop:
    1. Build context (datasets, conversation history)
    2. Call LLM with user message
    3. Parse response for text + tool calls
    4. Execute tool calls, feed results back to LLM
    5. Repeat until the LLM gives a final text response (no more tool calls)
    """
    config = get_config()
    model_config = config.models.dashboard_agent or config.models.text_to_sql

    # Fresh turn — invalidate any stale query cache from prior turns so
    # widget-creation tools can't reuse data the LLM never actually queried.
    from app.chat.tools import _LAST_QUERY
    if dashboard_id:
        _LAST_QUERY.pop(dashboard_id, None)

    # Record the user message on this async task's context so widget mutations
    # triggered anywhere down-stack carry the prompt that caused them.
    set_current_user_message(user_message)

    # Ensure we have a dashboard to put widgets on
    if dashboard_id is None:
        dashboards = list_dashboards(space_id)
        if dashboards:
            dashboard_id = dashboards[0].id
        else:
            dashboard = create_dashboard(space_id, "Dashboard")
            dashboard_id = dashboard.id

    # Save user message
    save_message(space_id=space_id, role="user", content=user_message)

    yield sse_thinking()

    # Build the system prompt with dataset context
    try:
        datasets_context = _build_space_context(space_id)
    except Exception as e:
        logger.error(f"Failed to build space context: {e}")
        yield sse_error(f"Failed to load space data: {e}")
        yield sse_done()
        return

    # Include existing widgets so the LLM can reference them for updates
    widgets_context = _build_widgets_context(dashboard_id)
    system_prompt = build_dashboard_system_prompt(datasets_context) + widgets_context

    # Load recent conversation history
    recent = get_recent_messages(space_id, limit=20)
    messages = [{"role": "system", "content": system_prompt}]
    for msg in recent:
        if msg.role in ("user", "assistant"):
            messages.append({"role": msg.role, "content": msg.content})

    # Ensure the last message is the current user message
    if not messages or messages[-1].get("content") != user_message:
        messages.append({"role": "user", "content": user_message})

    # Agent loop: call LLM, parse, execute tools, repeat
    llm = _build_chat_model(model_config)

    # Anti-loop tracking. (tool_name, last_error) tuple — if it repeats
    # REPEAT_FAILURE_THRESHOLD times, we bail with an explicit error.
    last_failure: tuple[str, str] | None = None
    failure_streak = 0

    for round_num in range(MAX_TOOL_ROUNDS):
        try:
            # Stream tokens in real-time, buffer tool_call blocks
            full_response = ""
            text_buffer = ""
            text_parts = []
            tool_calls_found = []
            in_tool_call = False
            tool_buffer = ""

            async for chunk in llm.astream(messages):
                content = chunk.content if hasattr(chunk, "content") else ""
                if not content:
                    continue

                full_response += content

                for char in content:
                    if in_tool_call:
                        tool_buffer += char
                        if "</tool_call>" in tool_buffer:
                            in_tool_call = False
                            # Parse and execute the tool call
                            match = re.search(
                                r"<tool_call>\s*([\s\S]*?)\s*</tool_call>",
                                tool_buffer, re.DOTALL,
                            )
                            if match:
                                try:
                                    raw = match.group(1).strip()
                                    # Parse with repair for malformed LLM JSON
                                    try:
                                        call = json.loads(raw)
                                    except json.JSONDecodeError:
                                        try:
                                            call = json.loads(raw.replace("{{", "{").replace("}}", "}"))
                                        except json.JSONDecodeError:
                                            repaired = repair_json(raw, return_objects=True)
                                            call = repaired if isinstance(repaired, dict) else None
                                    if not call or "name" not in call:
                                        tool_buffer = ""
                                        continue
                                    tool_name = call.get("name", "")
                                    tool_args = call.get("arguments", {})
                                    tool_calls_found.append({"name": tool_name, "args": tool_args})

                                    events, result = await execute_tool(
                                        tool_name=tool_name,
                                        tool_args=tool_args,
                                        dashboard_id=dashboard_id,
                                        space_id=space_id,
                                    )
                                    for event in events:
                                        yield event

                                    # Anti-loop: if the same tool errors with
                                    # the same error twice in a row, abort.
                                    err = result.get("error") if isinstance(result, dict) else None
                                    if err:
                                        sig = (tool_name, str(err)[:120])
                                        if sig == last_failure:
                                            failure_streak += 1
                                        else:
                                            last_failure, failure_streak = sig, 1
                                        if failure_streak >= REPEAT_FAILURE_THRESHOLD:
                                            yield sse_error(
                                                f"Aborting after {failure_streak} repeated failures of '{tool_name}': {err}",
                                                recoverable=False,
                                            )
                                            yield sse_done()
                                            return
                                    else:
                                        last_failure, failure_streak = None, 0

                                    # Feed result back for next round
                                    tool_result_str = format_tool_result_for_llm(tool_name, result)
                                    messages.append({"role": "assistant", "content": full_response})
                                    messages.append({
                                        "role": "user",
                                        "content": f"<tool_response>\n{tool_result_str}\n</tool_response>",
                                    })
                                except json.JSONDecodeError:
                                    pass
                            tool_buffer = ""
                    else:
                        text_buffer += char
                        if text_buffer.endswith("<tool_call>"):
                            text_before = text_buffer[: -len("<tool_call>")].strip()
                            if text_before:
                                clean = re.sub(r"<think>.*?</think>", "", text_before, flags=re.DOTALL).strip()
                                if clean:
                                    yield sse_text(clean + "\n\n")
                                    text_parts.append(clean)
                            text_buffer = ""
                            in_tool_call = True
                            tool_buffer = "<tool_call>"
                        # Check for raw JSON tool call (no <tool_call> tags)
                        elif text_buffer.rstrip().endswith(("}", "}}")) and '"name"' in text_buffer:
                            raw = text_buffer.strip()
                            try:
                                try:
                                    call = json.loads(raw)
                                except json.JSONDecodeError:
                                    call = json.loads(raw.replace("{{", "{").replace("}}", "}"))
                                if isinstance(call, dict) and "name" in call:
                                    tool_name = call.get("name", "")
                                    tool_args = call.get("arguments", {})
                                    tool_calls_found.append({"name": tool_name, "args": tool_args})
                                    events, result = await execute_tool(
                                        tool_name=tool_name, tool_args=tool_args,
                                        dashboard_id=dashboard_id, space_id=space_id,
                                    )
                                    for event in events:
                                        yield event
                                    err = result.get("error") if isinstance(result, dict) else None
                                    if err:
                                        sig = (tool_name, str(err)[:120])
                                        if sig == last_failure:
                                            failure_streak += 1
                                        else:
                                            last_failure, failure_streak = sig, 1
                                        if failure_streak >= REPEAT_FAILURE_THRESHOLD:
                                            yield sse_error(
                                                f"Aborting after {failure_streak} repeated failures of '{tool_name}': {err}",
                                                recoverable=False,
                                            )
                                            yield sse_done()
                                            return
                                    else:
                                        last_failure, failure_streak = None, 0
                                    tool_result_str = format_tool_result_for_llm(tool_name, result)
                                    messages.append({"role": "assistant", "content": full_response})
                                    messages.append({"role": "user", "content": f"<tool_response>\n{tool_result_str}\n</tool_response>"})
                                    text_buffer = ""
                                    continue
                            except (json.JSONDecodeError, TypeError):
                                pass

                            if len(text_buffer) > 80 and char in ".!?\n":
                                clean = re.sub(r"<think>.*?</think>", "", text_buffer, flags=re.DOTALL)
                                if clean.strip():
                                    yield sse_text(clean)
                                    text_parts.append(clean)
                                text_buffer = ""
                        elif len(text_buffer) > 80 and char in ".!?\n":
                            clean = re.sub(r"<think>.*?</think>", "", text_buffer, flags=re.DOTALL)
                            if clean.strip():
                                yield sse_text(clean)
                                text_parts.append(clean)
                            text_buffer = ""

            # Flush remaining content. There are THREE places content can be
            # stranded when a stream ends:
            #   - text_buffer  — text outside <tool_call> tags
            #   - tool_buffer  — partial tool call that never reached </tool_call>
            #     (was silently discarded before — caused agent to "hang" with
            #     no observable output when Qwen3 truncates mid-call)
            # We try tool_buffer first because it's the more useful content.
            recovered_call = None
            if in_tool_call and tool_buffer:
                # Drop the leading <tool_call> tag, look for a balanced JSON
                # object, then try strict parse → repair_json fallback.
                inner = tool_buffer.replace("<tool_call>", "", 1).strip()
                # If close tag is partially present, drop it
                inner = re.sub(r"</tool_call>?\s*$", "", inner).rstrip()
                m = re.search(r"\{[\s\S]*", inner, re.DOTALL)
                if m:
                    chunk = m.group(0)
                    try:
                        recovered_call = json.loads(chunk)
                    except json.JSONDecodeError:
                        try:
                            r = repair_json(chunk, return_objects=True)
                            if isinstance(r, dict):
                                recovered_call = r
                        except Exception:
                            pass
                if recovered_call and "name" in recovered_call:
                    logger.info(f"recovered truncated tool_call: {recovered_call.get('name')}")
                    tool_name = recovered_call.get("name", "")
                    tool_args = recovered_call.get("arguments", {})
                    tool_calls_found.append({"name": tool_name, "args": tool_args})
                    events, result = await execute_tool(
                        tool_name=tool_name, tool_args=tool_args,
                        dashboard_id=dashboard_id, space_id=space_id,
                    )
                    for event in events:
                        yield event
                    err = result.get("error") if isinstance(result, dict) else None
                    if err:
                        sig = (tool_name, str(err)[:120])
                        if sig == last_failure:
                            failure_streak += 1
                        else:
                            last_failure, failure_streak = sig, 1
                        if failure_streak >= REPEAT_FAILURE_THRESHOLD:
                            yield sse_error(
                                f"Aborting after {failure_streak} repeated failures of '{tool_name}': {err}",
                                recoverable=False,
                            )
                            yield sse_done()
                            return
                    else:
                        last_failure, failure_streak = None, 0
                    tool_result_str = format_tool_result_for_llm(tool_name, result)
                    messages.append({"role": "assistant", "content": full_response})
                    messages.append({"role": "user", "content": f"<tool_response>\n{tool_result_str}\n</tool_response>"})
                else:
                    # Couldn't recover. Surface the failure to the user so they
                    # know the agent didn't silently no-op.
                    logger.warning(f"truncated tool_call could not be recovered ({len(tool_buffer)} chars)")
                    yield sse_error(
                        "The model produced a truncated tool call (response cut off "
                        "before </tool_call>). Try the request again with a simpler "
                        "phrasing, or break it into smaller steps.",
                        recoverable=True,
                    )
                tool_buffer = ""

            if text_buffer:
                raw = text_buffer.strip()
                is_tool = False
                if raw and '"name"' in raw:
                    try:
                        try:
                            call = json.loads(raw)
                        except json.JSONDecodeError:
                            call = json.loads(raw.replace("{{", "{").replace("}}", "}"))
                        if isinstance(call, dict) and "name" in call:
                            is_tool = True
                            tool_name = call.get("name", "")
                            tool_args = call.get("arguments", {})
                            tool_calls_found.append({"name": tool_name, "args": tool_args})
                            events, result = await execute_tool(
                                tool_name=tool_name, tool_args=tool_args,
                                dashboard_id=dashboard_id, space_id=space_id,
                            )
                            for event in events:
                                yield event
                            err = result.get("error") if isinstance(result, dict) else None
                            if err:
                                sig = (tool_name, str(err)[:120])
                                if sig == last_failure:
                                    failure_streak += 1
                                else:
                                    last_failure, failure_streak = sig, 1
                                if failure_streak >= REPEAT_FAILURE_THRESHOLD:
                                    yield sse_error(
                                        f"Aborting after {failure_streak} repeated failures of '{tool_name}': {err}",
                                        recoverable=False,
                                    )
                                    yield sse_done()
                                    return
                            else:
                                last_failure, failure_streak = None, 0
                            tool_result_str = format_tool_result_for_llm(tool_name, result)
                            messages.append({"role": "assistant", "content": full_response})
                            messages.append({"role": "user", "content": f"<tool_response>\n{tool_result_str}\n</tool_response>"})
                    except (json.JSONDecodeError, TypeError):
                        pass
                if not is_tool:
                    clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                    # Filter out any remaining raw JSON tool-like strings
                    clean = re.sub(r'\{+"name"\s*:.*', '', clean, flags=re.DOTALL).strip()
                    if clean:
                        yield sse_text(clean)
                        text_parts.append(clean)

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            yield sse_error(f"AI generation failed: {e}")
            yield sse_done()
            return

        # If there were no tool calls, we're done
        if not tool_calls_found:
            full_text = "".join(text_parts).strip()
            if full_text:
                save_message(space_id=space_id, role="assistant", content=full_text)
            break

        # Save assistant message with tool info, then loop for more
        save_message(
            space_id=space_id,
            role="assistant",
            content="".join(text_parts).strip() or "(tool calls)",
            tool_calls=tool_calls_found,
        )
        tool_calls_found = []

    else:
        yield sse_text("\n\n(Reached maximum tool call limit.)")
        save_message(space_id=space_id, role="assistant", content="(Reached maximum tool call limit.)")

    yield sse_done(message_id=str(uuid4()))


def _build_space_context(space_id: str) -> str:
    """Build dataset context for all datasets linked to a space."""
    datasets = get_space_datasets(space_id)
    if not datasets:
        return "No datasets available in this space. The user needs to upload data first."

    ds_info = []
    for ds in datasets:
        try:
            schema = get_table_schema(ds.table_name)
        except Exception:
            schema = {}

        col_dict = ds.column_dictionary
        if isinstance(col_dict, str):
            col_dict = json.loads(col_dict)

        ds_info.append({
            "table_name": ds.table_name,
            "dataset_name": ds.dataset_name,
            "dataset_id": ds.id,
            "schema": schema,
            "column_dictionary": col_dict,
            "row_count": ds.row_count,
            "business_context": ds.business_context,
        })

    return build_datasets_context(ds_info)


def _build_widgets_context(dashboard_id: str) -> str:
    """One short line per widget — keeps the system prompt small.

    The LLM only needs titles + ids to pick a target. `update_widget` and
    `add_layer` are defensive — backend merges intelligently without the LLM
    having to see the current config. This trims ~3000 tokens of context.
    """
    dashboard = get_dashboard(dashboard_id)
    if not dashboard or not dashboard.widgets:
        return ""

    lines = ["\n\n## Existing Dashboard Widgets\n"]
    lines.append("Pick a widget_id from this list when modifying. Never ask the user for an id.\n")

    for w in dashboard.widgets:
        layers = (w.config or {}).get("layers") or []
        layer_hint = ""
        if layers:
            types = "+".join(l.get("type", "?") for l in layers)
            layer_hint = f" — layers: {types}"
        lines.append(f"- `{w.id}` — \"{w.title}\" ({w.widget_type}){layer_hint}")

    return "\n".join(lines)
