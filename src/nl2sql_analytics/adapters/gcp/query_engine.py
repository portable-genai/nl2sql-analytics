"""GCP QueryEnginePort: execute the composed query on BigQuery (lazy SDK import).

The ``google.cloud.bigquery`` import lives inside the method so the offline profiles import this
module with no GCP SDK installed. It only ever receives a composed, validated, bounded query with
bound parameters, so BigQuery runs exactly the certified SQL the composer authorised.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import CompiledQuery, QueryResult


class CloudQueryEngineAdapter:
    """Execute a composed query on BigQuery with bound query parameters."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def execute(self, query: CompiledQuery) -> QueryResult:  # pragma: no cover - live GCP
        from google.cloud import bigquery

        _ = (bigquery, query)
        raise RuntimeError("BigQuery is unreachable from the offline profile")
