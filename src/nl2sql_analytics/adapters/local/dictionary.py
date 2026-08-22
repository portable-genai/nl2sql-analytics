"""Local DictionaryPort: a fixture data dictionary derived from the certified semantic layer.

Offline stand-in for File Search. It maps business-term synonyms to certified metric ids so the
model has a hint about which metric a question is about. It authorises nothing: an unknown term
simply returns no hit, and the resolver still refuses anything the layer does not certify.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import DictionaryEntry
from ...semantic_config import load_semantic_layer
from ._fixtures import METRIC_SYNONYMS


class LocalDictionaryAdapter:
    """Return data-dictionary hints for a question from the layer plus a synonym table."""

    def __init__(self, settings: Settings) -> None:
        self._layer = load_semantic_layer(settings)

    def lookup(self, question: str) -> tuple[DictionaryEntry, ...]:
        lowered = question.lower()
        hits: list[DictionaryEntry] = []
        seen: set[str] = set()
        # Longer synonyms first, so "active customers" wins over "customers".
        for term in sorted(METRIC_SYNONYMS, key=len, reverse=True):
            if term in lowered:
                metric_id = METRIC_SYNONYMS[term]
                if metric_id in seen:
                    continue
                seen.add(metric_id)
                metric = self._layer.metric(metric_id)
                description = metric.title if metric is not None else "uncertified term"
                hits.append(
                    DictionaryEntry(term=term, metric_id=metric_id, description=description)
                )
        return tuple(hits)
