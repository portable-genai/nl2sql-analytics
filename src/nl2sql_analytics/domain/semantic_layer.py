"""The certified semantic layer as a pure, immutable value: metrics and datasets, no I/O.

This module holds the SHAPE of the layer and the read helpers the resolver needs. It performs no
file access and imports no parser: the YAML under ``config/semantic_layer/`` is read and turned
into these frozen dataclasses by ``semantic_config.py`` in the package root (the I/O boundary),
so the domain stays pure and a test can construct a layer in memory without touching disk.

An EMPTY layer is a valid, fully fail-closed layer: it certifies nothing, so the resolver refuses
every question. That is the point of loading the configuration through a three-state reader, an
empty or missing file must not silently become "allow everything".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .models import DatasetSpec, MetricDefinition


@dataclass(frozen=True, slots=True)
class SemanticLayer:
    """Every certified metric and dataset this deployment recognises."""

    metrics: Mapping[str, MetricDefinition] = field(default_factory=dict)
    datasets: Mapping[str, DatasetSpec] = field(default_factory=dict)
    version: str = ""

    def metric(self, metric_id: str) -> MetricDefinition | None:
        """The certified metric with this id, or ``None`` when the layer does not certify it."""
        return self.metrics.get(metric_id)

    def dataset(self, dataset_id: str) -> DatasetSpec | None:
        return self.datasets.get(dataset_id)

    def certified_metric_ids(self) -> tuple[str, ...]:
        """Every certified metric id, sorted: the alternatives a refusal offers a caller."""
        return tuple(sorted(self.metrics))

    def is_empty(self) -> bool:
        return not self.metrics
