from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.chat.agent import text_to_sql_with_correction
from app.database.chat_history import clear_chat_history, get_chat_history
from app.database.metadata import get_dataset
from app.database.spaces import get_space
from app.models.schemas import ChatRequest, DashboardChatRequest

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/{dataset_id}/query")
async def query_dataset(dataset_id: str, request: ChatRequest):
    dataset = get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    result = await text_to_sql_with_correction(
        user_question=request.question,
        dataset_id=dataset_id,
    )

    if not result.get("success", False):
        raise HTTPException(
            status_code=422,
            detail={
                "message": result.get("error", "Query generation failed"),
                "last_sql": result.get("last_sql"),
                "last_error": result.get("last_error"),
            },
        )

    return result


@router.post("/spaces/{space_id}/chat/stream")
async def stream_dashboard_chat(space_id: str, request: DashboardChatRequest):
    """SSE streaming endpoint for dashboard-building agent.

    The LLM analyzes the user's question, queries data, and creates
    dashboard widgets. Events stream back in real-time.
    """
    space = get_space(space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="Space not found")

    from app.chat.dashboard_agent import run_dashboard_chat_stream

    return StreamingResponse(
        run_dashboard_chat_stream(
            space_id=space_id,
            user_message=request.message,
            dashboard_id=request.dashboard_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/spaces/{space_id}/history")
async def get_space_chat_history(space_id: str, limit: int = 50):
    space = get_space(space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="Space not found")

    messages = get_chat_history(space_id, limit=limit)
    return {"messages": [m.model_dump() for m in messages]}


@router.delete("/spaces/{space_id}/history")
async def clear_space_chat_history(space_id: str):
    space = get_space(space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="Space not found")

    count = clear_chat_history(space_id)
    return {"status": "cleared", "messages_deleted": count}
