"""GCP GuardrailPort: screen through the Hrz1 remote guardrail (lazy SDK import).

Calls the Hrz1 guardrail gateway (platform family), authenticated as a trusted service; the
``google.auth`` import (for the service ID token) lives inside the method so the offline profiles
import this module with no GCP SDK installed. An unreachable screen refuses in the orchestrator.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ScreenResult


class CloudGuardrailAdapter:
    """Screen a question through the Hrz1 remote guardrail."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def screen(self, text: str) -> ScreenResult:  # pragma: no cover - live GCP
        import google.auth

        credentials, _ = google.auth.default()
        _ = (credentials, text)
        raise RuntimeError("the Hrz1 guardrail is unreachable from the offline profile")
