"""Schema-level tests for the Layer model.

Exercises the new `icon` type, `placement` field, `name` / `color` fields,
and verifies legacy `z` widgets still parse.
"""

import pytest
from pydantic import ValidationError

from app.models.schemas import Composition, Layer


class TestLayerNewFields:
    def test_icon_layer_parses(self):
        layer = Layer(
            id="icon-1",
            type="icon",
            name="trending-up",
            color="#22c55e",
            anchor="top-right",
            offset=[10, 10],
            size=[20, 20],
            placement="overlay",
        )
        assert layer.type == "icon"
        assert layer.name == "trending-up"
        assert layer.color == "#22c55e"
        assert layer.placement == "overlay"

    def test_placement_accepts_all_five_values(self):
        for p in ("background", "chart", "overlay", "annotation", "foreground"):
            layer = Layer(id=f"l-{p}", type="shape", placement=p)
            assert layer.placement == p

    def test_placement_rejects_unknown_value(self):
        with pytest.raises(ValidationError):
            Layer(id="bad", type="shape", placement="nowhere")

    def test_placement_optional_falls_back_to_z(self):
        layer = Layer(id="legacy", type="image", asset_id="abc", z=-1)
        assert layer.placement is None
        assert layer.z == -1

    def test_icon_type_accepted_in_literal(self):
        # Defensive: if a downstream change ever drops "icon" from the type
        # literal, this fails immediately.
        layer = Layer(id="i", type="icon", name="star")
        assert layer.type == "icon"


class TestLegacyCompat:
    """Widgets stored before this PR have `z` but no `placement`. They
    must continue to deserialize identically — the renderer maps legacy z."""

    def test_legacy_background_z_minus_one_still_valid(self):
        layer = Layer(
            id="bg",
            type="image",
            asset_id="some-uuid",
            anchor="fill",
            z=-1,
        )
        assert layer.z == -1
        assert layer.placement is None

    def test_legacy_logo_z_ten_still_valid(self):
        layer = Layer(
            id="logo",
            type="image",
            asset_id="some-uuid",
            anchor="top-right",
            offset=[10, 10],
            size=[40, 40],
            z=10,
        )
        assert layer.z == 10
        assert layer.placement is None

    def test_composition_with_mixed_legacy_and_new_layers(self):
        comp = Composition(
            canvas={"background": "#0b0b0b"},
            layers=[
                Layer(id="bg", type="image", asset_id="x", anchor="fill", z=-1),
                Layer(id="chart", type="chart", anchor="fill", echarts_option={"series": []}),
                Layer(id="ic", type="icon", name="star", placement="overlay"),
            ],
        )
        assert len(comp.layers) == 3
        assert comp.layers[0].z == -1
        assert comp.layers[2].placement == "overlay"


class TestPlacementSerialisation:
    def test_round_trip_preserves_placement(self):
        original = Layer(id="i", type="icon", name="check", placement="overlay")
        dumped = original.model_dump()
        restored = Layer(**dumped)
        assert restored.placement == "overlay"
        assert restored.name == "check"

    def test_round_trip_preserves_legacy_z(self):
        original = Layer(id="bg", type="svg", markup="<svg/>", anchor="fill", z=-1)
        dumped = original.model_dump()
        restored = Layer(**dumped)
        assert restored.z == -1
        assert restored.placement is None
