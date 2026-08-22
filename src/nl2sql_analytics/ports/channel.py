"""ChannelPort: deliver a finished answer to the conversational surface.

The conversational channel (BigQuery conversational analytics in the managed profile) sits behind
this port so the offline gate stays SDK-free: ``local`` is a fixture channel that formats the
answer into a transcript line and returns a delivery reference, ``gcp`` rides the managed channel
with lazy imports, ``onprem`` fails fast. Delivery is the LAST step and carries only the already
composed, cited, redacted answer; it makes no decision.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import AnalystAnswer


@runtime_checkable
class ChannelPort(Protocol):
    def deliver(self, answer: AnalystAnswer) -> str:
        """Deliver the finished answer to the channel and return a delivery reference."""
        ...
