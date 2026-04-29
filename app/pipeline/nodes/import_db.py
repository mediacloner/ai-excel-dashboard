import json
import uuid

import duckdb
import pandas as pd

from app.config import get_config
from app.database.metadata import save_dataset_metadata
from app.models.state import GraphState


def import_to_db(state: GraphState) -> GraphState:
    approved = state["approved_schema"]
    df: pd.DataFrame = state["dataframe"]
    warnings = state.get("warnings", [])

    # Apply column renames
    rename_map = {col["original"]: col["mapped_name"] for col in approved["columns"]}
    df = df.rename(columns=rename_map)

    # Apply type conversions
    for col in approved["columns"]:
        mapped = col["mapped_name"]
        sql_type = col["sql_type"]
        try:
            if sql_type == "DATE":
                df[mapped] = pd.to_datetime(df[mapped], errors="coerce")
            elif sql_type == "TIMESTAMP":
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
    config = get_config()
    conn = duckdb.connect(config.database.path)
    try:
        conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")
    finally:
        conn.close()

    # Save metadata
    save_dataset_metadata(
        dataset_id=dataset_id,
        dataset_name=state.get("dataset_name", state["filename"]),
        original_filename=state["filename"],
        column_dictionary=approved,
        table_name=table_name,
        row_count=len(df),
    )

    state["dataset_id"] = dataset_id
    state["table_name"] = table_name
    state["row_count"] = len(df)
    state["warnings"] = warnings

    return state
