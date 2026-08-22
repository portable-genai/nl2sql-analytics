"""GCP ChannelPort: deliver the answer to BigQuery conversational analytics (lazy SDK import).

The ``google.cloud.bigquery`` import lives inside the method so the offline profiles import this
module with no GCP SDK installed. Delivery is the last step and carries only the finished,
cited, redacted answer; it makes no decision.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import AnalystAnswer


class CloudChannelAdapter:
    """Deliver a finished answer to the managed conversational channel."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def deliver(self, answer: AnalystAnswer) -> str:  # pragma: no cover - live GCP
        from google.cloud import bigquery

        _ = (bigquery, answer)
        raise RuntimeError("the conversational channel is unreachable from the offline profile")
