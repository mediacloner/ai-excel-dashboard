from pathlib import Path

import yaml
from pydantic import BaseModel


class ModelConfig(BaseModel):
    name: str
    num_ctx: int = 4096
    keep_alive: str = "5m"
    temperature: float = 0.1
    format: str | None = None
    stop: list[str] | None = None


class ModelsConfig(BaseModel):
    schema_mapping: ModelConfig
    text_to_sql: ModelConfig
    dashboard_agent: ModelConfig | None = None
    ingestion_agent: ModelConfig | None = None


class DatabaseConfig(BaseModel):
    engine: str = "duckdb"
    path: str = "data/warehouse.duckdb"
    query_timeout_seconds: int = 10
    max_result_rows: int = 5000


class IngestionConfig(BaseModel):
    sample_rows: int = 10
    max_columns: int = 100
    max_file_size_mb: int = 50
    max_rows: int = 500_000
    allowed_extensions: list[str] = [".xlsx", ".xls", ".csv"]
    llm_retry_attempts: int = 3
    upload_dir: str = "data/uploads"


class ProfilingConfig(BaseModel):
    null_threshold_warning: float = 0.3
    unique_ratio_categorical: float = 0.05


class LangGraphConfig(BaseModel):
    checkpoint_db: str = "data/langgraph_state.db"


class AppConfig(BaseModel):
    models: ModelsConfig
    database: DatabaseConfig
    ingestion: IngestionConfig = IngestionConfig()
    profiling: ProfilingConfig = ProfilingConfig()
    langgraph: LangGraphConfig = LangGraphConfig()


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    return AppConfig.model_validate(raw)


# Module-level singleton loaded on first import
_config: AppConfig | None = None


def get_config() -> AppConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config
