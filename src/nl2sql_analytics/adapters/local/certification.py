"""Local CertificationPort: the fixture feed mirroring H4's certification response schema.

This is the ``local`` adapter for the one hard hand-off in the wave: H4's certification verdict
crosses to H1 as data. It reads the seeded :data:`CERTIFICATION_FEED`, whose shape mirrors H4's
pinned response, so the offline gate exercises the real certification gate without a running H4.
A dataset the feed does not list is UNKNOWN, and the orchestrator refuses an UNKNOWN dataset.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import CertificationStatus, DatasetCertification
from ._fixtures import CERTIFICATION_FEED


class LocalCertificationAdapter:
    """Answer certification status from the offline fixture feed."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def dataset_status(self, dataset_id: str) -> DatasetCertification:
        record = CERTIFICATION_FEED.get(dataset_id)
        if record is None:
            return DatasetCertification(dataset_id=dataset_id, status=CertificationStatus.UNKNOWN)
        raw_metrics = record.get("certified_metrics", ())
        metrics = (
            tuple(str(m) for m in raw_metrics) if isinstance(raw_metrics, (list, tuple)) else ()
        )
        return DatasetCertification(
            dataset_id=dataset_id,
            status=CertificationStatus(str(record["status"])),
            certified_metrics=metrics,
            scorecard_ref=str(record.get("scorecard_ref", "")),
        )
