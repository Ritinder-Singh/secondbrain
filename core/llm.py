"""
LLM client — Ollama only. Strictly local, no cloud calls.
Embeddings and chat completions both stay on the local Ollama instance.
"""
from openai import OpenAI
from typing import Generator
from config.settings import settings


_OLLAMA_HEADERS = {"ngrok-skip-browser-warning": "true"}


def _ollama_client() -> OpenAI:
    return OpenAI(
        api_key="ollama",
        base_url=f"{settings.OLLAMA_BASE_URL}/v1",
        default_headers=_OLLAMA_HEADERS,
    )


def get_model() -> str:
    return settings.OLLAMA_MODEL


def chat(messages: list[dict], stream: bool = False) -> str | Generator:
    client = _ollama_client()
    response = client.chat.completions.create(
        model=get_model(), messages=messages, stream=stream
    )
    if stream:
        def _gen():
            for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        return _gen()
    return response.choices[0].message.content


def embed(text: str) -> list[float]:
    client = _ollama_client()
    response = client.embeddings.create(model=settings.OLLAMA_EMBED_MODEL, input=text)
    return response.data[0].embedding


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Batch embed — single HTTP call, preserves input order."""
    if not texts:
        return []
    client = _ollama_client()
    response = client.embeddings.create(model=settings.OLLAMA_EMBED_MODEL, input=texts)
    # Sort by index to guarantee order matches input
    return [d.embedding for d in sorted(response.data, key=lambda x: x.index)]
