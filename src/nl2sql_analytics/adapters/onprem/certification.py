"""On-prem CertificationPort: fail-fast portability placeholder (the sovereign-exit proof, P-12).

The client binds its own data-governance certification source; this placeholder refuses at call
time rather than pretending a dataset is certified. Refusing is the correct failure: a placeholder
that returned CERTIFIED would let an uncertified dataset be answered from.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import DatasetCertification


class OnPremCertificationAdapter:
    """Satisfies CertificationPort but refuses: bind the client's own certification source."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def dataset_status(self, dataset_id: str) -> DatasetCertification:
        raise NotImplementedError(
            "on-prem certification is a portability placeholder: bind the client's own "
            "data-governance certification source (see docs/onprem-migration.md)"
        )
