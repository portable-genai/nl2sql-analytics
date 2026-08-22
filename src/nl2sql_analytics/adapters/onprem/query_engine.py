"""On-prem QueryEnginePort: fail-fast portability placeholder (the sovereign-exit proof, P-12)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import CompiledQuery, QueryResult


class OnPremQueryEngineAdapter:
    """Satisfies QueryEnginePort but refuses: bind the client's own warehouse."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def execute(self, query: CompiledQuery) -> QueryResult:
        raise NotImplementedError(
            "on-prem query engine is a portability placeholder: bind the client's own warehouse "
            "(see docs/onprem-migration.md)"
        )
