from app.pipeline.prompts import SQL_SYSTEM_PROMPT


def build_sql_system_prompt(
    table_name: str,
    schema_info: dict[str, str],
    column_dict: dict,
) -> str:
    schema_lines = "\n".join(
        f"  - {name} ({dtype})" for name, dtype in schema_info.items()
    )

    dict_lines = []
    if "columns" in column_dict:
        for col in column_dict["columns"]:
            dict_lines.append(
                f"  - {col['mapped_name']}: {col.get('description', 'No description')}"
            )
    dict_str = "\n".join(dict_lines) if dict_lines else "No dictionary available."

    return SQL_SYSTEM_PROMPT.format(
        table_name=table_name,
        schema_info=schema_lines,
        column_dict=dict_str,
    )
