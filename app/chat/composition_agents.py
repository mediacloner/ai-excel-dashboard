"""Composition sub-agents.

The top-level dashboard agent is the *composer*. It plans a widget as a stack of
layers and delegates the generation of each layer to a specialist sub-agent
(another Qwen3 call with a narrow prompt).

- design_chart_layer   → emits a single `chart` layer (ECharts option)
- design_visual_layer  → emits an `image`/`text`/`svg`/`shape` layer

Each sub-agent returns a plain Layer dict (validated by the frontend renderer,
not here — we keep validation loose so the LLM has wiggle room).
"""

import json
import logging
import re
from typing import Any

from json_repair import repair_json

from app.config import get_config
from app.llm.client import _build_chat_model

logger = logging.getLogger(__name__)


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of an LLM response, best-effort."""
    text = _strip_think(text)
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        repaired = repair_json(text, return_objects=True)
        if isinstance(repaired, dict):
            return repaired
    except Exception:
        pass
    # Fallback: find the first {...} block
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            try:
                r = repair_json(match.group(0), return_objects=True)
                if isinstance(r, dict):
                    return r
            except Exception:
                pass
    return None


async def _call_specialist(prompt: str) -> dict | None:
    """Run a sub-agent LLM call and return its parsed JSON layer dict."""
    config = get_config()
    model_config = config.models.dashboard_agent or config.models.text_to_sql
    llm = _build_chat_model(model_config)
    response = await llm.ainvoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)
    return _extract_json(content)


# ---------------------------------------------------------------------------
# design_chart_layer
# ---------------------------------------------------------------------------

_CHART_SPECIALIST_PROMPT = """You are a CHART LAYER specialist. Your only job is to emit ONE chart layer as JSON.

A chart layer looks like:
{{
  "id": "<short unique id>",
  "type": "chart",
  "anchor": "fill",
  "z": 0,
  "echarts_option": {{ ... complete valid ECharts option ... }}
}}

Rules:
- Respond with ONLY the JSON object. No prose, no markdown fences.
- Use `anchor: "fill"` unless told otherwise — the chart fills the widget body.
- The `echarts_option` MUST be a complete valid ECharts option (tooltip, xAxis/yAxis or series.data as appropriate). Do not fabricate data — use the provided rows.
- BAR CHART SHAPE — pick by counting categorical axes in the intent:
  * CASE A (ONE categorical axis, e.g. "returns by status"): EXACTLY ONE series with N data items; category labels on `xAxis.data`. For per-bar colors wrap each value as `{{"value": <N>, "itemStyle": {{"color": "<hex>"}}}}`. DO NOT split into one-series-per-category — that renders as grouped bars and is WRONG here.
  * CASE B (TWO categorical axes, e.g. "orders per month split by status"): ONE series PER inner category (e.g. one series per status), each with M data items (one per month). For a STACKED chart, set `stack: "<name>"` on EVERY series (same name stacks them). Without `stack`, bars render grouped side-by-side.
- COPY the real numbers and labels from the Data block below. Every `series[*].data` MUST be non-empty.

CASE A template (one categorical axis — replace CAT_N/VAL_N with values from Data):
{{
  "xAxis": {{"type": "category", "data": ["CAT_1", "CAT_2", "CAT_3"]}},
  "yAxis": {{"type": "value"}},
  "tooltip": {{}},
  "series": [{{
    "type": "bar",
    "data": [
      {{"value": VAL_1, "itemStyle": {{"color": "#<hex>"}}}},
      {{"value": VAL_2, "itemStyle": {{"color": "#<hex>"}}}},
      {{"value": VAL_3, "itemStyle": {{"color": "#<hex>"}}}}
    ]
  }}]
}}

