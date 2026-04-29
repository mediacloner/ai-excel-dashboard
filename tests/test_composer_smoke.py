"""End-to-end-ish smoke tests for `_exec_create_composed_widget`.

We monkeypatch DB + chart specialist so the test runs without DuckDB and
without an LLM call. The point is to verify the layer construction pipeline
produces well-formed layers with the correct types, placements, and that
icons/images/texts all coexist — i.e. the example scenarios the user has
today still work and now also support icons.
"""

import pytest

from app.chat import tools
from app.chat.tools import execute_tool
from app.models.schemas import Widget, WidgetLayout


@pytest.fixture
def fake_db(monkeypatch):
    """Stub auto_place_widget, create_widget, get_asset, last query, specialist."""
    captured: dict = {}

    def fake_auto_place(dashboard_id, width=6, height=2):
        return WidgetLayout(x=0, y=0, w=width, h=height)

    def fake_create_widget(*, dashboard_id, widget_type, title, config, layout, sql_query=None):
        captured["config"] = config
        captured["title"] = title
        return Widget(
            id="w-1",
            dashboard_id=dashboard_id,
            widget_type=widget_type,
            title=title,
            config=config,
            sql_query=sql_query,
            layout=layout,
            created_at="now",
            updated_at="now",
        )

    class FakeAsset:
        def __init__(self, fname="logo.png"):
            self.filename = fname
            self.tags = ["brand"]

    def fake_get_asset(_id):
        return FakeAsset()

    def fake_get_query_result(_dashboard_id):
        return {
            "columns": ["region", "sales"],
            "data": [
                {"region": "North", "sales": 100},
                {"region": "South", "sales": 150},
                {"region": "East", "sales": 80},
            ],
            "sql": "SELECT region, SUM(sales) FROM dataset_x GROUP BY region",
        }

    async def fake_design_chart_layer(intent, data_summary):
        # Returns a minimal valid chart layer with non-empty data
        return {
            "id": "chart",
            "type": "chart",
            "anchor": "fill",
            "echarts_option": {
                "xAxis": {"type": "category", "data": ["North", "South", "East"]},
                "yAxis": {"type": "value"},
                "series": [{"type": "bar", "data": [100, 150, 80]}],
            },
        }

    monkeypatch.setattr(tools, "auto_place_widget", fake_auto_place)
    monkeypatch.setattr(tools, "create_widget", fake_create_widget)
    monkeypatch.setattr(tools, "get_asset", fake_get_asset)
    monkeypatch.setattr(tools, "_get_query_result", fake_get_query_result)
    monkeypatch.setattr(tools, "design_chart_layer", fake_design_chart_layer)
    return captured


class TestComposedWidgetWithIcons:
    """Original scenario reborn — chart + logo + icon in a single tool call."""

    async def test_chart_with_logo_and_icon(self, fake_db):
        events, result = await execute_tool(
            "create_composed_widget",
            {
                "title": "Sales by region",
                "chart": {"intent": "bar chart of sales by region, distinct color per bar"},
                "images": [
                    {
                        "asset_id": "logo-uuid",
                        "anchor": "top-right",
                        "offset": [10, 10],
                        "size": [40, 40],
                    }
                ],
                "icons": [
                    {
                        "name": "trending-up",
                        "anchor": "top-left",
                        "offset": [10, 10],
                        "size": [20, 20],
                        "color": "#22c55e",
                    }
                ],
                "width": 6,
                "height": 2,
            },
            dashboard_id="d1",
            space_id="s1",
        )

        assert "widget" in result, result
        layers = fake_db["config"]["layers"]
        types = [l["type"] for l in layers]
        assert "chart" in types
        assert "image" in types
        assert "icon" in types

        icon_layer = next(l for l in layers if l["type"] == "icon")
        assert icon_layer["name"] == "trending-up"
        assert icon_layer["color"] == "#22c55e"
        assert icon_layer["placement"] == "overlay"

    async def test_chart_with_text_annotation(self, fake_db):
        events, result = await execute_tool(
            "create_composed_widget",
            {
                "title": "Annotated chart",
                "chart": {"intent": "bar chart"},
                "texts": [
                    {
                        "content": "Q1 results",
                        "anchor": "bottom-left",
                        "offset": [10, 10],
                        "style": {"color": "#fff", "fontSize": 14},
                    }
                ],
            },
            dashboard_id="d1",
            space_id="s1",
        )
        layers = fake_db["config"]["layers"]
        text_layer = next(l for l in layers if l["type"] == "text")
        assert text_layer["content"] == "Q1 results"
        assert text_layer["placement"] == "annotation"

    async def test_purely_decorative_widget_no_chart(self, fake_db):
        # The user can compose a widget with only icons — no chart.
        events, result = await execute_tool(
            "create_composed_widget",
            {
                "title": "Status panel",
                "icons": [
                    {"name": "check-circle", "anchor": "center", "size": 48, "color": "#22c55e"},
                ],
            },
            dashboard_id="d1",
            space_id="s1",
        )
        assert "widget" in result, result
        layers = fake_db["config"]["layers"]
        assert len(layers) == 1
        assert layers[0]["type"] == "icon"
        assert layers[0]["size"] == [48, 48]

    async def test_empty_compose_errors(self, fake_db):
        events, result = await execute_tool(
            "create_composed_widget",
            {"title": "Empty"},
            dashboard_id="d1",
            space_id="s1",
        )
        assert "error" in result
        assert "No layers" in result["error"]

    async def test_icon_explicit_placement_preserved(self, fake_db):
        events, result = await execute_tool(
            "create_composed_widget",
            {
                "title": "Annotated",
                "icons": [
                    {
                        "name": "alert-triangle",
                        "anchor": "top-right",
                        "size": 16,
                        "color": "#ff4757",
                        "placement": "annotation",
                    }
                ],
            },
            dashboard_id="d1",
            space_id="s1",
        )
        icon = fake_db["config"]["layers"][0]
        assert icon["placement"] == "annotation"


