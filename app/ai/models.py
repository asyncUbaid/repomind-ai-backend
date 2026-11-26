import httpx
from langchain_ollama import OllamaEmbeddings

from app.core.config import get_settings


def create_embeddings() -> OllamaEmbeddings:
    settings = get_settings()
    return OllamaEmbeddings(
        model=settings.ollama_embedding_model,
        base_url=settings.ollama_base_url,
    )


async def get_model_status() -> dict:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
        if response.status_code >= 400:
            return {"ollama_available": False, "chat_model": settings.ollama_chat_model, "embedding_model": settings.ollama_embedding_model, "error": f"Ollama returned HTTP {response.status_code}"}
        models = {item.get("name") for item in response.json().get("models", [])}
        return {
            "ollama_available": True,
            "chat_model": settings.ollama_chat_model,
            "chat_model_available": settings.ollama_chat_model in models,
            "embedding_model": settings.ollama_embedding_model,
            "embedding_model_available": settings.ollama_embedding_model in models,
        }
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        return {
            "ollama_available": False,
            "chat_model": settings.ollama_chat_model,
            "embedding_model": settings.ollama_embedding_model,
            "error": str(exc),
        }
