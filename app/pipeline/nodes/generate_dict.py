import json

from app.llm.client import call_llm_with_retry
from app.llm.vram import ensure_vram_free
from app.models.schemas import DictionaryResponse
from app.models.state import GraphState
from app.pipeline.prompts import DICTIONARY_GENERATION_PROMPT


async def generate_dictionary(state: GraphState) -> GraphState:
    await ensure_vram_free()

    prompt = DICTIONARY_GENERATION_PROMPT.format(
        mapped_headers=json.dumps(state["header_mappings"], indent=2),
        data_profile=json.dumps(state["data_profile"], indent=2),
        sample_rows=json.dumps(state["sample_data"][:5], indent=2, default=str),
    )

    result: DictionaryResponse = await call_llm_with_retry(
        prompt=prompt,
        schema=DictionaryResponse,
    )

    # Merge header mappings with dictionary entries into a unified schema
    columns = []
    for original, mapped in state["header_mappings"].items():
        entry = result.columns.get(mapped, None)
        if entry:
            columns.append({
                "original": original,
                "mapped_name": mapped,
                "sql_type": entry.sql_type,
                "description": entry.description,
                "confidence": entry.confidence,
            })
        else:
            columns.append({
                "original": original,
                "mapped_name": mapped,
                "sql_type": "TEXT",
                "description": "No description generated.",
                "confidence": "LOW",
            })

    state["column_dictionary"] = {"columns": columns}
    return state
