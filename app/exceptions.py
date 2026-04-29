class PipelineError(Exception):
    """Base exception for pipeline errors."""


class FileValidationError(PipelineError):
    """Raised when an uploaded file fails validation."""


class LLMRetryExhausted(PipelineError):
    """Raised when all LLM retry attempts fail."""


class SchemaValidationError(PipelineError):
    """Raised when LLM output fails Pydantic validation."""


class QueryExecutionError(PipelineError):
    """Raised when a generated SQL query fails to execute."""


class VRAMConflictError(PipelineError):
    """Raised when attempting to load a model while another is in VRAM."""
