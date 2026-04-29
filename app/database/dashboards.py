import json
from contextvars import ContextVar
from uuid import uuid4

from app.database.connection import get_connection, get_read_connection
from app.models.schemas import Dashboard, Widget, WidgetLayout


# The user message that triggered the current mutation. Set at the top of
# each chat turn by the dashboard agent so widget snapshots carry context.
_CURRENT_USER_MESSAGE: ContextVar[str | None] = ContextVar("user_message", default=None)

# Keep at most this many versions per widget.
MAX_VERSIONS_PER_WIDGET = 30


def set_current_user_message(msg: str | None) -> None:
    _CURRENT_USER_MESSAGE.set(msg)


def _snapshot_widget(
    widget_id: str,
    change_type: str,
    *,
    conn=None,
) -> None:
    """Insert a version row capturing the CURRENT state of `widget_id`.

    Call this AFTER mutating the widget — it reads the live row. The context
    var `_CURRENT_USER_MESSAGE` records which chat prompt drove the change.
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT id, dashboard_id, widget_type, title, config, sql_query, layout
            FROM widgets WHERE id = ?
            """,
            [widget_id],
        ).fetchone()
        if row is None:
            return
        user_msg = _CURRENT_USER_MESSAGE.get()
        config = row[4] if isinstance(row[4], str) else json.dumps(row[4])
        layout = row[6] if isinstance(row[6], str) else json.dumps(row[6])
        conn.execute(
            """
            INSERT INTO widget_versions
                (id, widget_id, dashboard_id, title, widget_type, config, layout, sql_query, change_type, user_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [str(uuid4()), row[0], row[1], row[3], row[2], config, layout, row[5], change_type, user_msg],
        )
        # Prune older versions beyond the cap
        conn.execute(
            """
            DELETE FROM widget_versions
            WHERE widget_id = ? AND id NOT IN (
                SELECT id FROM widget_versions
                WHERE widget_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            )
            """,
            [widget_id, widget_id, MAX_VERSIONS_PER_WIDGET],
        )
    finally:
        if own_conn:
            conn.close()


def list_widget_versions(widget_id: str) -> list[dict]:
    conn = get_read_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, widget_id, dashboard_id, title, widget_type, config, layout,
                   sql_query, change_type, user_message, created_at
            FROM widget_versions WHERE widget_id = ? ORDER BY created_at DESC
            """,
            [widget_id],
        ).fetchall()
        out = []
        for r in rows:
            cfg = r[5]
            lay = r[6]
            if isinstance(cfg, str):
                cfg = json.loads(cfg)
            if isinstance(lay, str):
                lay = json.loads(lay)
            out.append({
                "id": r[0],
                "widget_id": r[1],
                "dashboard_id": r[2],
                "title": r[3],
                "widget_type": r[4],
                "config": cfg,
                "layout": lay,
                "sql_query": r[7],
                "change_type": r[8],
                "user_message": r[9],
                "created_at": str(r[10]),
            })
        return out
    finally:
        conn.close()


def restore_widget_version(version_id: str) -> Widget | None:
    """Restore a widget to the snapshot identified by version_id. Records
    the restore itself as a new version so it can be undone."""
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT widget_id, title, config, layout, sql_query
            FROM widget_versions WHERE id = ?
            """,
            [version_id],
        ).fetchone()
        if row is None:
            return None
        widget_id, title, config, layout, sql_query = row
        if not isinstance(config, str):
            config = json.dumps(config)
        if not isinstance(layout, str):
            layout = json.dumps(layout)

        conn.execute(
            """
            UPDATE widgets
            SET config = ?, layout = ?, title = ?, sql_query = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            [config, layout, title, sql_query, widget_id],
        )
        _snapshot_widget(widget_id, "restored", conn=conn)
    finally:
        conn.close()
    return get_widget(widget_id)


def _row_to_widget(row: tuple) -> Widget:
    config = row[4]
    if isinstance(config, str):
        config = json.loads(config)
    layout = row[6]
    if isinstance(layout, str):
        layout = json.loads(layout)
    return Widget(
        id=row[0],
        dashboard_id=row[1],
        widget_type=row[2],
        title=row[3],
        config=config,
        sql_query=row[5],
        layout=WidgetLayout(**layout),
        created_at=str(row[7]),
        updated_at=str(row[8]),
    )


def create_dashboard(space_id: str, name: str) -> Dashboard:
    dashboard_id = str(uuid4())
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO dashboards (id, space_id, name) VALUES (?, ?, ?)",
            [dashboard_id, space_id, name],
        )
    finally:
        conn.close()
    return get_dashboard(dashboard_id)


def get_dashboard(dashboard_id: str) -> Dashboard | None:
    conn = get_read_connection()
    try:
        row = conn.execute(
            "SELECT id, space_id, name, created_at, updated_at FROM dashboards WHERE id = ?",
            [dashboard_id],
        ).fetchone()
        if row is None:
            return None

        widgets = _list_widgets(conn, dashboard_id)

        return Dashboard(
            id=row[0],
            space_id=row[1],
            name=row[2],
            created_at=str(row[3]),
            updated_at=str(row[4]),
            widgets=widgets,
        )
    finally:
        conn.close()


