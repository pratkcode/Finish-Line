import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from app.config import DATABASE_URL

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """A shared pool, opened on first use so tests and scripts need no setup."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row, "connect_timeout": 3},
            open=True,
            name="finish-line",
        )
    return _pool


def get_connection():
    """Borrow a connection; the transaction commits when the block exits
    normally and rolls back on an exception."""
    return get_pool().connection(timeout=5)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


# Errors that mean the database can't be reached (mapped to HTTP 503).
UNAVAILABLE_ERRORS = (psycopg.OperationalError, PoolTimeout)


def check_database() -> bool:
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
        return True
    except UNAVAILABLE_ERRORS:
        return False
