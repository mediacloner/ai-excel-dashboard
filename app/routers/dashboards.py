from fastapi import APIRouter, HTTPException

from app.database.dashboards import (
    create_dashboard,
    create_widget,
    delete_dashboard,
    delete_widget,
    get_dashboard,
    list_dashboards,
    list_widget_versions,
    restore_widget_version,
    update_dashboard,
    update_layouts,
    update_widget_config,
)
from app.database.spaces import get_space
from app.models.schemas import (
    CreateDashboardRequest,
    CreateWidgetRequest,
    UpdateLayoutRequest,
)

router = APIRouter(tags=["dashboards"])


@router.post("/spaces/{space_id}/dashboards")
async def create_new_dashboard(space_id: str, request: CreateDashboardRequest):
    space = get_space(space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="Space not found")

    dashboard = create_dashboard(space_id=space_id, name=request.name)
    return dashboard.model_dump()


@router.get("/spaces/{space_id}/dashboards")
async def get_space_dashboards(space_id: str):
    space = get_space(space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="Space not found")

    dashboards = list_dashboards(space_id)
    return {"dashboards": [d.model_dump() for d in dashboards]}


@router.get("/dashboards/{dashboard_id}")
async def get_dashboard_detail(dashboard_id: str):
    dashboard = get_dashboard(dashboard_id)
    if dashboard is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return dashboard.model_dump()


@router.put("/dashboards/{dashboard_id}")
async def rename_dashboard(dashboard_id: str, request: CreateDashboardRequest):
    dashboard = update_dashboard(dashboard_id, name=request.name)
    if dashboard is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return dashboard.model_dump()


@router.delete("/dashboards/{dashboard_id}")
async def remove_dashboard(dashboard_id: str):
    if not delete_dashboard(dashboard_id):
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return {"status": "deleted", "dashboard_id": dashboard_id}


@router.put("/dashboards/{dashboard_id}/layout")
async def update_dashboard_layout(dashboard_id: str, request: UpdateLayoutRequest):
    dashboard = get_dashboard(dashboard_id)
    if dashboard is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    update_layouts(dashboard_id, request.layouts)
    return {"status": "updated", "dashboard_id": dashboard_id}


@router.post("/dashboards/{dashboard_id}/widgets")
async def add_widget(dashboard_id: str, request: CreateWidgetRequest):
    dashboard = get_dashboard(dashboard_id)
    if dashboard is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    widget = create_widget(
        dashboard_id=dashboard_id,
        widget_type=request.widget_type,
        title=request.title,
        config=request.config,
        layout=request.layout,
        sql_query=request.sql_query,
    )
    return widget.model_dump()


@router.put("/widgets/{widget_id}")
async def update_existing_widget(widget_id: str, config: dict):
    widget = update_widget_config(widget_id, config)
    if widget is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    return widget.model_dump()


@router.delete("/widgets/{widget_id}")
async def remove_widget(widget_id: str):
    if not delete_widget(widget_id):
        raise HTTPException(status_code=404, detail="Widget not found")
    return {"status": "deleted", "widget_id": widget_id}


@router.get("/widgets/{widget_id}/versions")
async def get_widget_versions(widget_id: str):
    versions = list_widget_versions(widget_id)
    return {"versions": versions}


@router.post("/widget-versions/{version_id}/restore")
async def restore_version(version_id: str):
    widget = restore_widget_version(version_id)
    if widget is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return widget.model_dump()
