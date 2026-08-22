"""On-prem GuardrailPort: fail-fast portability placeholder (the sovereign-exit proof, P-12)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ScreenResult


class OnPremGuardrailAdapter:
    """Satisfies GuardrailPort but refuses: bind the client's own screening gateway."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def screen(self, text: str) -> ScreenResult:
        raise NotImplementedError(
            "on-prem guardrail is a portability placeholder: bind the client's own screening "
            "gateway (see docs/onprem-migration.md)"
        )
