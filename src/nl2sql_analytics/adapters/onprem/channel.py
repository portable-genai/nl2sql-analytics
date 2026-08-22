"""On-prem ChannelPort: fail-fast portability placeholder (the sovereign-exit proof, P-12)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import AnalystAnswer


class OnPremChannelAdapter:
    """Satisfies ChannelPort but refuses: bind the client's own conversational channel."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def deliver(self, answer: AnalystAnswer) -> str:
        raise NotImplementedError(
            "on-prem channel is a portability placeholder: bind the client's own conversational "
            "channel (see docs/onprem-migration.md)"
        )
