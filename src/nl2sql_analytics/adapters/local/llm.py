"""Local AnalystLlmPort: a deterministic, SDK-free stand-in for the analytical model.

It does the model's two jobs by pure code, so the offline gate is reproducible and needs no
credentials: it PROPOSES an intent by matching dictionary hints and dimension words, and it
NARRATES a result from the facts alone. Both outputs are still treated as untrusted by the
orchestrator (schema-validated / grounded-checked and discarded on failure), exactly as a real
model's would be, so the offline path exercises the same guards the managed path relies on.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...config import Settings
from ...domain.models import DictionaryEntry
from ._fixtures import DIMENSION_WORDS, METRIC_SYNONYMS


class LocalAnalystLlm:
    """Deterministic intent proposal and grounded narration."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def propose_intent(
        self, question: str, hints: tuple[DictionaryEntry, ...]
    ) -> Mapping[str, Any]:
        lowered = question.lower()
        metric_id = hints[0].metric_id if hints else self._keyword_metric(lowered)
        dimensions = [column for word, column in DIMENSION_WORDS.items() if word in lowered]
        # De-duplicate while keeping order (two words may map to one column).
        ordered: list[str] = []
        for column in dimensions:
            if column not in ordered:
                ordered.append(column)
        return {"metric_id": metric_id, "dimensions": ordered, "filters": [], "grain": ""}

    @staticmethod
    def _keyword_metric(lowered: str) -> str:
        for term in sorted(METRIC_SYNONYMS, key=len, reverse=True):
            if term in lowered:
                return METRIC_SYNONYMS[term]
        # No recognised metric term: propose a name the layer will not certify, so it refuses.
        return "unknown_metric"

    def narrate(self, facts: Mapping[str, Any]) -> str:
        metric = str(facts.get("metric", "the metric"))
        rows = facts.get("rows") or []
        row_count = int(facts.get("row_count", len(rows)))
        parts = ["; ".join(str(cell) for cell in row) for row in rows[:5]]
        body = " | ".join(parts) if parts else "no rows matched"
        caveats = facts.get("caveats") or []
        tail = f" Caveat: {caveats[0]}" if caveats else ""
        return f"{metric}: {body} ({row_count} row(s)).{tail}"
