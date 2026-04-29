import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_config
from app.exceptions import FileValidationError
from app.pipeline.nodes.ingest import ingest_excel
from app.pipeline.nodes.profile import profile_data

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("")
async def upload_file(file: UploadFile, dataset_name: str | None = None, space_id: str | None = None):
    config = get_config()

    # Validate extension
    ext = Path(file.filename).suffix.lower()
    if ext not in config.ingestion.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not supported. Allowed: {config.ingestion.allowed_extensions}",
        )

    # Save file to disk
    upload_dir = Path(config.ingestion.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = str(uuid.uuid4())
    save_path = upload_dir / f"{file_id}{ext}"

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Read + validate + profile
    try:
        state = {
            "file_path": str(save_path),
            "filename": file.filename,
            "dataset_name": dataset_name or Path(file.filename).stem,
        }
        state = ingest_excel(state)
        state = profile_data(state)
    except FileValidationError as e:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e))

    # Quick import: read ALL sheets, concat, write to DuckDB
    import duckdb
    import pandas as pd
    from app.database.metadata import save_dataset_metadata
    from app.database.spaces import link_dataset

    ext = save_path.suffix.lower()
    name = state["dataset_name"]
    total_rows = 0
    created_tables = []

    # Read all sheets for Excel files
    if ext in (".xlsx", ".xls"):
        all_sheets = pd.read_excel(str(save_path), sheet_name=None)  # dict of {sheet_name: df}
    else:
        all_sheets = {"Sheet1": state["dataframe"]}

    for sheet_name, df in all_sheets.items():
        if df.empty:
            continue

        ds_id = str(uuid.uuid4())
        sheet_label = sheet_name if len(all_sheets) > 1 else name
        table_name = f"dataset_{ds_id.replace('-', '_')}"

        # Build column dictionary from dtypes
        columns = []
        for col in df.columns:
            col_str = str(col)
            dtype = str(df[col].dtype)
            if "int" in dtype:
                sql_type = "INTEGER"
            elif "float" in dtype:
                sql_type = "FLOAT"
            elif "datetime" in dtype:
                sql_type = "TIMESTAMP"
            elif "bool" in dtype:
                sql_type = "BOOLEAN"
            else:
                sql_type = "TEXT"
            columns.append({
                "original": col_str,
                "mapped_name": col_str.lower().replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "")[:30],
                "sql_type": sql_type,
                "description": col_str,
                "confidence": "LOW",
            })

        # Rename columns to safe names
        rename_map = {c["original"]: c["mapped_name"] for c in columns}
        df_import = df.rename(columns=rename_map)

        conn = duckdb.connect(config.database.path)
        try:
            conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df_import")
        finally:
            conn.close()

        save_dataset_metadata(
            dataset_id=ds_id,
            dataset_name=sheet_label,
            original_filename=file.filename,
            column_dictionary={"columns": columns},
            table_name=table_name,
            row_count=len(df),
        )

        if space_id:
            link_dataset(space_id, ds_id)

        total_rows += len(df)
        created_tables.append({
            "dataset_id": ds_id,
            "sheet_name": sheet_name,
            "table_name": table_name,
            "row_count": len(df),
            "column_count": len(df.columns),
        })

    return {
        "file_id": file_id,
        "filename": file.filename,
        "dataset_name": name,
        "sheets_imported": len(created_tables),
        "datasets": created_tables,
        "row_count": total_rows,
        "column_count": max((t["column_count"] for t in created_tables), default=0),
    }


@router.post("/{file_id}/analyze")
async def analyze_file(file_id: str):
    """Trigger LLM analysis (header mapping + dictionary generation) for an uploaded file."""
    config = get_config()
    upload_dir = Path(config.ingestion.upload_dir)

    # Find the uploaded file
    matches = list(upload_dir.glob(f"{file_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="Upload not found")

    save_path = matches[0]

    # Run full pipeline up to human review checkpoint
    from app.pipeline.graph import get_compiled_pipeline

    pipeline = await get_compiled_pipeline()

    initial_state = {
        "file_path": str(save_path),
        "filename": save_path.name,
        "dataset_name": save_path.stem,
    }

    thread_config = {"configurable": {"thread_id": file_id}}

    # Run until interrupt (before import_to_db)
    result = await pipeline.ainvoke(initial_state, config=thread_config)

    return {
        "file_id": file_id,
        "status": "awaiting_review",
        "column_dictionary": result.get("column_dictionary"),
        "data_profile": result.get("data_profile"),
        "header_mappings": result.get("header_mappings"),
    }


# --- Conversational ingestion (SSE) ---


@router.post("/ingest/start")
async def start_conversational_ingestion(
    file: UploadFile,
    space_id: str,
    dataset_name: str | None = None,
):
    """Upload a file and start conversational ingestion via SSE.

    The LLM analyzes the file, asks clarifying questions if needed,
    and streams events back to the client.
    """
    config = get_config()

    ext = Path(file.filename).suffix.lower()
    if ext not in config.ingestion.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not supported.",
        )

    # Validate space exists
    from app.database.spaces import get_space
    space = get_space(space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="Space not found")

    # Save file
    upload_dir = Path(config.ingestion.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid.uuid4())
    save_path = upload_dir / f"{file_id}{ext}"

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    name = dataset_name or Path(file.filename).stem

    from app.ingestion.agent import run_ingestion_stream

    return StreamingResponse(
        run_ingestion_stream(
            file_path=str(save_path),
            space_id=space_id,
            dataset_name=name,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


class IngestionAnswerRequest(BaseModel):
    answer: str
    file_path: str
    space_id: str
    dataset_name: str
    conversation_history: list[dict] = []
    sheet_name: str | None = None
    header_row: int = 0


@router.post("/ingest/answer")
async def answer_ingestion_question(request: IngestionAnswerRequest):
    """Continue conversational ingestion after the user answers a question."""
    from app.ingestion.agent import continue_ingestion_stream

    return StreamingResponse(
        continue_ingestion_stream(
            file_path=request.file_path,
            space_id=request.space_id,
            dataset_name=request.dataset_name,
            user_answer=request.answer,
            conversation_history=request.conversation_history,
            sheet_name=request.sheet_name,
            header_row=request.header_row,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


class IngestionApproveRequest(BaseModel):
    file_path: str
    space_id: str
    dataset_name: str
    approved_schema: dict
    sheet_name: str | None = None
    header_row: int = 0
    business_context: str = ""


@router.post("/ingest/approve")
async def approve_and_import(request: IngestionApproveRequest):
    """Approve schema and import the dataset."""
    from app.ingestion.agent import run_direct_import

    return StreamingResponse(
        run_direct_import(
            file_path=request.file_path,
            space_id=request.space_id,
            dataset_name=request.dataset_name,
            approved_schema=request.approved_schema,
            sheet_name=request.sheet_name,
            header_row=request.header_row,
            business_context=request.business_context,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
