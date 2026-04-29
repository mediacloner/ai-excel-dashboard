import json

from app.llm.client import call_llm_with_retry
from app.llm.vram import ensure_vram_free
from app.models.schemas import HeaderMappingResponse
from app.models.state import GraphState
from app.pipeline.prompts import HEADER_MAPPING_PROMPT


async def map_headers(state: GraphState) -> GraphState:
    await ensure_vram_free()

    prompt = HEADER_MAPPING_PROMPT.format(
        data_profile=json.dumps(state["data_profile"], indent=2),
    )

    result: HeaderMappingResponse = await call_llm_with_retry(
        prompt=prompt,
        schema=HeaderMappingResponse,
    )

    state["header_mappings"] = result.mappings
    return state
