"""Tool registry, parser, and executor for the dashboard agent."""

import json
import logging
import re
import time
from typing import Any

from json_repair import repair_json

from app.chat.agent import execute_user_query
from app.chat.composition_agents import design_chart_layer
from app.chat.echarts_symbols import resolve_aliases as _resolve_echarts_aliases
from app.chat.streaming import (
    sse_tool_call_result,
    sse_tool_call_start,
    sse_widget_create,
    sse_widget_update,
)
from app.database.assets import get_asset, list_space_assets
from app.database.dashboards import (
    auto_place_widget,
    create_widget,
    get_widget,
    update_widget_config,
    update_widget_layout,
)
from app.models.schemas import WidgetLayout

logger = logging.getLogger(__name__)


# Per-dashboard scratchpad: latest successful query_data result, so the
# declarative composer can use real data without the LLM having to re-pass it
# through tool args (which Qwen3:8b often truncates or hallucinates).
_LAST_QUERY: dict[str, dict] = {}


def _store_query_result(dashboard_id: str, sql: str, result: dict) -> None:
    _LAST_QUERY[dashboard_id] = {"sql": sql, "columns": result.get("columns", []), "data": result.get("data", [])}


def _get_query_result(dashboard_id: str) -> dict | None:
    return _LAST_QUERY.get(dashboard_id)


