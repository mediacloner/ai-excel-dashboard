import httpx

from app.exceptions import VRAMConflictError


OLLAMA_BASE_URL = "http://localhost:11434"


async def get_loaded_models() -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{OLLAMA_BASE_URL}/api/ps")
        resp.raise_for_status()
        return resp.json().get("models", [])


async def ensure_vram_free() -> None:
    models = await get_loaded_models()
    if models:
        model_names = [m.get("name", "unknown") for m in models]
        raise VRAMConflictError(
            f"VRAM is occupied by: {', '.join(model_names)}. "
            "Wait for model to unload or restart Ollama."
        )


async def force_unload(model_name: str) -> None:
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": model_name, "keep_alive": 0},
        )