CASE B template (two categorical axes, STACKED — one series per inner category, `stack` on each):
{{
  "xAxis": {{"type": "category", "data": ["X_1", "X_2", "X_3"]}},
  "yAxis": {{"type": "value"}},
  "tooltip": {{"trigger": "axis"}},
  "legend": {{"data": ["GROUP_A", "GROUP_B", "GROUP_C"]}},
  "series": [
    {{"name": "GROUP_A", "type": "bar", "stack": "total", "itemStyle": {{"color": "#<hex>"}}, "data": [A1, A2, A3]}},
    {{"name": "GROUP_B", "type": "bar", "stack": "total", "itemStyle": {{"color": "#<hex>"}}, "data": [B1, B2, B3]}},
    {{"name": "GROUP_C", "type": "bar", "stack": "total", "itemStyle": {{"color": "#<hex>"}}, "data": [C1, C2, C3]}}
  ]
}}

User intent: {intent}

Data (columns and sample rows, already queried):
{data_summary}

Return ONLY the JSON layer."""


async def design_chart_layer(
    intent: str,
    data_summary: str,
) -> dict[str, Any] | None:
    prompt = _CHART_SPECIALIST_PROMPT.format(intent=intent, data_summary=data_summary)
    layer = await _call_specialist(prompt)
    if not layer:
        return None
    # Ensure required fields
    layer.setdefault("type", "chart")
    layer.setdefault("anchor", "fill")
    layer.setdefault("id", "chart")
    return layer


# ---------------------------------------------------------------------------
# design_visual_layer
# ---------------------------------------------------------------------------

_VISUAL_SPECIALIST_PROMPT = """You are a VISUAL LAYER specialist. You design non-chart layers — images, text annotations, SVG decorations, or simple shapes — that sit on top of or around a chart.

A layer is ONE of:

IMAGE layer (for logos, photos, icons):
{{
  "id": "<id>", "type": "image",
  "anchor": "<anchor>", "offset": [x, y], "size": [w, h], "z": 10,
  "asset_id": "<id from Available Assets>"   // preferred if using an uploaded asset
  // OR: "src": "/api/assets/file/<id>" or an absolute URL
}}

TEXT layer (annotations, badges, titles-inside-chart):
{{
  "id": "<id>", "type": "text",
  "anchor": "<anchor>", "offset": [x, y], "z": 5,
  "content": "<string>",
  "style": {{ "color": "#fff", "fontSize": 12, "fontWeight": 600 }}
}}

SVG layer (custom shapes, icons, decorations — inline SVG markup):
{{
  "id": "<id>", "type": "svg",
  "anchor": "<anchor>", "offset": [x, y], "size": [w, h], "z": 5,
  "markup": "<svg ...>...</svg>"
}}

SHAPE layer (rect/circle/line with a fill):
{{
  "id": "<id>", "type": "shape",
  "kind": "rect" | "circle" | "line",
  "anchor": "<anchor>", "offset": [x, y], "size": [w, h], "z": 5,
  "style": {{ "fill": "#5470c6", "opacity": 0.3 }}
}}

Anchors: top-left, top-center, top-right, center-left, center, center-right, bottom-left, bottom-center, bottom-right, fill.
`offset` is in pixels from the anchor point, inward. `size` is [w, h] in px.

Rules:
- Respond with ONLY the JSON object — one layer. No prose, no markdown fences.
- Logos go in top-right or top-left corners at 40-60px size. Don't cover chart data.
- Prefer `asset_id` over `src` when an available asset matches.
- Keep `z` >= the chart's z so the visual sits on top (chart is typically z=0).

User intent: {intent}

Available Assets (space-scoped images the user has uploaded):
{assets_summary}

Return ONLY the JSON layer."""


async def design_visual_layer(
    intent: str,
    assets_summary: str,
) -> dict[str, Any] | None:
    prompt = _VISUAL_SPECIALIST_PROMPT.format(intent=intent, assets_summary=assets_summary)
    layer = await _call_specialist(prompt)
    if not layer:
        return None
    layer.setdefault("id", "visual")
    layer.setdefault("z", 10)
    return layer
