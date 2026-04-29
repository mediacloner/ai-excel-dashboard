from typing import Any, TypedDict

import pandas as pd


class GraphState(TypedDict, total=False):
    # Input
    file_path: str
    filename: str
    dataset_name: str

    # Node 1: ingest_excel
    dataframe: pd.DataFrame
    raw_headers: list[str]
    sample_data: list[dict[str, Any]]

    # Node 2a: profile_data
    data_profile: dict[str, Any]

    # Node 2b: map_headers (LLM)
    header_mappings: dict[str, str]

    # Node 2c: generate_dictionary (LLM)
    column_dictionary: dict[str, Any]

    # Node 3: human_review_checkpoint
    approved_schema: dict[str, Any] | None

    # Node 4: import_to_db
    dataset_id: str
    table_name: str
    row_count: int

    # Tracking
    warnings: list[str]
    error: str | None
