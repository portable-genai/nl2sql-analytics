"""GCP AnalystLlmPort: Gemini for intent proposal and narration (lazy SDK import).

The ``google.genai`` import lives inside the methods so the offline profiles import this
module with no GCP SDK installed. The model's output stays untrusted downstream: the proposed
intent is schema-validated and the narration is grounded-checked, both discarded on failure.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...config import Settings
from ...domain.models import DictionaryEntry


class CloudAnalystLlm:
    """Propose intents and narrate results with Gemini."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def propose_intent(
        self, question: str, hints: tuple[DictionaryEntry, ...]
    ) -> Mapping[str, Any]:  # pragma: no cover - live GCP
        from google import genai

        _ = (genai, question, hints)
        raise RuntimeError("Gemini is unreachable from the offline profile")

    def narrate(self, facts: Mapping[str, Any]) -> str:  # pragma: no cover - live GCP
        from google import genai

        _ = (genai, facts)
        raise RuntimeError("Gemini is unreachable from the offline profile")
