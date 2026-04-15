from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Literal


class Settings(BaseSettings):

    APP_NAME: str = "Engram"
    VERSION: str = "0.1.0"

    # ── LLM ───────────────────────────────────────────────────────────────────
    LLM_PROVIDER: Literal["ollama", "groq"] = "ollama"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    # ── PostgreSQL + pgvector ─────────────────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "engram"
    POSTGRES_USER: str = "engram"
    POSTGRES_PASSWORD: str = "engram"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ── Obsidian Vault ────────────────────────────────────────────────────────
    VAULT_PATH: Path = Path("~/Documents/Engram-Vault").expanduser()

    # ── Whisper ───────────────────────────────────────────────────────────────
    WHISPER_MODEL: str = "base"
    WHISPER_DEVICE: str = "cpu"

    # ── Chunking ──────────────────────────────────────────────────────────────
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    CHUNK_STRATEGY: Literal["fixed", "sentence", "recursive", "code"] = "recursive"

    # ── Embedding dims — must match your model ────────────────────────────────
    # nomic-embed-text = 768, mxbai-embed-large = 1024, all-minilm = 384
    EMBED_DIMS: int = 768

    # ── GitHub ────────────────────────────────────────────────────────────────
    GITHUB_TOKEN: str = ""
    GITHUB_USERNAME: str = ""

    # ── Obsidian vault git sync ───────────────────────────────────────────────
    # Leave empty to disable auto-commit after ingestion
    VAULT_REPO_URL: str = ""

    # ── Telegram ──────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ALLOWED_USER_ID: str = ""

    # ── Self-hosted connectors ────────────────────────────────────────────────
    NEXTCLOUD_URL: str = ""
    NEXTCLOUD_USERNAME: str = ""
    NEXTCLOUD_PASSWORD: str = ""
    NEXTCLOUD_FOLDER: str = "/"

    BOOKSTACK_URL: str = ""
    BOOKSTACK_TOKEN_ID: str = ""
    BOOKSTACK_TOKEN_SECRET: str = ""

    # ── Web Search (Phase 3) ──────────────────────────────────────────────────
    SEARCH_PROVIDER: Literal["duckduckgo", "searxng"] = "searxng"
    SEARXNG_URL: str = ""

    # ── Notifications — ntfy.sh (Phase 3) ────────────────────────────────────
    NTFY_URL: str = "https://ntfy.sh"   # or your self-hosted instance
    NTFY_TOPIC: str = ""                # e.g. "engram-research-abc123"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
