"""Composition sub-agents.

The top-level dashboard agent is the *composer*. It plans a widget as a stack of
layers and delegates the generation of each chart layer to a specialist
sub-agent (another Qwen3 call with a narrow prompt).

- design_chart_layer → emits a single `chart` layer (ECharts option). Called
  internally from `_exec_create_composed_widget`; not directly invokable by
  the LLM (visual layers — image/text/icon/shape — are built deterministically
  in tools.py without an LLM round-trip).
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

_CHART_SPECIALIST_PROMPT = """/no_think

You are a CHART LAYER specialist. Your only job is to emit ONE chart layer as JSON.

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

CHART-DATA-ANCHORED DECORATIONS — when the intent mentions a decoration on a specific bar/point ("crown on #1", "icon on max", "flag on March"), add `markPoint` to the relevant `series[i]`:
  ```
  "markPoint": {{
    "label": {{"show": false}},
    "data": [
      {{"type": "max", "symbol": "@crown", "symbolSize": [32,32], "itemStyle": {{"color": "#fbbf24"}}}}
    ]
  }}
  ```
- Use `@<name>` symbol aliases — the backend resolves them to ECharts path strings. ANY lucide name works: `@crown`, `@trophy`, `@bike`, `@star`, `@flame`, `@heart`, `@gem`, `@medal`, `@award`, `@sparkles`, `@rocket`, `@target`, `@diamond`, `@thumbs-up`, `@bell`, `@flag`, `@gift`, `@coffee`, `@bolt`, `@lock`, `@key`, `@map-pin`, etc. (kebab-case)
- Pin to a value with `{{"type": "max"}}` / `{{"type": "min"}}` (auto), or `{{"coord": [<value>, "<category-name>"]}}` for horizontal bar (yAxis = category), `[<category-name>, <value>]` for vertical bar.
- Multiple decorations? One `markPoint` per series, with multiple entries in `data`, each carrying its own `symbol` / `symbolSize` / `itemStyle`. Example: crown on max + bike on Nancy:
  ```
  "data": [
    {{"type": "max", "symbol": "@crown", "symbolSize": [32,32], "itemStyle": {{"color": "#fbbf24"}}}},
    {{"coord": [28682.15, "Nancy Robinson"], "symbol": "@bike", "symbolSize": [28,28], "itemStyle": {{"color": "#3b82f6"}}}}
  ]
  ```
- ALWAYS set `markPoint.label.show: false` so the symbol isn't overlaid with text.
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


