import logging
import re

import pandas as pd

from app.config import get_config
from app.database.metadata import get_dataset, get_table_schema
from app.database.connection import get_read_connection
from app.chat.prompts import build_sql_system_prompt
from app.llm.client import call_sql_llm
from app.models.schemas import QueryResult

logger = logging.getLogger(__name__)


def execute_user_query(sql: str) -> QueryResult:
    config = get_config()
    conn = get_read_connection()
    try:
        result = conn.execute(sql).fetchdf()
        truncated = False

        if len(result) > config.database.max_result_rows:
            result = result.head(config.database.max_result_rows)
            truncated = True

        return QueryResult(
            success=True,
            data=result.to_dict(orient="records"),
            row_count=len(result),
            truncated=truncated,
        )
    except Exception as e:
        return QueryResult(success=False, error=str(e))
    finally:
        conn.close()


def _extract_sql(text: str) -> str:
    """Extract SQL from LLM response, stripping markdown fences if present."""
    # Try to find SQL in code blocks
    match = re.search(r"```(?:sql)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _suggest_chart(data: list[dict], columns: list[str]) -> dict | None:
    if not data:
        return None

    df = pd.DataFrame(data)
    text_cols = df.select_dtypes(include=["object"]).columns.tolist()
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()

    if len(text_cols) == 1 and 1 <= len(numeric_cols) <= 3 and len(df) <= 20:
        return {
            "type": "bar",
            "x_axis": text_cols[0],
            "y_axes": numeric_cols,
        }
    elif len(numeric_cols) >= 2 and any("date" in c.lower() for c in df.columns):
        date_col = next(c for c in df.columns if "date" in c.lower())
        return {
            "type": "line",
            "x_axis": date_col,
            "y_axes": [c for c in numeric_cols if "date" not in c.lower()],
        }

    return None


async def text_to_sql_with_correction(
    user_question: str,
    dataset_id: str,
    max_retries: int = 2,
) -> dict:
    metadata = get_dataset(dataset_id)
    if metadata is None:
        return {"success": False, "error": f"Dataset '{dataset_id}' not found."}

    schema_info = get_table_schema(metadata.table_name)
    system_prompt = build_sql_system_prompt(
        table_name=metadata.table_name,
        schema_info=schema_info,
        column_dict=metadata.column_dictionary,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_question},
    ]

    for attempt in range(max_retries + 1):
        raw_response = await call_sql_llm(messages)
        sql = _extract_sql(raw_response)

        result = execute_user_query(sql)

        if result.success:
            chart = _suggest_chart(result.data, list(schema_info.keys()))
            return {
                "success": True,
                "sql": sql,
                "data": result.data,
                "row_count": result.row_count,
                "truncated": result.truncated,
                "chart_suggestion": chart,
                "attempts": attempt + 1,
            }

        # Self-correction: feed the error back
        logger.warning(f"SQL attempt {attempt + 1} failed: {result.error}")
        messages.append({"role": "assistant", "content": sql})
        messages.append({
            "role": "user",
            "content": (
                f"The SQL query failed with this error:\n{result.error}\n\n"
                f"Please fix the query. Remember:\n"
                f"- Table name: {metadata.table_name}\n"
                f"- Available columns: {list(schema_info.keys())}"
            ),
        })

    return {
        "success": False,
        "error": "Could not generate a valid query after multiple attempts.",
        "last_sql": sql,
        "last_error": result.error,
    }
