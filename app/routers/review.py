from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.schemas import SchemaMapping

router = APIRouter(prefix="/review", tags=["review"])


class ApproveRequest(BaseModel):
    approved_schema: SchemaMapping


@router.get("/{file_id}")
async def get_pending_review(file_id: str):
    """Get the schema pending human review for a given upload."""
    from app.pipeline.graph import get_compiled_pipeline

    pipeline = await get_compiled_pipeline()
    thread_config = {"configurable": {"thread_id": file_id}}

    state = await pipeline.aget_state(thread_config)

    if state is None or not state.values:
        raise HTTPException(status_code=404, detail="No pending review found")

    values = state.values
    return {
        "file_id": file_id,
        "status": "awaiting_review",
        "column_dictionary": values.get("column_dictionary"),
        "data_profile": values.get("data_profile"),
        "header_mappings": values.get("header_mappings"),
        "sample_data": values.get("sample_data"),
        "raw_headers": values.get("raw_headers"),
    }


@router.post("/{file_id}/approve")
async def approve_schema(file_id: str, request: ApproveRequest):
    """Approve the schema and resume the pipeline to import data."""
    from app.pipeline.graph import get_compiled_pipeline

    pipeline = await get_compiled_pipeline()
    thread_config = {"configurable": {"thread_id": file_id}}

    # Update state with approved schema and resume
    await pipeline.aupdate_state(
        thread_config,
        {"approved_schema": request.approved_schema.model_dump()},
    )

    # Resume execution (will run import_to_db)
    result = await pipeline.ainvoke(None, config=thread_config)

    return {
        "file_id": file_id,
        "status": "imported",
        "dataset_id": result.get("dataset_id"),
        "table_name": result.get("table_name"),
        "row_count": result.get("row_count"),
        "warnings": result.get("warnings", []),
    }
