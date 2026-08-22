"""On-prem AnalystLlmPort: fail-fast portability placeholder (the sovereign-exit proof, P-12)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...config import Settings
from ...domain.models import DictionaryEntry


class OnPremAnalystLlm:
    """Satisfies AnalystLlmPort but refuses: bind the client's own model runtime."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def propose_intent(
        self, question: str, hints: tuple[DictionaryEntry, ...]
    ) -> Mapping[str, Any]:
        raise NotImplementedError(
            "on-prem model is a portability placeholder: bind the client's own model runtime "
            "(see docs/onprem-migration.md)"
        )

    def narrate(self, facts: Mapping[str, Any]) -> str:
        raise NotImplementedError(
            "on-prem model is a portability placeholder: bind the client's own model runtime "
            "(see docs/onprem-migration.md)"
        )
