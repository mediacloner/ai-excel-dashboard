"""Extract every lucide-react icon as a single SVG path-d string.

Reads frontend/node_modules/lucide-react/dist/esm/icons/*.js, parses each
icon's `__iconNode` array, converts every primitive (path/circle/line/rect/
polygon/polyline/ellipse) to an SVG path-d fragment, and emits a single
JSON map `{ "icon-name": "M... M... ..." }` to app/chat/lucide_paths.json.

The result is consumed by echarts_symbols.resolve_aliases at runtime so any
`@<lucide-name>` alias in an ECharts option is rewritten to a real
`path://<d>` symbol — making all ~3,400 lucide icons available as
chart-data-anchored decorations via `markPoint`.

Run from repo root:
    .venv/bin/python scripts/extract_lucide_paths.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ICON_DIR = Path("frontend/node_modules/lucide-react/dist/esm/icons")
OUT = Path("app/chat/lucide_paths.json")

# Each lucide icon file ends with:
#   const __iconNode = [
#     ["path", { d: "...", key: "..." }],
#     ["circle", { cx: "12", cy: "12", r: "10", key: "..." }],
#     ...
#   ];
#   const Foo = createLucideIcon("foo", __iconNode);
NODE_BLOCK = re.compile(r"const __iconNode = \[(.*?)\];", re.DOTALL)
ELEMENT = re.compile(r"\[\s*\"(\w+)\"\s*,\s*\{(.*?)\}\s*\]", re.DOTALL)
ATTR = re.compile(r"(\w+)\s*:\s*\"([^\"]*)\"")
NAME_OF = re.compile(r'createLucideIcon\("([^"]+)"')
# Alias files: `export { default } from './canonical-name.js';`
ALIAS_OF = re.compile(r"from\s+['\"]\./([\w\-]+)\.js['\"]")


def _attrs(blob: str) -> dict[str, str]:
    return dict(ATTR.findall(blob))


def _circle_to_path(a: dict[str, str]) -> str:
    cx, cy, r = float(a["cx"]), float(a["cy"]), float(a["r"])
    # Two half-arcs forming a full circle.
    return (
        f"M{cx - r} {cy}"
        f" a {r} {r} 0 1 0 {2 * r} 0"
        f" a {r} {r} 0 1 0 {-2 * r} 0"
    )


def _ellipse_to_path(a: dict[str, str]) -> str:
    cx, cy = float(a["cx"]), float(a["cy"])
    rx, ry = float(a["rx"]), float(a["ry"])
    return (
        f"M{cx - rx} {cy}"
        f" a {rx} {ry} 0 1 0 {2 * rx} 0"
        f" a {rx} {ry} 0 1 0 {-2 * rx} 0"
    )


def _line_to_path(a: dict[str, str]) -> str:
    return f"M{a['x1']} {a['y1']} L{a['x2']} {a['y2']}"


def _rect_to_path(a: dict[str, str]) -> str:
    x, y = float(a.get("x", 0)), float(a.get("y", 0))
    w, h = float(a["width"]), float(a["height"])
    rx = float(a.get("rx", 0))
    if rx > 0:
        # Rounded rectangle as path with 4 arc corners.
        return (
            f"M{x + rx} {y}"
            f" h{w - 2 * rx} a{rx} {rx} 0 0 1 {rx} {rx}"
            f" v{h - 2 * rx} a{rx} {rx} 0 0 1 -{rx} {rx}"
            f" h-{w - 2 * rx} a{rx} {rx} 0 0 1 -{rx} -{rx}"
            f" v-{h - 2 * rx} a{rx} {rx} 0 0 1 {rx} -{rx} Z"
        )
    return f"M{x} {y} h{w} v{h} h-{w} Z"


def _points_to_path(points: str, close: bool) -> str:
    coords = [c for c in re.split(r"[,\s]+", points.strip()) if c]
    if len(coords) < 4 or len(coords) % 2:
        return ""
    cmds = [f"M{coords[0]} {coords[1]}"]
    for i in range(2, len(coords), 2):
        cmds.append(f"L{coords[i]} {coords[i + 1]}")
    if close:
        cmds.append("Z")
    return " ".join(cmds)


def element_to_path(kind: str, attrs: dict[str, str]) -> str:
    if kind == "path":
        return attrs.get("d", "")
    if kind == "circle":
        return _circle_to_path(attrs)
    if kind == "ellipse":
        return _ellipse_to_path(attrs)
    if kind == "line":
        return _line_to_path(attrs)
    if kind == "rect":
        return _rect_to_path(attrs)
    if kind == "polygon":
        return _points_to_path(attrs.get("points", ""), close=True)
    if kind == "polyline":
        return _points_to_path(attrs.get("points", ""), close=False)
    return ""


def parse_icon_file(text: str) -> tuple[str, str] | None:
    name_m = NAME_OF.search(text)
    block_m = NODE_BLOCK.search(text)
    if not name_m or not block_m:
        return None
    name = name_m.group(1)
    parts: list[str] = []
    for el in ELEMENT.finditer(block_m.group(1)):
        kind, attrs_blob = el.group(1), el.group(2)
        attrs = _attrs(attrs_blob)
        d = element_to_path(kind, attrs)
        if d:
            parts.append(d)
    if not parts:
        return None
    return name, " ".join(parts)


def main() -> None:
    if not ICON_DIR.exists():
        raise SystemExit(f"icon dir not found: {ICON_DIR.resolve()}")
    out: dict[str, str] = {}
    aliases: dict[str, str] = {}  # alias-name → canonical-name
    skipped: list[str] = []
    for f in sorted(ICON_DIR.glob("*.js")):
        if f.name.endswith(".map.js") or "DynamicIcon" in f.name:
            continue
        text = f.read_text(encoding="utf-8")
        parsed = parse_icon_file(text)
        if parsed is None:
            # Maybe it's a pure re-export alias (e.g. alert-circle → circle-alert)
            m = ALIAS_OF.search(text)
            if m:
                aliases[f.stem] = m.group(1)
            else:
                skipped.append(f.name)
            continue
        name, path_d = parsed
        out[name] = path_d

    # Resolve aliases against the canonical map.
    resolved_aliases = 0
    for alias_name, canonical in aliases.items():
        if canonical in out and alias_name not in out:
            out[alias_name] = out[canonical]
            resolved_aliases += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, sort_keys=True, separators=(",", ":")))
    size_kb = OUT.stat().st_size / 1024
    print(f"wrote {len(out)} icons → {OUT} ({size_kb:.0f} KB)")
    print(f"  (canonical: {len(out) - resolved_aliases}, aliases: {resolved_aliases})")
    if skipped:
        print(f"skipped {len(skipped)} files (no icon node, no alias):", skipped[:5])


if __name__ == "__main__":
    main()
