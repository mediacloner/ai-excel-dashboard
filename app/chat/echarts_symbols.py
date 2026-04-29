"""ECharts decoration symbol registry.

Maps short alias names (`@crown`, `@trophy`, …) to ECharts-compatible
`path://<d-string>` symbol values. The path data is taken from lucide v1.8
(MIT-licensed). Multi-path icons are joined into one `d` string — each
path's leading `M` command starts a new subpath, which ECharts honors.

Resolution: `resolve_aliases(option)` walks an `echarts_option` dict
and replaces any string of the form `"@<name>"` with `"path://<d>"`.
This lets the LLM (or any author) write `markPoint: {symbol: "@crown"}`
without copying ~200 chars of path data.

The catalog is intentionally small — we expose only "decoration-grade"
named icons (medals, stars, flames, gems, hearts, …). Adding more is
trivial: drop another `(name, d)` pair into DECORATION_PATHS.
"""

from typing import Any

# Each value is a single SVG path `d` string, viewBox 0 0 24 24 (lucide's).
# When an icon has multiple subpaths in lucide, they're concatenated with a
# space — every subpath starts with M, so ECharts renders them as separate
# strokes within one symbol.
DECORATION_PATHS: dict[str, str] = {
    "crown": (
        "M11.562 3.266a.5.5 0 0 1 .876 0L15.39 8.87a1 1 0 0 0 1.516.294"
        "L21.183 5.5a.5.5 0 0 1 .798.519l-2.834 10.246a1 1 0 0 1-.956.734"
        "H5.81a1 1 0 0 1-.957-.734L2.02 6.02a.5.5 0 0 1 .798-.519l4.276 3.664"
        "a1 1 0 0 0 1.516-.294z M5 21h14"
    ),
    "trophy": (
        "M10 14.66v1.626a2 2 0 0 1-.976 1.696A5 5 0 0 0 7 21.978 "
        "M14 14.66v1.626a2 2 0 0 0 .976 1.696A5 5 0 0 1 17 21.978 "
        "M18 9h1.5a1 1 0 0 0 0-5H18 M4 22h16 "
        "M6 9a6 6 0 0 0 12 0V3a1 1 0 0 0-1-1H7a1 1 0 0 0-1 1z "
        "M6 9H4.5a1 1 0 0 1 0-5H6"
    ),
    "award": (
        "M15.477 12.89 17 22l-5-3-5 3 1.523-9.11 "
        "M12 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12z"
    ),
    "medal": (
        "M7.21 15 2.66 7.14a2 2 0 0 1 .13-2.2L4.4 2.8A2 2 0 0 1 6 2h12a2 2 0 0 1 1.6.8l1.6 2.14a2 2 0 0 1 .14 2.2L16.79 15 "
        "M11 12 5.12 2.2 M13 12l5.88-9.8 M8 7h8 "
        "M12 17a5 5 0 1 0 0 10 5 5 0 0 0 0-10z"
    ),
    "star": (
        "M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"
    ),
    "sparkles": (
        "M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z "
        "M20 2v4 M22 4h-4 M4 17v2 M5 18H3"
    ),
    "flame": (
        "M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"
    ),
    "gem": (
        "M6 3h12l4 6-10 13L2 9z M11 3 8 9l4 13 4-13-3-6 M2 9h20"
    ),
    "heart": (
        "M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.29 1.51 4.04 3 5.5l7 7Z"
    ),
    "zap": (
        "M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"
    ),
    "rocket": (
        "M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z "
        "M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z "
        "M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0 "
        "M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"
    ),
    "target": (
        "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z "
        "M12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12z "
        "M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4z"
    ),
    "diamond": (
        "M2.7 10.3a2.41 2.41 0 0 0 0 3.41l7.59 7.59a2.41 2.41 0 0 0 3.41 0l7.59-7.59a2.41 2.41 0 0 0 0-3.41l-7.59-7.59a2.41 2.41 0 0 0-3.41 0Z"
    ),
    "thumbs-up": (
        "M7 10v12 M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88z"
    ),
    "party-popper": (
        "M5.8 11.3 2 22l10.7-3.79 "
        "M4 3h.01 M22 8h.01 M15 2h.01 M22 20h.01 "
        "M22 2l-2.24.75a2.9 2.9 0 0 0-1.96 3.12c.1.86-.57 1.63-1.45 1.63h-.38c-.86 0-1.6.6-1.76 1.44L14 10 "
        "M22 13.99l-.78-.78a2.91 2.91 0 0 0-4.12 0l-.51.51a2.91 2.91 0 0 1-4.12 0L8.4 9.7a2.91 2.91 0 0 1 0-4.12l.51-.51a2.91 2.91 0 0 0 0-4.12L8.13.17 "
        "M11 13l1.5-1.5"
    ),
}


def resolve_aliases(node: Any) -> Any:
    """Walk an arbitrary nested structure and replace `@<name>` strings
    (only when the name is a known decoration) with `path://<d>` strings.

    Mutates dicts/lists in place; returns the same node for convenience.
    Strings that aren't `@<name>` aliases pass through unchanged.
    """
    if isinstance(node, dict):
        for k, v in list(node.items()):
            node[k] = resolve_aliases(v)
        return node
    if isinstance(node, list):
        for i, v in enumerate(node):
            node[i] = resolve_aliases(v)
        return node
    if isinstance(node, str) and node.startswith("@"):
        name = node[1:].strip().lower()
        if name in DECORATION_PATHS:
            return f"path://{DECORATION_PATHS[name]}"
    return node


def list_decoration_names() -> list[str]:
    """Sorted catalog for prompt construction."""
    return sorted(DECORATION_PATHS.keys())
