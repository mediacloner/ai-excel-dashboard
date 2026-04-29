from pathlib import Path

import pandas as pd

from app.config import get_config
from app.exceptions import FileValidationError
from app.models.state import GraphState


def ingest_excel(state: GraphState) -> GraphState:
    config = get_config()
    file_path = Path(state["file_path"])

    # Validate file extension
    ext = file_path.suffix.lower()
    if ext not in config.ingestion.allowed_extensions:
        raise FileValidationError(
            f"File type '{ext}' not supported. Allowed: {config.ingestion.allowed_extensions}"
        )

    # Validate file size
    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb > config.ingestion.max_file_size_mb:
        raise FileValidationError(
            f"File size ({size_mb:.1f}MB) exceeds limit ({config.ingestion.max_file_size_mb}MB)"
        )

    # Read the file
    if ext == ".csv":
        df = pd.read_csv(file_path)
    else:
        df = pd.read_excel(file_path)

    # Validate dimensions
    if len(df.columns) > config.ingestion.max_columns:
        raise FileValidationError(
            f"Too many columns ({len(df.columns)}). Maximum: {config.ingestion.max_columns}"
        )
    if len(df) > config.ingestion.max_rows:
        raise FileValidationError(
            f"Too many rows ({len(df)}). Maximum: {config.ingestion.max_rows}"
        )

    # Extract sample data
    sample_rows = min(config.ingestion.sample_rows, len(df))
    sample_data = df.head(sample_rows).to_dict(orient="records")

    state["dataframe"] = df
    state["raw_headers"] = list(df.columns)
    state["sample_data"] = sample_data
    state["warnings"] = state.get("warnings", [])

    return state
