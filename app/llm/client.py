import json
import logging

from langchain_ollama import ChatOllama
from pydantic import BaseModel, ValidationError

from app.config import ModelConfig, get_config
from app.exceptions import LLMRetryExhausted, SchemaValidationError

logger = logging.getLogger(__name__)


def _build_chat_model(model_config: ModelConfig) -> ChatOllama:
    kwargs = {
        "model": model_config.name,
        "num_ctx": model_config.num_ctx,
        "temperature": model_config.temperature,
        "keep_alive": model_config.keep_alive,
    }
    if model_config.format:
        kwargs["format"] = model_config.format
    if model_config.stop:
        kwargs["stop"] = model_config.stop
    return ChatOllama(**kwargs)


async def call_llm_with_retry(
    prompt: str,
    schema: type[BaseModel],
    model_config: ModelConfig | None = None,
) -> BaseModel:
    config = get_config()
    if model_config is None:
        model_config = config.models.schema_mapping

    max_retries = config.ingestion.llm_retry_attempts
    last_error = None
    current_prompt = prompt

    for attempt in range(max_retries):
        try:
            # Slightly increase temperature on retries for diversity
            retry_config = model_config.model_copy(
                update={"temperature": model_config.temperature + (attempt * 0.1)}
            )
            llm = _build_chat_model(retry_config)
            response = await llm.ainvoke(current_prompt)
            content = response.content

            parsed = json.loads(content)
            validated = schema.model_validate(parsed)
            return validated

        except json.JSONDecodeError as e:
            last_error = f"Invalid JSON on attempt {attempt + 1}: {e}"
            logger.warning(last_error)
            current_prompt = (
                prompt
                + "\n\nIMPORTANT: Your previous response was not valid JSON. "
                "Respond ONLY with a valid JSON object."
            )

        except ValidationError as e:
            last_error = f"Validation failed on attempt {attempt + 1}: {e}"
            logger.warning(last_error)
            current_prompt = (
                prompt
                + f"\n\nYour previous response had validation errors:\n{e}\n"
                "Please fix these issues."
            )

    raise LLMRetryExhausted(f"Failed after {max_retries} attempts. Last error: {last_error}")


async def call_sql_llm(messages: list[dict[str, str]]) -> str:
    config = get_config()
    llm = _build_chat_model(config.models.text_to_sql)
    response = await llm.ainvoke(messages)
    return response.content.strip()


async def stream_llm(
    messages: list[dict[str, str]],
    model_config: ModelConfig | None = None,
):
    """Stream LLM response token by token. Yields content strings."""
    config = get_config()
    if model_config is None:
        model_config = config.models.dashboard_agent or config.models.text_to_sql
    llm = _build_chat_model(model_config)
    async for chunk in llm.astream(messages):
        content = chunk.content if hasattr(chunk, "content") else ""
        if content:
            yield content