class TestAddLayerValidatesIcon:
    async def test_add_layer_rejects_icon_without_name(self, monkeypatch):
        from app.chat import tools as t

        # Minimal widget stub
        from app.models.schemas import Widget, WidgetLayout

        widget = Widget(
            id="w1",
            dashboard_id="d1",
            widget_type="chart",
            title="t",
            config={"layers": [{"id": "chart", "type": "chart", "anchor": "fill"}]},
            sql_query=None,
            layout=WidgetLayout(),
            created_at="now",
            updated_at="now",
        )
        monkeypatch.setattr(t, "get_widget", lambda _id: widget)

        events, result = await execute_tool(
            "add_layer",
            {"widget_id": "w1", "layer": {"type": "icon", "anchor": "top-right"}},
            dashboard_id="d1",
            space_id="s1",
        )
        assert "error" in result
        assert "name" in result["error"].lower()

    async def test_add_layer_infers_text_type_from_content(self, monkeypatch):
        """LLM forgot `type: text` but sent `content` — backend must fold `type` in
        so the renderer doesn't drop the layer silently."""
        from app.chat import tools as t
        from app.models.schemas import Widget, WidgetLayout

        captured: dict = {}

        widget = Widget(
            id="w1",
            dashboard_id="d1",
            widget_type="chart",
            title="t",
            config={"layers": [{"id": "chart", "type": "chart", "anchor": "fill"}]},
            sql_query=None,
            layout=WidgetLayout(),
            created_at="now",
            updated_at="now",
        )
        monkeypatch.setattr(t, "get_widget", lambda _id: widget)

        def fake_update_widget_config(widget_id, updates):
            captured["updates"] = updates
            new_config = dict(widget.config)
            new_config["layers"] = updates["layers"]
            return widget.model_copy(update={"config": new_config})

        monkeypatch.setattr(t, "update_widget_config", fake_update_widget_config)

        events, result = await execute_tool(
            "add_layer",
            {
                "widget_id": "w1",
                "layer": {
                    # NO "type" field — exact failure shape we hit in prod.
                    "content": "Total Returns: 1001",
                    "anchor": "bottom-left",
                    "offset": [10, 10],
                    "placement": "annotation",
                    "color": "red",  # also at top-level (LLM mistake)
                    "id": "layer-1",
                },
            },
            dashboard_id="d1",
            space_id="s1",
        )
        assert "widget" in result, result
        added = [l for l in captured["updates"]["layers"] if l.get("id") == "layer-1"][0]
        assert added["type"] == "text"
        # Top-level color was folded into style.color
        assert added.get("style", {}).get("color") == "red"
        assert "color" not in added or added.get("color") is None

    async def test_add_layer_text_without_content_errors(self, monkeypatch):
        from app.chat import tools as t
        from app.models.schemas import Widget, WidgetLayout

        widget = Widget(
            id="w1",
            dashboard_id="d1",
            widget_type="chart",
            title="t",
            config={"layers": []},
            sql_query=None,
            layout=WidgetLayout(),
            created_at="now",
            updated_at="now",
        )
        monkeypatch.setattr(t, "get_widget", lambda _id: widget)

        events, result = await execute_tool(
            "add_layer",
            {"widget_id": "w1", "layer": {"type": "text", "anchor": "top-left"}},
            dashboard_id="d1",
            space_id="s1",
        )
        assert "error" in result
        assert "content" in result["error"].lower()

    async def test_add_layer_strips_invalid_placement(self, monkeypatch):
        from app.chat import tools as t
        from app.models.schemas import Widget, WidgetLayout

        captured: dict = {}

        widget = Widget(
            id="w1",
            dashboard_id="d1",
            widget_type="chart",
            title="t",
            config={"layers": [{"id": "chart", "type": "chart", "anchor": "fill"}]},
            sql_query=None,
            layout=WidgetLayout(),
            created_at="now",
            updated_at="now",
        )
        monkeypatch.setattr(t, "get_widget", lambda _id: widget)

        def fake_update_widget_config(widget_id, updates):
            captured["updates"] = updates
            # Return a synthesized widget reflecting the merged layers
            new_config = dict(widget.config)
            new_config["layers"] = updates["layers"]
            return widget.model_copy(update={"config": new_config})

        monkeypatch.setattr(t, "update_widget_config", fake_update_widget_config)

        events, result = await execute_tool(
            "add_layer",
            {
                "widget_id": "w1",
                "layer": {
                    "type": "icon",
                    "name": "star",
                    "anchor": "top-right",
                    "placement": "moon",  # invalid
                },
            },
            dashboard_id="d1",
            space_id="s1",
        )
        # The bad placement was dropped, but the layer still got added.
        assert "widget" in result, result
        new_layers = captured["updates"]["layers"]
        added = [l for l in new_layers if l.get("type") == "icon"][0]
        assert "placement" not in added or added.get("placement") is None
