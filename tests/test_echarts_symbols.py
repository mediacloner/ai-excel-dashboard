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


class TestLucideFallback:
    """Aliases not in the hand-curated DECORATION_PATHS should still resolve
    via the auto-extracted lucide_paths.json catalog (1900+ icons)."""

    def test_bike_resolves_via_lucide_fallback(self):
        from app.chat.echarts_symbols import resolve_aliases

        opt = {"symbol": "@bike"}
        out = resolve_aliases(opt)
        assert out["symbol"].startswith("path://"), f"@bike unresolved: {out['symbol']!r}"

    def test_car_resolves_via_lucide_fallback(self):
        from app.chat.echarts_symbols import resolve_aliases

        opt = {"symbol": "@car"}
        out = resolve_aliases(opt)
        assert out["symbol"].startswith("path://")

    def test_bicycle_alias_resolves_to_bike(self):
        """User-friendly synonym: 'bicycle' → 'bike' in lucide."""
        from app.chat.echarts_symbols import resolve_aliases

        bike = resolve_aliases({"s": "@bike"})["s"]
        bicycle = resolve_aliases({"s": "@bicycle"})["s"]
        assert bike == bicycle
        assert bike.startswith("path://")

    def test_lightning_alias_resolves_to_zap(self):
        from app.chat.echarts_symbols import resolve_aliases

        zap = resolve_aliases({"s": "@zap"})["s"]
        lightning = resolve_aliases({"s": "@lightning"})["s"]
        assert zap == lightning

    def test_truly_missing_icon_passes_through(self):
        """A name that isn't in lucide AND isn't an alias stays untouched."""
        from app.chat.echarts_symbols import resolve_aliases

        opt = {"symbol": "@xyznotaicon"}
        assert resolve_aliases(opt)["symbol"] == "@xyznotaicon"

    def test_has_alias_helper(self):
        from app.chat.echarts_symbols import has_alias

        assert has_alias("crown")
        assert has_alias("bike")
        assert has_alias("bicycle")  # via NAME_ALIASES
        assert not has_alias("xyznotaicon")
