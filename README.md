# Excel Pipeline

Local AI-powered Excel/CSV ingestion and natural language SQL query system. Upload messy spreadsheets, let an LLM clean and map the schema, review it, then query your data with plain English.

Runs entirely on consumer hardware using [Ollama](https://ollama.com) for local inference with dynamic VRAM management.

## Architecture

```
Upload (Excel/CSV)
  |
  v
POST /upload --> ingest file --> profile columns
  |
  v
POST /upload/{id}/analyze --> [LLM] map headers --> [LLM] generate dictionary
  |
  v
LangGraph INTERRUPT (human review)
  |
  v
POST /review/{id}/approve --> import to DuckDB
  |
  v
POST /chat/{dataset_id}/query --> [LLM] text-to-SQL --> execute --> results
```

**Pipeline stages** (LangGraph state machine):

1. **ingest** - Read Excel/CSV, extract headers and sample rows
2. **profile** - Generate column statistics (nulls, types, patterns, distributions)
3. **map_headers** - LLM renames columns to clean, SQL-safe names
4. **generate_dict** - LLM produces a data dictionary with descriptions and SQL types
5. **import_db** - Apply approved schema and write to DuckDB

The pipeline pauses between stages 4 and 5 for human review (`interrupt_before`). The frontend presents the proposed schema, the user edits/approves, and the pipeline resumes.

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Data processing | Pandas, OpenPyXL |
| Database | DuckDB (embedded) |
| Orchestration | LangGraph (with SQLite checkpointing) |
| LLM | Ollama (Qwen3 models) via langchain-ollama |
| Validation | Pydantic v2 |

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com) installed and running
- GPU with 12GB+ VRAM recommended (tested on RTX 3060)
- 32GB system RAM recommended

### Ollama Models

Pull the required models before first run:

```bash
ollama pull qwen3:14b    # schema mapping (heavy reasoning)
ollama pull qwen3:8b     # text-to-SQL (fast, coder-optimized)
```

## Setup

```bash
# Clone the repo
git clone <repo-url>
cd "Excel Project"

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# For development
pip install -e ".[dev]"
```

## Running

```bash
# Start the API server
uvicorn app.main:app --reload
```

The server starts at `http://localhost:8000`. API docs available at `http://localhost:8000/docs`.

## API Endpoints

### Upload & Ingestion

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/upload` | Upload an Excel/CSV file, returns initial profile |
| `POST` | `/upload/{file_id}/analyze` | Run LLM pipeline through to schema review |

### Review & Approval

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/review/{file_id}` | Get pending schema for human review |
| `POST` | `/review/{file_id}/approve` | Approve schema, import data to DuckDB |

### Datasets

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/datasets` | List all imported datasets |
| `GET` | `/datasets/{dataset_id}` | Get dataset details and suggested questions |
| `DELETE` | `/datasets/{dataset_id}` | Delete a dataset and its table |

### Chat

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/chat/{dataset_id}/query` | Natural language query, returns SQL + results |

### Health

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Server status check |

## Configuration

All settings are in `config.yaml`:

```yaml
models:
  schema_mapping:
    name: "qwen3:14b"       # Heavy reasoning model for schema work
    num_ctx: 8192
    keep_alive: "0m"         # Flush VRAM immediately after use
    temperature: 0.1
    format: "json"           # Constrained JSON output
  text_to_sql:
    name: "qwen3:8b"        # Fast model for SQL generation
    num_ctx: 4096
    keep_alive: "5m"         # Keep warm during chat sessions
    temperature: 0.0
    stop: [";"]

database:
  path: "data/warehouse.duckdb"
  query_timeout_seconds: 10
  max_result_rows: 5000

ingestion:
  max_file_size_mb: 50
  max_rows: 500000
  allowed_extensions: [".xlsx", ".xls", ".csv"]
  llm_retry_attempts: 3
```

## VRAM Management

The system is designed for a single GPU with limited VRAM. Models are never loaded simultaneously:

1. **Schema mapping phase** - Loads `qwen3:14b` (~8-10GB), flushes VRAM immediately after (`keep_alive: 0m`)
2. **Chat phase** - Loads `qwen3:8b` (~5GB), stays warm for 5 minutes between queries

The `app/llm/vram.py` module checks Ollama's `/api/ps` endpoint before each LLM call to prevent conflicts.

## Project Structure

```
app/
  main.py              # FastAPI app, CORS, lifespan, router registration
  config.py            # YAML config loader (singleton)
  exceptions.py        # Custom exception hierarchy
  chat/
    agent.py           # Text-to-SQL with retry and self-correction
    prompts.py         # SQL prompt builder
    suggestions.py     # Auto-generate suggested questions
  database/
    connection.py      # DuckDB connection management
    metadata.py        # Dataset metadata CRUD
  llm/
    client.py          # Ollama wrapper with JSON validation retry
    vram.py            # VRAM conflict detection
  models/
    schemas.py         # Pydantic request/response schemas
    state.py           # LangGraph state definition
  pipeline/
    graph.py           # LangGraph state machine builder
    prompts.py         # LLM prompts for schema mapping
    nodes/
      ingest.py        # Read Excel/CSV files
      profile.py       # Generate column statistics
      map_headers.py   # LLM column renaming
      generate_dict.py # LLM data dictionary generation
      import_db.py     # Write to DuckDB
  routers/
    upload.py          # Upload endpoints
    review.py          # Schema review endpoints
    datasets.py        # Dataset management endpoints
    chat.py            # Chat query endpoint
config.yaml            # Application configuration
data/
  warehouse.duckdb     # DuckDB database
  langgraph_state.db   # LangGraph checkpoint store (SQLite)
  uploads/             # Temporary uploaded files
```

## Testing

```bash
pytest
```

## Safety

- Chat queries are restricted to `SELECT` statements only
- SQL is validated against a forbidden keyword list (INSERT, UPDATE, DELETE, DROP, etc.)
- Query execution uses read-only DuckDB connections
- File uploads are validated for extension, size, and column count
- LLM outputs are validated against Pydantic schemas before use
