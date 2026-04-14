"""Dataclass mirrors of DB tables for type safety."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Document:
    id: str
    title: str
    source_type: str
    source_url: str = ""
    file_path: str = ""
    para_category: str = "Resources"
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    vault_note: str = ""
    ingested_at: Optional[datetime] = None
    summary: str = ""


@dataclass
class Chunk:
    id: str
    doc_id: str
    chunk_index: int
    content: str
    embedding: list          # list[float], 768 dims
    metadata: dict = field(default_factory=dict)


@dataclass
class Message:
    id: str
    conversation_id: str
    role: str                # user | assistant
    content: str
    created_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)
