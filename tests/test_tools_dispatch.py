"""Tool dispatch contract tests.

After this PR, `design_chart_layer`, `design_visual_layer`, and
`create_composition` are NO LONGER directly invokable by the LLM. Calling
them via `execute_tool` must return an "Unknown tool" error.

`build_icon_layer` is the new tool — verify it produces a valid icon layer.
`build_image_layer` continues to work and now honors `placement`.
"""

from app.chat.tools import execute_tool


class TestOrphanToolsRemoved:
    async def test_design_chart_layer_returns_unknown(self):
        events, result = await execute_tool(
            "design_chart_layer",
            {"intent": "bar chart"},
            dashboard_id="d1",
            space_id="s1",
        )
        assert "error" in result
        assert "Unknown tool" in result["error"]

    async def test_design_visual_layer_returns_unknown(self):
        events, result = await execute_tool(
            "design_visual_layer",
            {"intent": "logo"},
            dashboard_id="d1",
            space_id="s1",
        )
        assert "error" in result
        assert "Unknown tool" in result["error"]

    async def test_create_composition_returns_unknown(self):
        events, result = await execute_tool(
            "create_composition",
            {"layers": []},
            dashboard_id="d1",
            space_id="s1",
        )
        assert "error" in result
        assert "Unknown tool" in result["error"]


class TestBuildIconLayer:
    async def test_basic_icon_layer(self):
        events, result = await execute_tool(
            "build_icon_layer",
            {
                "name": "trending-up",
                "anchor": "top-right",
                "offset": [10, 10],
                "size": [24, 24],
                "color": "#22c55e",
            },
            dashboard_id="d1",
            space_id="s1",
        )
        assert "layer" in result, result
        layer = result["layer"]
        assert layer["type"] == "icon"
        assert layer["name"] == "trending-up"
        assert layer["color"] == "#22c55e"
        assert layer["anchor"] == "top-right"
        assert layer["size"] == [24, 24]
        # Default placement when none specified
        assert layer["placement"] == "overlay"

    async def test_icon_size_int_normalised_to_pair(self):
        events, result = await execute_tool(
            "build_icon_layer",
            {"name": "star", "size": 32},
            dashboard_id="d1",
            space_id="s1",
        )
        assert result["layer"]["size"] == [32, 32]

    async def test_icon_missing_name_errors(self):
        events, result = await execute_tool(
            "build_icon_layer",
            {"anchor": "top-right"},
            dashboard_id="d1",
            space_id="s1",
        )
        assert "error" in result
        assert "name" in result["error"].lower()

    async def test_icon_invalid_anchor_errors(self):
        events, result = await execute_tool(
            "build_icon_layer",
            {"name": "star", "anchor": "moon"},
            dashboard_id="d1",
            space_id="s1",
        )
        assert "error" in result
        assert "anchor" in result["error"].lower()

    async def test_icon_explicit_placement_wins_over_default(self):
        events, result = await execute_tool(
            "build_icon_layer",
            {"name": "star", "placement": "annotation"},
            dashboard_id="d1",
            space_id="s1",
        )
        assert result["layer"]["placement"] == "annotation"

    async def test_icon_explicit_z_no_placement(self):
        # When the LLM passes z without placement, we honor z (legacy contract).
        events, result = await execute_tool(
            "build_icon_layer",
            {"name": "star", "z": 99},
            dashboard_id="d1",
            space_id="s1",
        )
        layer = result["layer"]
        assert layer["z"] == 99
        # placement should NOT be auto-assigned when z was explicit
        assert "placement" not in layer or layer.get("placement") is None


class TestBuildImageLayerPlacement:
    async def test_image_layer_default_placement_overlay(self, monkeypatch):
        # Stub out DB lookup so we don't need an asset row.
        from app.chat import tools

        class FakeAsset:
            filename = "logo.png"
            tags = ["brand"]

        monkeypatch.setattr(tools, "get_asset", lambda _id: FakeAsset())

        events, result = await execute_tool(
            "build_image_layer",
            {"asset_id": "any", "anchor": "top-right"},
            dashboard_id="d1",
            space_id="s1",
        )
        assert "layer" in result, result
        assert result["layer"]["placement"] == "overlay"

    async def test_image_fill_anchor_defaults_to_background(self, monkeypatch):
        from app.chat import tools

        class FakeAsset:
            filename = "starry.png"
            tags = ["sky", "stars"]

        monkeypatch.setattr(tools, "get_asset", lambda _id: FakeAsset())

        events, result = await execute_tool(
            "build_image_layer",
            {"asset_id": "any", "anchor": "fill"},
            dashboard_id="d1",
            space_id="s1",
        )
        layer = result["layer"]
        assert layer["placement"] == "background"
        # Legacy z fallback is also -1 so old renderers still work
        assert layer["z"] == -1

    async def test_image_explicit_placement_overrides_default(self, monkeypatch):
        from app.chat import tools

        class FakeAsset:
            filename = "x.png"
            tags = []

        monkeypatch.setattr(tools, "get_asset", lambda _id: FakeAsset())

        events, result = await execute_tool(
            "build_image_layer",
            {"asset_id": "any", "anchor": "top-right", "placement": "foreground"},
            dashboard_id="d1",
            space_id="s1",
        )
        assert result["layer"]["placement"] == "foreground"

    async def test_image_explicit_z_only_no_placement(self, monkeypatch):
        from app.chat import tools

        class FakeAsset:
            filename = "x.png"
            tags = []

        monkeypatch.setattr(tools, "get_asset", lambda _id: FakeAsset())

        events, result = await execute_tool(
            "build_image_layer",
            {"asset_id": "any", "anchor": "top-right", "z": 7},
            dashboard_id="d1",
            space_id="s1",
        )
        layer = result["layer"]
        assert layer["z"] == 7
        # Explicit z without placement → placement stays unset (legacy contract)
        assert "placement" not in layer or layer.get("placement") is None
