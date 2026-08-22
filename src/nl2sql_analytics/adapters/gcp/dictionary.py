"""GCP DictionaryPort: data-dictionary retrieval over Vertex AI Search / File Search (lazy).

The ``google.cloud.discoveryengine`` import lives inside the method so the offline profiles import
this module with no GCP SDK installed. Retrieval only: it returns hints and authorises nothing.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import DictionaryEntry


class CloudDictionaryAdapter:
    """Retrieve data-dictionary hints from a managed search index."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def lookup(self, question: str) -> tuple[DictionaryEntry, ...]:  # pragma: no cover - live GCP
        from google.cloud import discoveryengine

        _ = (discoveryengine, question)
        raise RuntimeError("File Search is unreachable from the offline profile")
