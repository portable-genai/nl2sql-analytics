"""QueryEnginePort: execute a composed, validated, bounded query and return its rows.

The port only ever receives a :class:`CompiledQuery` the deterministic composer built and
validated, so no free-form SQL reaches an engine. ``gcp`` is BigQuery with lazy imports, ``local``
is stdlib ``sqlite3`` over a seeded fictional warehouse (which keeps the offline gate SDK-free),
``onprem`` fails fast. Parameters are bound by the engine; the SQL text carries no caller value.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import CompiledQuery, QueryResult


@runtime_checkable
class QueryEnginePort(Protocol):
    def execute(self, query: CompiledQuery) -> QueryResult:
        """Execute the composed query with its bound parameters and return the result table."""
        ...
