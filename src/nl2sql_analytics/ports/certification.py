"""CertificationPort: the boundary to the H4 data-governance agent's certification verdict.

H4's certification response crosses to H1 as DATA over H4's API, never as code: H1 never imports
H4. This port is that seam. The ``local`` adapter is a fixture feed mirroring H4's pinned response
schema, so H1's offline gate never needs a running H4; the ``gcp`` adapter calls H4's deployed
endpoint; ``onprem`` fails fast. Resolution is fail-closed: an unknown or unreachable dataset
status refuses (see the orchestrator), never answers.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import DatasetCertification


@runtime_checkable
class CertificationPort(Protocol):
    def dataset_status(self, dataset_id: str) -> DatasetCertification:
        """Return H4's current certification for one dataset (UNKNOWN when it has none)."""
        ...
