import pandas as pd

from app.models.state import GraphState


def profile_data(state: GraphState) -> GraphState:
    df: pd.DataFrame = state["dataframe"]
    profile = {}

    for col in df.columns:
        col_profile = {
            "original_name": str(col),
            "total_rows": len(df),
            "null_count": int(df[col].isnull().sum()),
            "null_percentage": round(df[col].isnull().mean() * 100, 1),
            "unique_count": int(df[col].nunique()),
            "unique_percentage": round(df[col].nunique() / max(len(df), 1) * 100, 1),
            "sample_values": [_serialize(v) for v in df[col].dropna().head(5).tolist()],
            "inferred_dtype": str(df[col].dtype),
        }

        # Numeric stats
        if pd.api.types.is_numeric_dtype(df[col]):
            col_profile["min"] = float(df[col].min()) if not df[col].isnull().all() else None
            col_profile["max"] = float(df[col].max()) if not df[col].isnull().all() else None
            col_profile["mean"] = round(float(df[col].mean()), 2) if not df[col].isnull().all() else None
            col_profile["median"] = round(float(df[col].median()), 2) if not df[col].isnull().all() else None

        # String pattern detection
        if df[col].dtype == object:
            sample = df[col].dropna().head(100).astype(str)
            if len(sample) > 0:
                col_profile["avg_length"] = round(sample.str.len().mean(), 1)
                col_profile["max_length"] = int(sample.str.len().max())

                # Detect common patterns
                date_match = sample.str.match(r"\d{4}[-/]\d{2}[-/]\d{2}").mean()
                email_match = sample.str.contains(r"@.*\.", regex=True).mean()

                if date_match > 0.8:
                    col_profile["detected_pattern"] = "DATE"
                elif email_match > 0.8:
                    col_profile["detected_pattern"] = "EMAIL"

        profile[str(col)] = col_profile

    state["data_profile"] = profile
    return state


def _serialize(value):
    """Convert pandas/numpy types to JSON-safe Python types."""
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value
