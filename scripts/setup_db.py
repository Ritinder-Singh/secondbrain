"""
Run once after starting postgres to create the schema.
Usage: uv run python scripts/setup_db.py
"""
from pathlib import Path
import psycopg
from config.settings import settings


def setup() -> None:
    print(f"Connecting to {settings.DATABASE_URL}...")
    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn:
        migration_file = Path(__file__).parent.parent / "db/migrations/001_initial.sql"
        sql = migration_file.read_text()
        conn.execute(sql)

    print("✓ Schema created successfully")
    print("✓ pgvector extension enabled")
    print("✓ HNSW index created on chunks.embedding")
    print("✓ GIN index created on chunks.content")


if __name__ == "__main__":
    setup()
