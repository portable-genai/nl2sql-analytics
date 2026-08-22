"""Local GuardrailPort: a deterministic screen over a fixture prompt-injection corpus.

Offline stand-in for the Hrz1 remote guardrail. It is not a no-op: it blocks any question that
carries a known prompt-injection or policy-violation marker, so the offline gate can prove the
injection corpus never reaches the generation port. A real, working screen offline is what makes
"screen unavailable fails closed" a meaningful claim rather than an untested branch.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ScreenResult
from ._fixtures import INJECTION_MARKERS


class LocalGuardrailAdapter:
    """Allow a clean question; block one carrying an injection marker."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def screen(self, text: str) -> ScreenResult:
        lowered = text.lower()
        for marker in INJECTION_MARKERS:
            if marker in lowered:
                return ScreenResult(allowed=False, reason=f"matched blocked pattern {marker!r}")
        return ScreenResult(allowed=True, reason="no blocked pattern matched")
