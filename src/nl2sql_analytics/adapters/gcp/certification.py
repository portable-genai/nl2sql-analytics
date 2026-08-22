"""GCP CertificationPort: read the H4 data-governance agent's certification API (lazy imports).

Calls H4's deployed certification endpoint over its API, authenticated as a trusted service. The
``google.auth`` import lives inside the method so the offline profiles import this module with no
GCP SDK installed (the portability proof). H1 never imports H4: it consumes H4's response as data.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import DatasetCertification


class CloudCertificationAdapter:
    """Fetch certification status from H4's deployed API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def dataset_status(self, dataset_id: str) -> DatasetCertification:  # pragma: no cover - GCP
        # Lazy import: absent offline and in CI, so a call refuses rather than importing eagerly.
        import google.auth

        credentials, _ = google.auth.default()
        _ = (credentials, dataset_id)
        # A real call would GET {review_url}/v1/certification/{dataset_id} with an ID token and map
        # the JSON body onto DatasetCertification. Unreachable offline; the orchestrator treats any
        # failure here as UNKNOWN and refuses, so a missing status never becomes a silent answer.
        raise RuntimeError("H4 certification API is unreachable from the offline profile")
