"""Tests for the @-alias decoration symbol resolver."""

from app.chat.echarts_symbols import (
    DECORATION_PATHS,
    list_decoration_names,
    resolve_aliases,
)


class TestResolveAliases:
    def test_crown_alias_replaced_with_path(self):
        opt = {"series": [{"markPoint": {"symbol": "@crown"}}]}
        out = resolve_aliases(opt)
        sym = out["series"][0]["markPoint"]["symbol"]
        assert sym.startswith("path://")
        assert DECORATION_PATHS["crown"] in sym

    def test_unknown_alias_passes_through(self):
        opt = {"symbol": "@unicorn"}  # not in registry
        out = resolve_aliases(opt)
        assert out["symbol"] == "@unicorn"

    def test_non_alias_string_unchanged(self):
        opt = {"symbol": "circle", "name": "Approved", "msg": "not @prefix"}
        out = resolve_aliases(opt)
        assert out["symbol"] == "circle"
        assert out["name"] == "Approved"
        assert out["msg"] == "not @prefix"

    def test_alias_with_kebab_case(self):
        opt = {"symbol": "@thumbs-up"}
        out = resolve_aliases(opt)
        assert out["symbol"].startswith("path://")

    def test_aliases_resolved_inside_lists(self):
        opt = {
            "series": [
                {"markPoint": {"symbol": "@crown", "data": [{"type": "max"}]}},
                {"markPoint": {"symbol": "@trophy", "data": [{"type": "min"}]}},
            ]
        }
        out = resolve_aliases(opt)
        assert "path://" in out["series"][0]["markPoint"]["symbol"]
        assert "path://" in out["series"][1]["markPoint"]["symbol"]

    def test_alias_case_insensitive(self):
        opt = {"symbol": "@Crown"}  # capitalised
        out = resolve_aliases(opt)
        assert out["symbol"].startswith("path://")

    def test_no_aliases_returns_equivalent_structure(self):
        opt = {"xAxis": {"type": "category", "data": ["A", "B"]}, "series": [{"type": "bar"}]}
        out = resolve_aliases(opt)
        assert out == opt

    def test_catalog_includes_demo_decorations(self):
        names = list_decoration_names()
        for required in ("crown", "trophy", "star", "flame", "gem", "heart", "medal", "award"):
            assert required in names, f"missing required decoration: {required}"
