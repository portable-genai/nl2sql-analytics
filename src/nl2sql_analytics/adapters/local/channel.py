"""Local ChannelPort: format a finished answer into a transcript line, offline.

Offline stand-in for the managed conversational channel. It records the delivered answers so a
test and the demo can inspect the transcript, and returns a delivery reference. It makes no
decision and carries only the already composed, cited, redacted answer.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import AnalystAnswer


class LocalChannelAdapter:
    """Deliver an answer to an in-memory transcript for the SDK-free ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._transcript: list[str] = []

    def deliver(self, answer: AnalystAnswer) -> str:
        verdict = "REFUSED" if answer.refused else answer.metric_id
        line = f"[{verdict}] {answer.summary}"
        self._transcript.append(line)
        return f"channel:{len(self._transcript)}:{verdict}"

    @property
    def transcript(self) -> tuple[str, ...]:
        """Expose the delivered transcript for inspection in tests and the demo."""
        return tuple(self._transcript)
