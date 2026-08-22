"""On-prem DictionaryPort: fail-fast portability placeholder (the sovereign-exit proof, P-12)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import DictionaryEntry


class OnPremDictionaryAdapter:
    """Satisfies DictionaryPort but refuses: bind the client's own dictionary/search index."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def lookup(self, question: str) -> tuple[DictionaryEntry, ...]:
        raise NotImplementedError(
            "on-prem data dictionary is a portability placeholder: bind the client's own "
            "retrieval index (see docs/onprem-migration.md)"
        )