def list_dashboards(space_id: str) -> list[Dashboard]:
    conn = get_read_connection()
    try:
        rows = conn.execute(
            "SELECT id, space_id, name, created_at, updated_at FROM dashboards WHERE space_id = ? ORDER BY created_at DESC",
            [space_id],
        ).fetchall()
        dashboards = []
        for row in rows:
            widgets = _list_widgets(conn, row[0])
            dashboards.append(Dashboard(
                id=row[0],
                space_id=row[1],
                name=row[2],
                created_at=str(row[3]),
                updated_at=str(row[4]),
                widgets=widgets,
            ))
        return dashboards
    finally:
        conn.close()


def update_dashboard(dashboard_id: str, name: str) -> Dashboard | None:
    dashboard = get_dashboard(dashboard_id)
    if dashboard is None:
        return None

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE dashboards SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [name, dashboard_id],
        )
    finally:
        conn.close()
    return get_dashboard(dashboard_id)


def delete_dashboard(dashboard_id: str) -> bool:
    dashboard = get_dashboard(dashboard_id)
    if dashboard is None:
        return False

    conn = get_connection()
    try:
        conn.execute("DELETE FROM widgets WHERE dashboard_id = ?", [dashboard_id])
        conn.execute("DELETE FROM dashboards WHERE id = ?", [dashboard_id])
        return True
    finally:
        conn.close()


# --- Widget operations ---


def _list_widgets(conn, dashboard_id: str) -> list[Widget]:
    rows = conn.execute(
        """
        SELECT id, dashboard_id, widget_type, title, config, sql_query, layout, created_at, updated_at
        FROM widgets WHERE dashboard_id = ?
        ORDER BY created_at ASC
        """,
        [dashboard_id],
    ).fetchall()
    return [_row_to_widget(r) for r in rows]


def create_widget(
    dashboard_id: str,
    widget_type: str,
    title: str,
    config: dict,
    layout: WidgetLayout,
    sql_query: str | None = None,
) -> Widget:
    widget_id = str(uuid4())
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO widgets (id, dashboard_id, widget_type, title, config, sql_query, layout)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                widget_id,
                dashboard_id,
                widget_type,
                title,
                json.dumps(config),
                sql_query,
                json.dumps(layout.model_dump()),
            ],
        )
        # Update dashboard timestamp
        conn.execute(
            "UPDATE dashboards SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [dashboard_id],
        )
        _snapshot_widget(widget_id, "created", conn=conn)
    finally:
        conn.close()
    return get_widget(widget_id)


def get_widget(widget_id: str) -> Widget | None:
    conn = get_read_connection()
    try:
        row = conn.execute(
            "SELECT id, dashboard_id, widget_type, title, config, sql_query, layout, created_at, updated_at FROM widgets WHERE id = ?",
            [widget_id],
        ).fetchone()
        if row is None:
            return None
        return _row_to_widget(row)
    finally:
        conn.close()


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Deep merge overlay into base. Lists are replaced, dicts are merged recursively."""
    result = {**base}
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def update_widget_config(widget_id: str, config: dict) -> Widget | None:
    widget = get_widget(widget_id)
    if widget is None:
        return None

    merged = _deep_merge(widget.config, config)
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE widgets SET config = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [json.dumps(merged), widget_id],
        )
        _snapshot_widget(widget_id, "updated", conn=conn)
    finally:
        conn.close()
    return get_widget(widget_id)


def update_widget_layout(widget_id: str, layout: WidgetLayout) -> Widget | None:
    """Update a single widget's grid layout (x/y/w/h)."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE widgets SET layout = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [json.dumps(layout.model_dump()), widget_id],
        )
        _snapshot_widget(widget_id, "resized", conn=conn)
    finally:
        conn.close()
    return get_widget(widget_id)


def update_layouts(dashboard_id: str, layouts: dict[str, WidgetLayout]) -> bool:
    conn = get_connection()
    try:
        for widget_id, layout in layouts.items():
            conn.execute(
                "UPDATE widgets SET layout = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND dashboard_id = ?",
                [json.dumps(layout.model_dump()), widget_id, dashboard_id],
            )
        conn.execute(
            "UPDATE dashboards SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [dashboard_id],
        )
        return True
    finally:
        conn.close()


def delete_widget(widget_id: str) -> bool:
    widget = get_widget(widget_id)
    if widget is None:
        return False

    conn = get_connection()
    try:
        conn.execute("DELETE FROM widgets WHERE id = ?", [widget_id])
        return True
    finally:
        conn.close()


def auto_place_widget(dashboard_id: str, width: int = 6, height: int = 2) -> WidgetLayout:
    """Find the next available position in the dashboard grid (12 columns wide)."""
    conn = get_read_connection()
    try:
        rows = conn.execute(
            "SELECT layout FROM widgets WHERE dashboard_id = ?",
            [dashboard_id],
        ).fetchall()

        occupied: set[tuple[int, int]] = set()
        for row in rows:
            layout = row[0]
            if isinstance(layout, str):
                layout = json.loads(layout)
            for dx in range(layout["w"]):
                for dy in range(layout["h"]):
                    occupied.add((layout["x"] + dx, layout["y"] + dy))

        # Scan row by row for a space that fits
        for y in range(100):
            for x in range(12 - width + 1):
                fits = True
                for dx in range(width):
                    for dy in range(height):
                        if (x + dx, y + dy) in occupied:
                            fits = False
                            break
                    if not fits:
                        break
                if fits:
                    return WidgetLayout(x=x, y=y, w=width, h=height)

        # Fallback: place at the bottom
        max_y = max((pos[1] for pos in occupied), default=0) + 1
        return WidgetLayout(x=0, y=max_y, w=width, h=height)
    finally:
        conn.close()
