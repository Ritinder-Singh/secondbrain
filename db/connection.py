"""
PostgreSQL connection pool using psycopg3.
pgvector registers its types on each connection.
"""
import atexit
from contextlib import contextmanager
from typing import Generator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import JsonbDumper
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector

from config.settings import settings

_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=settings.DATABASE_URL,
            min_size=1,
            max_size=10,
            open=True,
        )
        atexit.register(_pool.close)
    return _pool


@contextmanager
def get_conn() -> Generator[psycopg.Connection, None, None]:
    """Context manager that checks out a connection from the pool."""
    pool = _get_pool()
    with pool.connection() as conn:
        register_vector(conn)
        conn.adapters.register_dumper(dict, JsonbDumper)  # auto-serialize dicts as JSONB
        yield conn


@contextmanager
def get_cursor() -> Generator[psycopg.Cursor, None, None]:
    """Convenience: context manager yielding a dict-row cursor."""
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            yield cur
