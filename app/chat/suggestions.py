def generate_suggested_questions(
    column_dict: dict,
    schema_info: dict[str, str],
) -> list[str]:
    suggestions = []

    # Categorise columns by type
    numeric_cols = [c for c, dtype in schema_info.items() if dtype in ("FLOAT", "INTEGER", "BIGINT", "DOUBLE", "Int64")]
    date_cols = [c for c, dtype in schema_info.items() if "DATE" in dtype.upper() or "TIMESTAMP" in dtype.upper()]
    text_cols = [c for c, dtype in schema_info.items() if "VARCHAR" in dtype.upper() or "TEXT" in dtype.upper()]

    if numeric_cols and text_cols:
        suggestions.append(f"What is the average {numeric_cols[0]} by {text_cols[0]}?")

    if text_cols:
        suggestions.append(f"How many records are there per {text_cols[0]}?")

    if date_cols and numeric_cols:
        suggestions.append(f"Show the trend of {numeric_cols[0]} over time by {date_cols[0]}")

    if numeric_cols:
        suggestions.append(f"What are the top 10 records by {numeric_cols[0]}?")

    if numeric_cols:
        suggestions.append(f"Show the distribution of {numeric_cols[0]}")

    return suggestions[:5]
