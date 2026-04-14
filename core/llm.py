"""
Unified LLM client — Ollama (local) or Groq (cloud fallback).
Single config flag switches providers: LLM_PROVIDER=groq in .env
Both use the OpenAI-compatible API so code is identical for both.
Embeddings ALWAYS use local Ollama regardless of LLM_PROVIDER.
"""
from openai import OpenAI
from typing import Generator
from config.settings import settings


_OLLAMA_HEADERS = {"ngrok-skip-browser-warning": "true"}


def _chat_client() -> OpenAI:
    if settings.LLM_PROVIDER == "groq":
        return OpenAI(api_key=settings.GROQ_API_KEY, base_url=settings.GROQ_BASE_URL)
    return OpenAI(
        api_key="ollama",
        base_url=f"{settings.OLLAMA_BASE_URL}/v1",
        default_headers=_OLLAMA_HEADERS,
    )


def _embed_client() -> OpenAI:
    """Embedding client is always local Ollama — never sent to cloud."""
    return OpenAI(
        api_key="ollama",
        base_url=f"{settings.OLLAMA_BASE_URL}/v1",
        default_headers=_OLLAMA_HEADERS,
    )


def get_model() -> str:
    return settings.GROQ_MODEL if settings.LLM_PROVIDER == "groq" else settings.OLLAMA_MODEL


def chat(messages: list[dict], stream: bool = False) -> str | Generator:
    client = _chat_client()
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
    """Embed a single text. Always local — embeddings never leave the machine."""
    client = _embed_client()
    response = client.embeddings.create(model=settings.OLLAMA_EMBED_MODEL, input=text)
    return response.data[0].embedding


def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of texts in a single HTTP call to Ollama.
    Dramatically faster than calling embed() per chunk for large documents.
    Returns embeddings in the same order as the input list.
    """
    if not texts:
        return []
    client = _embed_client()
    response = client.embeddings.create(model=settings.OLLAMA_EMBED_MODEL, input=texts)
    # Sort by index to guarantee order matches input
    return [d.embedding for d in sorted(response.data, key=lambda x: x.index)]
