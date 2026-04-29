import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ColumnProfile(BaseModel):
    original_name: str
    total_rows: int
    null_count: int
    null_percentage: float
    unique_count: int
    unique_percentage: float
    sample_values: list[Any]
    inferred_dtype: str
    # Numeric stats (optional)
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    median: float | None = None
    # String stats (optional)
    avg_length: float | None = None
    max_length: int | None = None
    detected_pattern: str | None = None


class DataProfile(BaseModel):
    columns: dict[str, ColumnProfile]
    total_rows: int
    total_columns: int


class ColumnMapping(BaseModel):
    original: str
    mapped_name: str
    sql_type: Literal["TEXT", "INTEGER", "FLOAT", "DATE", "BOOLEAN", "TIMESTAMP"]
    description: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"]

    @field_validator("mapped_name")
    @classmethod
    def validate_sql_safe(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(f"Column name '{v}' is not SQL-safe")
        if len(v) > 30:
            raise ValueError(f"Column name '{v}' exceeds 30 characters")
        return v


class SchemaMapping(BaseModel):
    columns: list[ColumnMapping]


class SQLResponse(BaseModel):
    sql: str
    explanation: str

    @field_validator("sql")
    @classmethod
    def validate_read_only(cls, v: str) -> str:
        forbidden = [
            "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
            "CREATE", "TRUNCATE", "GRANT", "REVOKE",
        ]
        upper = v.upper()
        for keyword in forbidden:
            if re.search(rf"\b{keyword}\b", upper):
                raise ValueError(f"Generated SQL contains forbidden keyword: {keyword}")
        return v


class HeaderMappingResponse(BaseModel):
    """Raw LLM response for header mapping: original -> mapped name."""
    mappings: dict[str, str]

    @field_validator("mappings")
    @classmethod
    def validate_all_sql_safe(cls, v: dict[str, str]) -> dict[str, str]:
        for original, mapped in v.items():
            if not re.match(r"^[a-z][a-z0-9_]*$", mapped):
                raise ValueError(f"Mapped name '{mapped}' for '{original}' is not SQL-safe")
            if len(mapped) > 30:
                raise ValueError(f"Mapped name '{mapped}' exceeds 30 characters")
        return v


class DictionaryEntry(BaseModel):
    description: str
    sql_type: Literal["TEXT", "INTEGER", "FLOAT", "DATE", "BOOLEAN", "TIMESTAMP"]
    confidence: Literal["HIGH", "MEDIUM", "LOW"]


class DictionaryResponse(BaseModel):
    """Raw LLM response for dictionary generation."""
    columns: dict[str, DictionaryEntry]


class DatasetMetadata(BaseModel):
    id: str
    dataset_name: str
    original_filename: str
    column_dictionary: dict[str, Any]
    business_context: str = ""
    table_name: str
    row_count: int
    upload_date: str


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    sql: str
    data: list[dict[str, Any]]
    row_count: int
    truncated: bool = False
    chart_suggestion: dict[str, Any] | None = None
    attempts: int = 1


class QueryResult(BaseModel):
    success: bool
    data: list[dict[str, Any]] | None = None
    row_count: int = 0
    truncated: bool = False
    error: str | None = None


# --- Space Dashboard schemas ---


class Space(BaseModel):
    id: str
    name: str
    description: str = ""
    created_at: str
    updated_at: str


class CreateSpaceRequest(BaseModel):
    name: str
    description: str = ""


class UpdateSpaceRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class WidgetLayout(BaseModel):
    x: int = 0
    y: int = 0
    w: int = 6
    h: int = 2


# --- Composition / Layer model (ambitious widget schema) ---
#
# A Widget's config can either be:
#   (a) legacy: {"echarts_option": {...}} for type="chart", etc.
#   (b) composition: {"layers": [Layer, ...], "canvas": {...}}
#
# The frontend LayerWidget renderer handles both — legacy configs are
# implicitly wrapped as a single chart layer.

Anchor = Literal[
    "top-left", "top-center", "top-right",
    "center-left", "center", "center-right",
    "bottom-left", "bottom-center", "bottom-right",
    "fill",
]

# Semantic placement in the layer stack. Replaces ad-hoc numeric z for the
# common case of "behind / in / above the chart". The renderer maps this to
# a numeric z internally (background=-10, chart=0, overlay=10, annotation=20,
# foreground=30). Numeric `z` still works as a fallback so legacy widgets
# (e.g. `z: -1` backgrounds) keep rendering correctly.
Placement = Literal["background", "chart", "overlay", "annotation", "foreground"]


class Layer(BaseModel):
    """A single compositional layer inside a widget.

    Positioning: `anchor` pins the layer to a corner/edge/center of the
    widget body. `offset` (px) nudges it inward. `size` (px) sets width/height.
    `anchor: "fill"` stretches to the whole body (offset/size ignored).
    """
    id: str
    type: Literal["chart", "image", "text", "svg", "shape", "icon"]
    anchor: Anchor = "top-left"
    offset: list[int] = Field(default_factory=lambda: [0, 0])
    size: list[int] | None = None  # [w, h] in px; null = auto
    placement: Placement | None = None  # preferred — semantic stack position
    z: int = 0                          # legacy / escape hatch; ignored if placement set
    # type-specific (all optional; validated per type by the frontend)
    echarts_option: dict[str, Any] | None = None  # type=chart
    src: str | None = None                        # type=image (URL or /assets/...)
    asset_id: str | None = None                   # type=image (reference by id)
    content: str | None = None                    # type=text
    markup: str | None = None                     # type=svg (inline SVG string)
    kind: Literal["rect", "circle", "line"] | None = None  # type=shape
    name: str | None = None                       # type=icon (lucide name, e.g. "trending-up")
    color: str | None = None                      # type=icon (CSS color; defaults to currentColor)
    style: dict[str, Any] | None = None           # css-ish: color, fontSize, opacity, ...


class Composition(BaseModel):
    """A composed widget body = ordered stack of layers."""
    canvas: dict[str, Any] = Field(default_factory=dict)  # e.g. {"background": "#0b0b0b"}
    layers: list[Layer] = Field(default_factory=list)


class Widget(BaseModel):
    id: str
    dashboard_id: str
    widget_type: Literal["chart", "kpi", "table"]
    title: str
    config: dict[str, Any]
    sql_query: str | None = None
    layout: WidgetLayout
    created_at: str
    updated_at: str


class CreateWidgetRequest(BaseModel):
    widget_type: Literal["chart", "kpi", "table"]
    title: str
    config: dict[str, Any]
    sql_query: str | None = None
    layout: WidgetLayout = Field(default_factory=WidgetLayout)


class Dashboard(BaseModel):
    id: str
    space_id: str
    name: str
    created_at: str
    updated_at: str
    widgets: list[Widget] = []


class CreateDashboardRequest(BaseModel):
    name: str


class UpdateLayoutRequest(BaseModel):
    """Batch layout update from react-grid-layout onLayoutChange."""
    layouts: dict[str, WidgetLayout]


class Asset(BaseModel):
    id: str
    space_id: str
    filename: str
    mime: str
    url: str
    tags: list[str] = []
    created_at: str


class ChatMessage(BaseModel):
    id: str
    space_id: str
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_result: dict[str, Any] | None = None
    created_at: str


class DashboardChatRequest(BaseModel):
    message: str
    space_id: str
    dashboard_id: str | None = None


class SSEEvent(BaseModel):
    event: str
    data: dict[str, Any]
