"""Tool implementations for the conversational ingestion agent."""

import json
import logging
import time
from pathlib import Path

import pandas as pd

from app.config import get_config
from app.database.dashboards import create_dashboard
from app.database.metadata import save_dataset_metadata
from app.database.spaces import link_dataset
from app.ingestion.analysis import FileAnalysis, analyze_file
from app.llm.client import call_llm_with_retry
from app.llm.vram import ensure_vram_free
from app.models.schemas import DictionaryResponse, HeaderMappingResponse
from app.pipeline.prompts import DICTIONARY_GENERATION_PROMPT, HEADER_MAPPING_PROMPT
from app.pipeline.nodes.profile import profile_data

logger = logging.getLogger(__name__)


async def tool_analyze_file(file_path: str) -> dict:
    """Analyze file structure. Returns the full structural analysis."""
    analysis = analyze_file(file_path)
    return analysis.to_dict()


async def tool_read_sheet(
    file_path: str,
    sheet_name: str = None,
    header_row: int = 0,
    num_rows: int = 10,
) -> dict:
    """Read sample rows from a specific sheet."""
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".csv":
        df = pd.read_csv(str(path), header=header_row, nrows=num_rows)
    else:
        kwargs = {"header": header_row, "nrows": num_rows}
        if sheet_name:
            kwargs["sheet_name"] = sheet_name
        df = pd.read_excel(str(path), **kwargs)

    return {
        "headers": [str(c) for c in df.columns],
        "rows": df.to_dict(orient="records"),
        "row_count": len(df),
        "col_count": len(df.columns),
    }


async def tool_run_schema_mapping(
    file_path: str,
    sheet_name: str | None = None,
    header_row: int = 0,
    columns_to_include: list[str] | None = None,
    user_context: str = "",
) -> dict:
    """Run LLM-powered header mapping and dictionary generation.

    Reuses the existing pipeline logic but with user-provided context.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    # Read the data
    if ext == ".csv":
        df = pd.read_csv(str(path), header=header_row)
    else:
        kwargs = {"header": header_row}
        if sheet_name:
            kwargs["sheet_name"] = sheet_name
        df = pd.read_excel(str(path), **kwargs)

    # Filter columns if specified
    if columns_to_include:
        existing = [c for c in columns_to_include if c in df.columns]
        if existing:
            df = df[existing]

    # Profile the data (reuse existing profiling)
    state = {
        "dataframe": df,
        "raw_headers": [str(c) for c in df.columns],
        "sample_data": df.head(10).to_dict(orient="records"),
        "warnings": [],
    }
    state = profile_data(state)

    # Header mapping with user context
    await ensure_vram_free()

    header_prompt = HEADER_MAPPING_PROMPT.format(
        data_profile=json.dumps(state["data_profile"], indent=2),
    )
    if user_context:
        header_prompt += f"\n\nAdditional context from the user about this data:\n{user_context}"

    header_result: HeaderMappingResponse = await call_llm_with_retry(
        prompt=header_prompt,
        schema=HeaderMappingResponse,
    )

    # Dictionary generation with user context
    await ensure_vram_free()

    dict_prompt = DICTIONARY_GENERATION_PROMPT.format(
        mapped_headers=json.dumps(header_result.mappings, indent=2),
        data_profile=json.dumps(state["data_profile"], indent=2),
        sample_rows=json.dumps(state["sample_data"][:5], indent=2, default=str),
    )
    if user_context:
        dict_prompt += f"\n\nAdditional context from the user about this data:\n{user_context}"

    dict_result: DictionaryResponse = await call_llm_with_retry(
        prompt=dict_prompt,
        schema=DictionaryResponse,
    )

    # Merge into unified schema
    columns = []
    for original, mapped in header_result.mappings.items():
        entry = dict_result.columns.get(mapped)
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

    return {"columns": columns}


async def tool_import_dataset(
    file_path: str,
    sheet_name: str | None,
    header_row: int,
    approved_schema: dict,
    dataset_name: str,
    space_id: str,
    business_context: str = "",
) -> dict:
    """Import the data into DuckDB using the approved schema.

    Reuses the existing import_to_db logic.
    """
    import uuid
    import duckdb

    path = Path(file_path)
    ext = path.suffix.lower()
    config = get_config()

    # Read the data
    if ext == ".csv":
        df = pd.read_csv(str(path), header=header_row)
    else:
        kwargs = {"header": header_row}
        if sheet_name:
            kwargs["sheet_name"] = sheet_name
        df = pd.read_excel(str(path), **kwargs)

    warnings = []

    # Apply column renames
    rename_map = {col["original"]: col["mapped_name"] for col in approved_schema["columns"]}
    df = df.rename(columns=rename_map)

    # Apply type conversions
    for col in approved_schema["columns"]:
        mapped = col["mapped_name"]
        sql_type = col["sql_type"]
        try:
            if sql_type in ("DATE", "TIMESTAMP"):
                df[mapped] = pd.to_datetime(df[mapped], errors="coerce")
            elif sql_type == "INTEGER":
                df[mapped] = pd.to_numeric(df[mapped], errors="coerce").astype("Int64")
            elif sql_type == "FLOAT":
                df[mapped] = pd.to_numeric(df[mapped], errors="coerce")
            elif sql_type == "BOOLEAN":
                bool_map = {
                    "true": True, "false": False,
                    "yes": True, "no": False,
                    "1": True, "0": False,
                    "y": True, "n": False,
                }
                df[mapped] = df[mapped].astype(str).str.lower().map(bool_map)
        except Exception as e:
            warnings.append(f"Type conversion failed for {mapped}: {e}")

    # Generate table identifiers
    dataset_id = str(uuid.uuid4())
    table_name = f"dataset_{dataset_id.replace('-', '_')}"

    # Write to DuckDB
    conn = duckdb.connect(config.database.path)
    try:
        conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")
    finally:
        conn.close()

    # Save metadata with business context from user's ingestion Q&A
    save_dataset_metadata(
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        original_filename=Path(file_path).name,
        column_dictionary=approved_schema,
        table_name=table_name,
        row_count=len(df),
        business_context=business_context,
    )

    # Link to space
    link_dataset(space_id, dataset_id)

    return {
        "dataset_id": dataset_id,
        "table_name": table_name,
        "row_count": len(df),
        "warnings": warnings,
    }


# Tool registry for the agent
INGESTION_TOOLS = {
    "analyze_file": tool_analyze_file,
    "read_sheet": tool_read_sheet,
    "run_schema_mapping": tool_run_schema_mapping,
    "import_dataset": tool_import_dataset,
    # "ask_user" and "present_schema_review" are handled specially by the agent (they produce SSE events, not tool results)
}
