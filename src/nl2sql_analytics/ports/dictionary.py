"""DictionaryPort: data-dictionary retrieval that helps the model map words to certified metrics.

A retrieval seam only: it returns candidate business-term-to-metric hints for the model to weigh
when proposing an intent. It authorises nothing. The ``gcp`` family is File Search with lazy
imports, ``local`` is a fixture dictionary derived from the certified layer, ``onprem`` fails fast.
An empty return is legitimate (the model then proposes from the question alone); it never widens
what can be answered, because the resolver still refuses anything the layer does not certify.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import DictionaryEntry


@runtime_checkable
class DictionaryPort(Protocol):
    def lookup(self, question: str) -> tuple[DictionaryEntry, ...]:
        """Return data-dictionary hints relevant to the (already redacted) question."""
        ...