async def execute_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    dashboard_id: str,
    space_id: str,
) -> tuple[list[str], dict[str, Any]]:
    """Execute a tool call and return (sse_events, result).

    Returns a list of SSE event strings and the raw result dict.
    """
    events = []
    events.append(sse_tool_call_start(tool_name, tool_args))
    start = time.time()
    logger.info(f"[tool] {tool_name} args={tool_args}")

    try:
        if tool_name == "query_data":
            result = _exec_query_data(tool_args)
            if "error" not in result and "data" in result:
                _store_query_result(dashboard_id, tool_args.get("sql", ""), result)

        elif tool_name == "create_chart_widget":
            result = _exec_create_chart(tool_args, dashboard_id)
            if "widget" in result:
                events.append(sse_widget_create(result["widget"]))

        elif tool_name == "create_kpi_widget":
            result = _exec_create_kpi(tool_args, dashboard_id)
            if "widget" in result:
                events.append(sse_widget_create(result["widget"]))

        elif tool_name == "create_table_widget":
            result = _exec_create_table(tool_args, dashboard_id)
            if "widget" in result:
                events.append(sse_widget_create(result["widget"]))

        elif tool_name == "update_widget":
            result = _exec_update_widget(tool_args)
            if "widget" in result:
                # Send full widget so frontend can replace it entirely
                events.append(sse_widget_update(
                    result["widget_id"],
                    result["widget"],
                ))

        elif tool_name == "list_assets":
            result = _exec_list_assets(tool_args, space_id)

        elif tool_name == "build_image_layer":
            result = _exec_build_image_layer(tool_args)

        elif tool_name == "build_icon_layer":
            result = _exec_build_icon_layer(tool_args)

        elif tool_name == "create_composed_widget":
            result = await _exec_create_composed_widget(tool_args, dashboard_id)
            if "widget" in result:
                events.append(sse_widget_create(result["widget"]))

        elif tool_name == "add_layer":
            result = _exec_add_layer(tool_args)
            if "widget" in result:
                events.append(sse_widget_update(result["widget_id"], result["widget"]))

        else:
            result = {"error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        logger.error(f"Tool execution failed: {tool_name}: {e}")
        result = {"error": str(e)}

    duration = int((time.time() - start) * 1000)
    # Strip the full widget from the result summary sent to SSE tool_call_result
    summary = {k: v for k, v in result.items() if k != "widget"}
    events.append(sse_tool_call_result(tool_name, summary, duration))

    return events, result


def _exec_query_data(args: dict) -> dict:
    """Execute a SQL query using the existing query engine."""
    sql = args.get("sql", "")
    if not sql:
        return {"error": "No SQL provided"}

    result = execute_user_query(sql)
    if result.success:
        return {
            "columns": list(result.data[0].keys()) if result.data else [],
            "data": result.data,
            "row_count": result.row_count,
            "truncated": result.truncated,
        }
    else:
        return {"error": result.error}


def _chart_has_data(option: dict) -> bool:
    """Heuristic: does an echarts_option have any series data?"""
    series = option.get("series") or []
    if isinstance(series, dict):
        series = [series]
    for s in series:
        d = s.get("data")
        if d is None:
            continue
        if isinstance(d, list) and len(d) > 0:
            return True
    # Some chart types put data on xAxis instead
    x = option.get("xAxis")
    if isinstance(x, dict) and x.get("data"):
        return True
    if isinstance(x, list):
        for xi in x:
            if isinstance(xi, dict) and xi.get("data"):
                return True
    return False


def _exec_create_chart(args: dict, dashboard_id: str) -> dict:
    """Create an ECharts chart widget."""
    title = args.get("title", "Chart")
    echarts_option = args.get("echarts_option", {})
    sql_query = args.get("sql_query", "")
    width = args.get("width", 6)
    height = args.get("height", 2)

    # Rewrite "@crown" / "@trophy" / … aliases anywhere in the option
    # tree into real `path://<d>` strings ECharts can render.
    echarts_option = _resolve_echarts_aliases(echarts_option)

    if not _chart_has_data(echarts_option):
        return {"error": "Chart series data is empty. Run query_data first (use the exact `table_name` from Available Datasets, not the dataset label), then build the echarts_option with real numbers."}

    # Must have run a real query in this conversation — prevents fabricated data.
    if _get_query_result(dashboard_id) is None:
        return {"error": "No query has been run yet. Call query_data FIRST with real SQL against the dataset, then build the chart from those results."}

    # Auto-place in the grid
    layout = auto_place_widget(dashboard_id, width=width, height=height)

    widget = create_widget(
        dashboard_id=dashboard_id,
        widget_type="chart",
        title=title,
        config={"echarts_option": echarts_option},
        layout=layout,
        sql_query=sql_query,
    )

    return {"widget_id": widget.id, "status": "created", "widget": widget.model_dump()}


def _exec_create_kpi(args: dict, dashboard_id: str) -> dict:
    """Create a KPI card widget."""
    title = args.get("title", "KPI")
    value = args.get("value", "—")
    subtitle = args.get("subtitle", "")
    trend = args.get("trend")
    sql_query = args.get("sql_query", "")
    width = args.get("width", 3)
    height = args.get("height", 1)

    if not value or str(value).strip() in {"—", "-", "?", ""}:
        return {"error": "KPI value is empty. Run query_data first to get the real number."}
    if _get_query_result(dashboard_id) is None:
        return {"error": "No query has been run yet. Call query_data FIRST to compute the real KPI value."}

    # Tidy up value formatting — LLMs often emit raw long floats like "1242.6116780000007".
    try:
        as_float = float(str(value).replace(",", "").replace("$", "").replace("€", "").replace("%", "").strip())
        # Preserve currency/percent prefixes/suffixes if present
        raw_str = str(value).strip()
        prefix = ""
        suffix = ""
        for sym in ("$", "€", "£", "¥"):
            if raw_str.startswith(sym):
                prefix = sym
                break
        for sym in ("%", "x", "×"):
            if raw_str.endswith(sym):
                suffix = sym
                break
        # If it's a big number, use thousands separators; if fractional, 2 decimals
        if as_float == int(as_float):
            formatted = f"{int(as_float):,}"
        else:
            formatted = f"{as_float:,.2f}"
        value = f"{prefix}{formatted}{suffix}"
    except (ValueError, TypeError):
        pass  # non-numeric string, leave alone

    # Auto-override from cached query if the LLM supplied the wrong number.
    # Heuristic: if the last successful query returned exactly one row with one
    # numeric column, that is almost certainly the KPI value the user wanted.
    cached = _get_query_result(dashboard_id)
    if cached and cached.get("data") and len(cached["data"]) == 1:
        row = cached["data"][0]
        numeric_vals = [v for v in row.values() if isinstance(v, (int, float))]
        if len(numeric_vals) == 1:
            real = numeric_vals[0]
            # Only override if numerically different — tolerate reformatted
            # versions of the same number (e.g. "1,242.61" vs 1242.6116779).
            try:
                llm_num = float(str(value).replace(",", "").replace("$", "").replace("€", "").replace("%", ""))
                real_f = float(real)
                if abs(llm_num - real_f) > max(abs(real_f) * 0.01, 0.5):
                    logger.warning(f"KPI value mismatch: LLM='{value}' cached={real} — using cached")
                    # Format cached value the same way
                    if real_f == int(real_f):
                        value = f"{int(real_f):,}"
                    else:
                        value = f"{real_f:,.2f}"
            except (ValueError, TypeError):
                # LLM value is a non-numeric formatted string — trust it
                pass

    layout = auto_place_widget(dashboard_id, width=width, height=height)

    widget = create_widget(
        dashboard_id=dashboard_id,
        widget_type="kpi",
        title=title,
        config={"value": value, "subtitle": subtitle, "trend": trend},
        layout=layout,
        sql_query=sql_query,
    )

    return {"widget_id": widget.id, "status": "created", "widget": widget.model_dump()}


def _exec_create_table(args: dict, dashboard_id: str) -> dict:
    """Create a data table widget."""
    title = args.get("title", "Table")
    columns = args.get("columns", [])
    data = args.get("data", [])
    sql_query = args.get("sql_query", "")
    width = args.get("width", 6)
    height = args.get("height", 3)

    # Always prefer cached query results — the LLM fabricates table contents.
    cached = _get_query_result(dashboard_id)
    if cached and cached.get("data") and cached.get("columns"):
        columns = cached["columns"]
        data = [[row.get(c) for c in columns] for row in cached["data"]]
    elif not data or not columns:
        return {"error": "No cached query result and no data provided. Run query_data first."}

    layout = auto_place_widget(dashboard_id, width=width, height=height)

    widget = create_widget(
        dashboard_id=dashboard_id,
        widget_type="table",
        title=title,
        config={"columns": columns, "data": data},
        layout=layout,
        sql_query=sql_query,
    )

    return {"widget_id": widget.id, "status": "created", "widget": widget.model_dump()}


def _exec_list_assets(_args: dict, space_id: str) -> dict:
    """List all image/svg assets available in this space."""
    assets = list_space_assets(space_id)
    return {
        "assets": [
            {
                "id": a.id,
                "filename": a.filename,
                "mime": a.mime,
                "url": a.url,
                "tags": a.tags,
            }
            for a in assets
        ],
    }


async def _exec_create_composed_widget(args: dict, dashboard_id: str) -> dict:
    """Declarative, single-call composer.

    Takes a full widget plan and orchestrates sub-agents backend-side so the
    LLM can't drop layers between tool calls (Qwen3:8b struggles with that).

    args:
      title: str
      chart: {"intent": str, "data_summary": str|dict} | None
      images: [{"asset_id": str, "anchor": str, "offset": [x,y], "size": [w,h], "placement"?: str, "z"?: int, "id"?: str}]
      texts:  [{"content": str, "anchor": str, "offset": [x,y], "placement"?: str, "z"?: int, "style"?: {...}}]
      icons:  [{"name": str, "anchor": str, "offset": [x,y], "size": [w,h], "color"?: str, "placement"?: str, "z"?: int, "id"?: str}]
      sql_query: str
      width: int, height: int
      canvas: {...}
    """
    title = args.get("title", "Widget")
    chart_spec = args.get("chart")
    images = args.get("images", []) or []
    texts = args.get("texts", []) or []
    icons = args.get("icons", []) or []
    sql_query = args.get("sql_query", "")
    width = args.get("width", 6)
    height = args.get("height", 2)
    canvas = args.get("canvas", {})

    layers: list[dict] = []

    # Chart layer (optional — a purely decorative widget may have no chart)
    if chart_spec and isinstance(chart_spec, dict):
        intent = chart_spec.get("intent", "")
        # Prefer the server-cached last query result — the LLM often
        # fabricates / truncates data_summary. Fall back to what it passed.
        cached = _get_query_result(dashboard_id)
        if cached and cached.get("data"):
            data_summary_obj = {"columns": cached["columns"], "data": cached["data"], "sql": cached["sql"]}
            data_summary = json.dumps(data_summary_obj, default=str)
            if not sql_query:
                sql_query = cached.get("sql", "")
        else:
            data_summary = chart_spec.get("data_summary", "")
            if isinstance(data_summary, (list, dict)):
                data_summary = json.dumps(data_summary, default=str)
        if intent:
            chart_layer = await design_chart_layer(intent, str(data_summary))
            if chart_layer is None:
                return {"error": "Chart specialist failed to produce a layer"}
            chart_layer.setdefault("id", "chart")
            chart_layer.setdefault("type", "chart")
            chart_layer.setdefault("anchor", "fill")
            chart_layer.setdefault("z", 0)
            # Resolve `@crown`-style aliases inside echarts_option before validation.
            if chart_layer.get("echarts_option"):
                chart_layer["echarts_option"] = _resolve_echarts_aliases(chart_layer["echarts_option"])
            if not _chart_has_data(chart_layer.get("echarts_option") or {}):
                return {"error": "Chart specialist produced an empty chart (series data missing). Re-run create_composed_widget — ensure query_data has returned rows first, and describe the data in `chart.intent` so the specialist fills series[0].data."}
            layers.append(chart_layer)

    # Image layers — deterministic, validated
    for i, img in enumerate(images):
        asset_id = img.get("asset_id", "")
        if not asset_id:
            return {"error": f"images[{i}] missing asset_id"}
        if get_asset(asset_id) is None:
            return {"error": f"images[{i}] asset_id '{asset_id}' does not exist — use one from list_assets"}
        anchor = img.get("anchor", "top-right")
        if anchor not in _VALID_ANCHORS:
            return {"error": f"images[{i}] invalid anchor '{anchor}'"}
        layer = {
            "id": img.get("id", f"image-{i}"),
            "type": "image",
            "anchor": anchor,
            "offset": img.get("offset", [10, 10]),
            "size": img.get("size", [40, 40]),
            "asset_id": asset_id,
        }
        _apply_placement(layer, img, default_placement="overlay", default_z=10 + i)
        layers.append(layer)

    # Text layers — simple deterministic construction
    for i, t in enumerate(texts):
        content = t.get("content", "")
        if not content:
            continue
        anchor = t.get("anchor", "top-left")
        if anchor not in _VALID_ANCHORS:
            return {"error": f"texts[{i}] invalid anchor '{anchor}'"}
        layer = {
            "id": t.get("id", f"text-{i}"),
            "type": "text",
            "anchor": anchor,
            "offset": t.get("offset", [10, 10]),
            "content": content,
            "style": t.get("style", {}),
        }
        _apply_placement(layer, t, default_placement="annotation", default_z=20 + i)
        layers.append(layer)

    # Icon layers — lucide icon by name, no asset upload required
    for i, ic in enumerate(icons):
        name = (ic.get("name") or "").strip()
        if not name:
            return {"error": f"icons[{i}] missing name (e.g. 'trending-up', 'star')"}
        anchor = ic.get("anchor", "top-right")
        if anchor not in _VALID_ANCHORS:
            return {"error": f"icons[{i}] invalid anchor '{anchor}'"}
        size = ic.get("size", [20, 20])
        if isinstance(size, int):
            size = [size, size]
        layer = {
            "id": ic.get("id", f"icon-{i}"),
            "type": "icon",
            "anchor": anchor,
            "offset": ic.get("offset", [10, 10]),
            "size": size,
            "name": name,
            "color": ic.get("color"),
        }
        _apply_placement(layer, ic, default_placement="overlay", default_z=15 + i)
        layers.append(layer)

    if not layers:
        return {"error": "No layers produced — provide at least a chart or one image/text/icon."}

    layout = auto_place_widget(dashboard_id, width=width, height=height)
    widget = create_widget(
        dashboard_id=dashboard_id,
        widget_type="chart",
        title=title,
        config={"canvas": canvas, "layers": layers},
        layout=layout,
        sql_query=sql_query,
    )
    return {
        "widget_id": widget.id,
        "status": "created",
        "layer_count": len(layers),
        "widget": widget.model_dump(),
    }


_VALID_ANCHORS = {
    "top-left", "top-center", "top-right",
    "center-left", "center", "center-right",
    "bottom-left", "bottom-center", "bottom-right",
    "fill",
}

_VALID_PLACEMENTS = {"background", "chart", "overlay", "annotation", "foreground"}


def _apply_placement(
    layer: dict,
    src: dict,
    *,
    default_placement: str,
    default_z: int,
) -> None:
    """Resolve placement + z onto a layer dict.

    Precedence: explicit `placement` > explicit `z` > default placement.
    The renderer maps placement→z, so once placement is set we don't need z;
    but we still set z = default_z as a fallback for any consumer reading it.
    """
    placement = src.get("placement")
    if placement:
        if placement not in _VALID_PLACEMENTS:
            placement = default_placement
        layer["placement"] = placement
        # leave z unset / default — placement wins in renderer
        layer["z"] = src.get("z", default_z)
        return
    if "z" in src:
        layer["z"] = src["z"]
        return
    # Neither given — use default placement (semantic, future-proof)
    layer["placement"] = default_placement
    layer["z"] = default_z


def _exec_build_image_layer(args: dict) -> dict:
    """Deterministic image-layer builder. No LLM — the composer must supply
    an asset_id that was returned by list_assets. Validates the id exists."""
    asset_id = args.get("asset_id", "")
    if not asset_id:
        return {"error": "asset_id is required (get it from list_assets)"}

    asset = get_asset(asset_id)
    if asset is None:
        return {"error": f"No asset with id '{asset_id}'. Call list_assets first and copy the id EXACTLY."}

    # Intent hint from the composer (e.g. "clouds background") — used only to
    # detect mismatches with the actual asset. Purely advisory.
    intent_hint = (args.get("intent") or "").lower().strip()
    if intent_hint:
        asset_tokens = (asset.filename.lower() + " " + " ".join(asset.tags or [])).lower()
        hint_tokens = [t for t in intent_hint.split() if len(t) > 3 and t not in {"background", "image", "logo", "picture", "photo", "corner", "widget"}]
        if hint_tokens and not any(t in asset_tokens for t in hint_tokens):
            return {
                "error": (
                    f"The only matching asset has filename='{asset.filename}' tags={asset.tags}. "
                    f"It does not match the requested intent '{intent_hint}'. "
                    "Ask the user to upload or paste a URL for that specific image, instead of substituting."
                )
            }

    anchor = args.get("anchor", "top-right")
    if anchor not in _VALID_ANCHORS:
        return {"error": f"anchor must be one of {sorted(_VALID_ANCHORS)}"}

    offset = args.get("offset", [10, 10])
    size = args.get("size", [40, 40])
    layer_id = args.get("id", "logo")

    # Default placement: "background" if anchor is fill (i.e. cover-the-widget),
    # otherwise "overlay" (logos in corners).
    default_placement = "background" if anchor == "fill" else "overlay"
    default_z = -1 if anchor == "fill" else 10

    layer = {
        "id": layer_id,
        "type": "image",
        "anchor": anchor,
        "offset": offset,
        "size": size,
        "asset_id": asset_id,
    }
    _apply_placement(layer, args, default_placement=default_placement, default_z=default_z)
    return {"layer": layer}


def _exec_build_icon_layer(args: dict) -> dict:
    """Deterministic icon-layer builder. The LLM picks an icon by name (lucide
    PascalCase or kebab-case — the renderer normalises). No assets, no markup."""
    name = (args.get("name") or "").strip()
    if not name:
        return {"error": "name is required (e.g. 'trending-up', 'star', 'alert-triangle')"}

    anchor = args.get("anchor", "top-right")
    if anchor not in _VALID_ANCHORS:
        return {"error": f"anchor must be one of {sorted(_VALID_ANCHORS)}"}

    size = args.get("size", [20, 20])
    if isinstance(size, int):
        size = [size, size]

    layer = {
        "id": args.get("id", f"icon-{name}"),
        "type": "icon",
        "anchor": anchor,
        "offset": args.get("offset", [10, 10]),
        "size": size,
        "name": name,
        "color": args.get("color"),
    }
    _apply_placement(layer, args, default_placement="overlay", default_z=15)
    return {"layer": layer}


def _legacy_to_chart_layer(config: dict) -> list[dict]:
    """Wrap a legacy `{echarts_option: ...}` config as a single chart layer."""
    opt = config.get("echarts_option")
    if not opt:
        return []
    return [{
        "id": "chart", "type": "chart", "anchor": "fill", "z": 0,
        "echarts_option": opt,
    }]


def _infer_layer_type(layer: dict) -> str | None:
    """Infer the `type` field from which payload fields are present.

    Mirrors the renderer's defensive inference so the stored shape stays
    valid even if the LLM forgets `type`.
    """
    if layer.get("type"):
        return layer["type"]
    if layer.get("echarts_option"):
        return "chart"
    if layer.get("markup"):
        return "svg"
    if layer.get("asset_id") or layer.get("src"):
        return "image"
    if layer.get("name"):
        return "icon"
    if layer.get("kind"):
        return "shape"
    if "content" in layer:
        return "text"
    return None


def _exec_add_layer(args: dict) -> dict:
    """Append a single layer to an existing widget.

    Handles the legacy migration: if the widget's config has `echarts_option`
    but no `layers`, wrap the chart as a layer before appending.
    """
    widget_id = args.get("widget_id", "")
    layer = args.get("layer")

    if not widget_id:
        return {"error": "widget_id is required"}
    if not isinstance(layer, dict):
        return {"error": "layer must be a dict"}

    widget = get_widget(widget_id)
    if widget is None:
        return {"error": f"Widget '{widget_id}' not found"}

    # Defensive: infer type if missing. Without this the layer is stored
    # untyped and the renderer falls through every branch → invisible.
    if not layer.get("type"):
        guessed = _infer_layer_type(layer)
        if guessed is None:
            return {"error": "layer is missing `type` and no inference is possible. Set type to one of: chart, image, text, svg, shape, icon."}
        layer["type"] = guessed

    # Defensive: text layers expect `style.color`, but LLMs sometimes
    # copy the icon pattern and put `color` at top level. Fold it in.
    if layer["type"] == "text" and layer.get("color") and not (layer.get("style") or {}).get("color"):
        style = dict(layer.get("style") or {})
        style["color"] = layer.pop("color")
        layer["style"] = style

    # Validate image layers reference a real asset so we fail loud, not 404.
    if layer.get("type") == "image":
        asset_id = layer.get("asset_id")
        src = layer.get("src")
        if asset_id and get_asset(asset_id) is None:
            return {"error": f"Image layer references unknown asset_id '{asset_id}'. Call list_assets and use one of the ids verbatim."}
        if not asset_id and not src:
            return {"error": "Image layer needs asset_id (preferred) or src."}

    # Icon layers need a name; the renderer falls back to HelpCircle but loud is better.
    if layer.get("type") == "icon":
        if not (layer.get("name") or "").strip():
            return {"error": "Icon layer needs a `name` (e.g. 'trending-up', 'star', 'alert-triangle')."}

    # Text layers need content; an empty text layer renders nothing.
    if layer.get("type") == "text":
        if not (layer.get("content") or "").strip():
            return {"error": "Text layer needs `content` (the string to display)."}

    # Normalise placement: if the LLM passed an invalid placement, drop it
    # (renderer falls back to z). Don't error — the layer may still be useful.
    placement = layer.get("placement")
    if placement and placement not in _VALID_PLACEMENTS:
        layer.pop("placement", None)

    existing_layers = widget.config.get("layers") or []
    if not existing_layers:
        existing_layers = _legacy_to_chart_layer(widget.config)

    # Ensure the new layer has an id
    layer.setdefault("id", f"layer-{len(existing_layers)}")

    new_layers = [*existing_layers, layer]
    canvas = widget.config.get("canvas", {})

    updated = update_widget_config(widget_id, {"layers": new_layers, "canvas": canvas})
    if updated is None:
        return {"error": "Update failed"}
    return {"widget_id": updated.id, "status": "updated", "widget": updated.model_dump()}


def _exec_update_widget(args: dict) -> dict:
    """Update an existing widget's config.

    Smart routing: if the widget uses the composition schema (has `layers`)
    and the LLM passed top-level `echarts_option`, redirect the update into
    the first chart layer's echarts_option — that's what actually renders.

    Also supports resizing: `updates.layout = {"w": 4, "h": 2, "x": 0, "y": 0}`
    (all fields optional) is pulled out and persisted to the `layout` column.
    """
    widget_id = args.get("widget_id", "")
    updates = args.get("updates", {})

    if not widget_id:
        return {"error": "No widget_id provided"}

    current = get_widget(widget_id)
    if current is None:
        return {"error": f"Widget '{widget_id}' not found"}

    # Pull out layout updates (resize/move) — stored in a separate column.
    if isinstance(updates, dict) and isinstance(updates.get("layout"), dict):
        layout_patch = updates.pop("layout")
        new_layout = current.layout.model_copy(update={
            k: int(v) for k, v in layout_patch.items()
            if k in ("x", "y", "w", "h") and isinstance(v, (int, float))
        })
        # Clamp to the 12-col grid
        new_layout.w = max(1, min(12, new_layout.w))
        new_layout.x = max(0, min(12 - new_layout.w, new_layout.x))
        new_layout.h = max(1, new_layout.h)
        new_layout.y = max(0, new_layout.y)
        update_widget_layout(widget_id, new_layout)

    if isinstance(updates, dict) and "echarts_option" in updates:
        # Resolve `@crown`-style aliases inside the partial option update too.
        updates["echarts_option"] = _resolve_echarts_aliases(updates["echarts_option"])
        layers = current.config.get("layers") or []
        if layers:
            # Redirect: merge into the first chart layer, not top-level.
            chart_idx = next((i for i, l in enumerate(layers) if l.get("type") == "chart"), None)
            if chart_idx is not None:
                new_layers = [dict(l) for l in layers]
                # Fallback chain: legacy echarts_option (original chart spec)
                # → current chart-layer option → LLM update. This preserves
                # fields the LLM drops (e.g. `series[0].type`).
                legacy_opt = current.config.get("echarts_option") or {}
                current_opt = new_layers[chart_idx].get("echarts_option") or {}
                base_opt = _dict_deep_merge(legacy_opt, current_opt) if legacy_opt else current_opt
                merged_opt = _dict_deep_merge(base_opt, updates["echarts_option"])
                new_layers[chart_idx]["echarts_option"] = merged_opt
                updates = {k: v for k, v in updates.items() if k != "echarts_option"}
                updates["layers"] = new_layers

    if updates:
        widget = update_widget_config(widget_id, updates)
        if widget is None:
            return {"error": f"Widget '{widget_id}' not found"}
    else:
        widget = get_widget(widget_id)
        if widget is None:
            return {"error": f"Widget '{widget_id}' not found"}

    return {"widget_id": widget.id, "status": "updated", "widget": widget.model_dump()}


def _dict_deep_merge(base: dict, overlay: dict) -> dict:
    """Local deep merge — dicts merged recursively, lists merged BY INDEX
    when corresponding items are dicts. This preserves fields the LLM drops
    (e.g. `series[0].type` when updating only colors)."""
    result = {**base}
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _dict_deep_merge(result[key], value)
        elif (
            key in result
            and isinstance(result[key], list)
            and isinstance(value, list)
            and all(isinstance(x, dict) for x in result[key] + value)
        ):
            # Index-wise dict merge
            merged: list = []
            for i in range(max(len(result[key]), len(value))):
                if i < len(result[key]) and i < len(value):
                    merged.append(_dict_deep_merge(result[key][i], value[i]))
                elif i < len(value):
                    merged.append(value[i])
                else:
                    merged.append(result[key][i])
            result[key] = merged
        else:
            result[key] = value
    return result


def _repair_json(s: str) -> dict | None:
    """Attempt to parse and repair malformed JSON from LLM output."""
    s = s.strip()
    # Try as-is first
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # Try fixing double braces
    try:
        return json.loads(s.replace("{{", "{").replace("}}", "}"))
    except json.JSONDecodeError:
        pass
    # Use json_repair as last resort (handles missing commas, brackets, duplicate keys, etc.)
    try:
        repaired = repair_json(s, return_objects=True)
        if isinstance(repaired, dict):
            return repaired
    except Exception:
        pass
    return None


def parse_llm_response(text: str) -> list[dict]:
    """Parse LLM response into text chunks and tool calls.

    Handles Hermes-style <tool_call> tags. Strips <think> blocks from Qwen3.
    """
    # Strip thinking tags
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    parts = []
    pattern = r"<tool_call>\s*([\s\S]*?)\s*</tool_call>"
    segments = re.split(pattern, text, flags=re.DOTALL)

    for i, segment in enumerate(segments):
        segment = segment.strip()
        if not segment:
            continue

        if i % 2 == 0:
            # Text segment
            parts.append({"type": "text", "content": segment})
        else:
            # Tool call JSON — repair malformed LLM output
            call = _repair_json(segment)
            try:
                if call is None:
                    raise ValueError("Could not parse")
                parts.append({
                    "type": "tool_call",
                    "name": call.get("name", ""),
                    "arguments": call.get("arguments", {}),
                })
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse tool call JSON: {segment[:200]}")
                parts.append({"type": "text", "content": segment})

    return parts


def format_tool_result_for_llm(tool_name: str, result: dict) -> str:
    """Format a tool result as a message to feed back to the LLM."""
    # For query results, truncate large data arrays
    if tool_name == "query_data" and "data" in result:
        data = result["data"]
        if len(data) > 20:
            truncated_data = data[:20]
            summary = {**result, "data": truncated_data, "note": f"Showing first 20 of {len(data)} rows"}
        else:
            summary = result
    else:
        summary = result

    return json.dumps(summary, default=str)
