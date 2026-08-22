"""Local QueryEnginePort: stdlib ``sqlite3`` over a seeded fictional warehouse.

Keeps the offline gate SDK-free while executing the SAME composed, validated query the managed
BigQuery engine would run. The warehouse is seeded from :data:`WAREHOUSE` into an in-memory
database, deliberately holding a second tenant's rows so the row-level predicate has something to
exclude. Parameters are bound by the driver; the SQL text carries no caller value.
"""

from __future__ import annotations

import sqlite3

from ...config import Settings
from ...domain.models import CompiledQuery, QueryResult
from ._fixtures import WAREHOUSE


def _seed(conn: sqlite3.Connection) -> None:
    for table, (columns, rows) in WAREHOUSE.items():
        cols = ", ".join(columns)
        conn.execute(f"CREATE TABLE {table} ({cols})")
        placeholders = ", ".join("?" for _ in columns)
        conn.executemany(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", rows)
    conn.commit()


def _cell(value: object) -> str:
    return "" if value is None else str(value)


class LocalQueryEngineAdapter:
    """Execute a composed query against the seeded in-memory warehouse."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # check_same_thread=False: the demo server is threaded, and this connection is read-only
        # after seeding (every query is a bounded SELECT), so cross-thread reads are safe. A write
        # path would need a lock, but the query engine never writes.
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        _seed(self._conn)

    def execute(self, query: CompiledQuery) -> QueryResult:
        bound = {name: value for name, value in query.params}
        cursor = self._conn.execute(query.sql, bound)
        columns = tuple(str(description[0]) for description in cursor.description)
        rows = tuple(tuple(_cell(value) for value in row) for row in cursor.fetchall())
        return QueryResult(columns=columns, rows=rows)
