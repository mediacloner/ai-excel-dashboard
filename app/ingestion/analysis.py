"""Pure-Python structural analysis of Excel/CSV files.

Detects ambiguities that the LLM should ask the user about before ingestion.
No LLM calls here — this is deterministic analysis only.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class SheetInfo:
    name: str
    row_count: int
    col_count: int
    has_data: bool


@dataclass
class MergedRegion:
    sheet: str
    range: str
    top_left_value: str | None


@dataclass
class ColumnIssue:
    column: str
    issue_type: str  # "high_null", "mixed_types", "date_ambiguity", "duplicate_name", "cryptic_name", "coded_values"
    detail: str
    sample_values: list = field(default_factory=list)


@dataclass
class FileAnalysis:
    """Complete structural analysis of an uploaded file."""
    file_path: str
    file_name: str
    file_size_mb: float
    file_type: str  # "xlsx", "xls", "csv"

    # Sheet info
    sheets: list[SheetInfo] = field(default_factory=list)
    multiple_sheets: bool = False

    # Structural issues
    merged_cells: list[MergedRegion] = field(default_factory=list)
    has_merged_cells: bool = False
    likely_header_row: int = 0  # 0-indexed
    has_title_row: bool = False  # row 0 looks like a title, not headers
    empty_columns: list[str] = field(default_factory=list)
    high_null_columns: list[str] = field(default_factory=list)

    # Column-level issues
    column_issues: list[ColumnIssue] = field(default_factory=list)

    # Data preview
    raw_headers: list[str] = field(default_factory=list)
    sample_rows: list[dict] = field(default_factory=list)
    total_rows: int = 0
    total_columns: int = 0

    @property
    def has_ambiguities(self) -> bool:
        return (
            self.multiple_sheets
            or self.has_merged_cells
            or self.has_title_row
            or len(self.empty_columns) > 0
            or len(self.column_issues) > 0
        )

    def to_dict(self) -> dict:
        return {
            "file_name": self.file_name,
            "file_size_mb": self.file_size_mb,
            "file_type": self.file_type,
            "sheets": [{"name": s.name, "rows": s.row_count, "cols": s.col_count, "has_data": s.has_data} for s in self.sheets],
            "multiple_sheets": self.multiple_sheets,
            "has_merged_cells": self.has_merged_cells,
            "merged_cells": [{"sheet": m.sheet, "range": m.range, "value": m.top_left_value} for m in self.merged_cells],
            "likely_header_row": self.likely_header_row,
            "has_title_row": self.has_title_row,
            "empty_columns": self.empty_columns,
            "high_null_columns": self.high_null_columns,
            "column_issues": [
                {"column": ci.column, "issue_type": ci.issue_type, "detail": ci.detail, "sample_values": ci.sample_values}
                for ci in self.column_issues
            ],
            "raw_headers": self.raw_headers,
            "sample_rows": self.sample_rows,
            "total_rows": self.total_rows,
            "total_columns": self.total_columns,
            "has_ambiguities": self.has_ambiguities,
        }


def analyze_file(file_path: str) -> FileAnalysis:
    """Run full structural analysis on an Excel/CSV file."""
    path = Path(file_path)
    ext = path.suffix.lower()
    analysis = FileAnalysis(
        file_path=file_path,
        file_name=path.name,
        file_size_mb=round(path.stat().st_size / (1024 * 1024), 2),
        file_type=ext.lstrip("."),
    )

    if ext == ".csv":
        _analyze_csv(path, analysis)
    else:
        _analyze_excel(path, analysis)

    return analysis


def _analyze_excel(path: Path, analysis: FileAnalysis) -> None:
    """Analyze an Excel file using openpyxl for structure + pandas for data."""
    import openpyxl

    wb = openpyxl.load_workbook(str(path), read_only=False, data_only=True)

    # Sheet analysis
    for name in wb.sheetnames:
        ws = wb[name]
        row_count = ws.max_row or 0
        col_count = ws.max_column or 0
        has_data = row_count > 1 and col_count > 0
        analysis.sheets.append(SheetInfo(name=name, row_count=row_count, col_count=col_count, has_data=has_data))

    data_sheets = [s for s in analysis.sheets if s.has_data]
    analysis.multiple_sheets = len(data_sheets) > 1

    # Merged cells detection (check all sheets)
    for name in wb.sheetnames:
        ws = wb[name]
        for merged_range in ws.merged_cells.ranges:
            top_left = ws.cell(merged_range.min_row, merged_range.min_col).value
            analysis.merged_cells.append(MergedRegion(
                sheet=name,
                range=str(merged_range),
                top_left_value=str(top_left) if top_left is not None else None,
            ))
    analysis.has_merged_cells = len(analysis.merged_cells) > 0

    wb.close()

    # Use first data sheet for detailed analysis
    target_sheet = data_sheets[0].name if data_sheets else wb.sheetnames[0]

    # Read with pandas for data analysis
    df = pd.read_excel(str(path), sheet_name=target_sheet, header=None, nrows=20)
    _detect_header_row(df, analysis)

    # Re-read with proper header
    df_full = pd.read_excel(str(path), sheet_name=target_sheet, header=analysis.likely_header_row)
    _analyze_dataframe(df_full, analysis)


def _analyze_csv(path: Path, analysis: FileAnalysis) -> None:
    """Analyze a CSV file."""
    analysis.sheets = [SheetInfo(name="Sheet1", row_count=0, col_count=0, has_data=True)]

    # Read a small sample without headers first to detect header row
    df_raw = pd.read_csv(str(path), header=None, nrows=20)
    _detect_header_row(df_raw, analysis)

    # Re-read with proper header
    df_full = pd.read_csv(str(path), header=analysis.likely_header_row)
    analysis.sheets[0].row_count = len(df_full)
    analysis.sheets[0].col_count = len(df_full.columns)
    _analyze_dataframe(df_full, analysis)


def _detect_header_row(df_raw: pd.DataFrame, analysis: FileAnalysis) -> None:
    """Detect if row 0 is a title vs actual headers.

    Heuristics:
    - If row 0 has very few non-null values (1-2) and row 1+ has many, row 0 is likely a title
    - If row 0 values are all strings and short, it's likely headers
    - If row 0 has a single cell spanning context (detected via merged cells), it's a title
    """
    if len(df_raw) < 2:
        return

    row0_non_null = df_raw.iloc[0].dropna()
    row1_non_null = df_raw.iloc[1].dropna() if len(df_raw) > 1 else pd.Series()

    # Row 0 has very few values compared to row 1 -> likely a title
    if len(row0_non_null) <= 2 and len(row1_non_null) > len(row0_non_null) + 2:
        analysis.has_title_row = True
        # Check if row 1 looks like headers (string-like, short values)
        if len(df_raw) > 2:
            row2_non_null = df_raw.iloc[2].dropna()
            # Row 1 has strings, row 2 has diverse types -> row 1 is header
            analysis.likely_header_row = 1
            return

    # Check if row 0 looks like a title (single merged text, all-caps, etc.)
    if len(row0_non_null) == 1:
        val = str(row0_non_null.iloc[0])
        if len(val) > 30 or val.isupper():
            analysis.has_title_row = True
            analysis.likely_header_row = 1
            return

    analysis.likely_header_row = 0


def _analyze_dataframe(df: pd.DataFrame, analysis: FileAnalysis) -> None:
    """Analyze column-level issues in the dataframe."""
    analysis.raw_headers = [str(c) for c in df.columns]
    analysis.total_rows = len(df)
    analysis.total_columns = len(df.columns)
    analysis.sample_rows = df.head(10).to_dict(orient="records")

    # Serialize sample rows for JSON safety
    analysis.sample_rows = [
        {k: _safe_serialize(v) for k, v in row.items()}
        for row in analysis.sample_rows
    ]

    for col in df.columns:
        col_str = str(col)
        series = df[col]

        # High null detection (>70% null)
        null_pct = series.isnull().mean()
        if null_pct > 0.7:
            analysis.high_null_columns.append(col_str)
            analysis.column_issues.append(ColumnIssue(
                column=col_str,
                issue_type="high_null",
                detail=f"{null_pct:.0%} of values are null/empty",
                sample_values=_get_sample(series),
            ))

        # Fully empty columns (>95% null)
        if null_pct > 0.95:
            analysis.empty_columns.append(col_str)

        # Mixed type detection
        non_null = series.dropna()
        if len(non_null) > 0 and series.dtype == object:
            types = non_null.apply(type).value_counts()
            if len(types) > 1:
                # Check if there's a meaningful mix (not just str vs str)
                numeric_count = non_null.apply(lambda x: _is_numeric_like(x)).sum()
                if 0.1 < numeric_count / len(non_null) < 0.9:
                    analysis.column_issues.append(ColumnIssue(
                        column=col_str,
                        issue_type="mixed_types",
                        detail=f"Contains both numeric and text values ({numeric_count}/{len(non_null)} look numeric)",
                        sample_values=_get_sample(series),
                    ))

        # Date ambiguity (MM/DD vs DD/MM)
        if series.dtype == object:
            sample = non_null.head(100).astype(str)
            date_pattern = sample.str.match(r"^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}$")
            if date_pattern.mean() > 0.5:
                # Check if day/month are ambiguous
                ambiguous = _check_date_ambiguity(sample[date_pattern])
                if ambiguous:
                    analysis.column_issues.append(ColumnIssue(
                        column=col_str,
                        issue_type="date_ambiguity",
                        detail="Date format is ambiguous — could be MM/DD or DD/MM",
                        sample_values=_get_sample(series, n=5),
                    ))

        # Cryptic column names
        if _is_cryptic_name(col_str):
            analysis.column_issues.append(ColumnIssue(
                column=col_str,
                issue_type="cryptic_name",
                detail=f"Column name '{col_str}' is not self-explanatory",
                sample_values=_get_sample(series),
            ))

        # Coded/enum values (small set of short values)
        if series.dtype == object and len(non_null) > 10:
            unique_count = series.nunique()
            if 2 <= unique_count <= 10:
                unique_vals = series.dropna().unique().tolist()[:10]
                avg_len = sum(len(str(v)) for v in unique_vals) / max(len(unique_vals), 1)
                if avg_len <= 5:
                    analysis.column_issues.append(ColumnIssue(
                        column=col_str,
                        issue_type="coded_values",
                        detail=f"Contains {unique_count} short coded values",
                        sample_values=[str(v) for v in unique_vals],
                    ))

    # Duplicate-looking column names
    seen = {}
    for col in analysis.raw_headers:
        normalized = re.sub(r"[^a-z0-9]", "", col.lower())
        if normalized in seen:
            analysis.column_issues.append(ColumnIssue(
                column=col,
                issue_type="duplicate_name",
                detail=f"Column '{col}' looks similar to '{seen[normalized]}'",
            ))
        seen[normalized] = col

    # Potential column relationships (e.g., "id" + "name" pairs)
    _detect_relationships(df, analysis)


def _detect_relationships(df: pd.DataFrame, analysis: FileAnalysis) -> None:
    """Detect potential relationships between columns."""
    cols = [str(c).lower() for c in df.columns]
    col_map = {c.lower(): str(c) for c in df.columns}

    # Look for id/name pairs
    for i, c1 in enumerate(cols):
        for j, c2 in enumerate(cols):
            if i >= j:
                continue
            # Pattern: xxx_id + xxx_name or xxx_code + xxx_description
            base1 = re.sub(r"(_id|_code|_key|_no|_num)$", "", c1)
            base2 = re.sub(r"(_name|_desc|_description|_label|_text)$", "", c2)
            if base1 and base1 == base2 and c1 != c2:
                analysis.column_issues.append(ColumnIssue(
                    column=col_map.get(c1, c1),
                    issue_type="potential_relationship",
                    detail=f"'{col_map.get(c1, c1)}' may be the key/code for '{col_map.get(c2, c2)}'",
                ))


def _is_cryptic_name(name: str) -> bool:
    """Check if a column name is cryptic (short abbreviations, coded names)."""
    name_clean = name.strip()
    # Single character or very short without vowels
    if len(name_clean) <= 2:
        return True
    # Looks like a code: all caps + numbers, or starts with common code prefixes
    if re.match(r"^[A-Z]{2,4}\d+$", name_clean):
        return True
    if re.match(r"^(FLD|COL|COD|VAR|TMP|F|C)_?[A-Z0-9]+$", name_clean, re.IGNORECASE):
        return True
    # Unnamed/generic
    if re.match(r"^(Unnamed|Column|Field|col)\s*:?\s*\d*$", name_clean, re.IGNORECASE):
        return True
    return False


def _is_numeric_like(value) -> bool:
    """Check if a value looks numeric."""
    try:
        float(str(value).replace(",", "").replace("$", "").replace("€", "").replace("%", ""))
        return True
    except (ValueError, TypeError):
        return False


def _check_date_ambiguity(date_strings: pd.Series) -> bool:
    """Check if dates are ambiguous (all day values <= 12, making MM/DD vs DD/MM unclear)."""
    for val in date_strings.head(50):
        parts = re.split(r"[/\-]", str(val))
        if len(parts) >= 2:
            try:
                first, second = int(parts[0]), int(parts[1])
                # If either part is > 12, format is unambiguous
                if first > 12 or second > 12:
                    return False
            except ValueError:
                continue
    return True


def _get_sample(series: pd.Series, n: int = 5) -> list:
    """Get sample non-null values as strings."""
    return [str(v) for v in series.dropna().head(n).tolist()]


def _safe_serialize(value):
    """Convert a value to a JSON-serializable type."""
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
