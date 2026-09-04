"""GuardrailPort: screen a question through the agent-guardrail-gateway BEFORE any generation.

Every question is screened here first. A block, or a screen that could not be reached, refuses the
question, so a prompt-injection or policy-violating input never reaches the generation port. ``gcp``
is the agent-guardrail-gateway remote guardrail (platform family) with lazy imports, ``local`` is a
deterministic screen over a fixture injection corpus, ``onprem`` fails fast. Failing closed is the
whole point: an unavailable screen must refuse, never wave the question through.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import ScreenResult


@runtime_checkable
class GuardrailPort(Protocol):
    def screen(self, text: str) -> ScreenResult:
        """Screen one (already redacted) question; ``allowed`` false means do not answer it."""
        ...
