"""Load the certified semantic layer from ``config/semantic_layer/`` into pure domain values.

This is the I/O boundary for the layer: it reads and parses YAML (which the pure domain must not
do) and returns a frozen :class:`SemanticLayer`. A missing or unreadable file yields an EMPTY
layer, which the resolver treats as "certify nothing, refuse everything", never as "allow all":
losing the configuration must fail closed. Metrics and datasets are joined with their row/column
policies here so the domain receives one already-merged, immutable value.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import Settings
from .domain.models import DatasetSpec, MetricDefinition
from .domain.semantic_layer import SemanticLayer

#: Repo-root-relative default: ``src/<pkg>/semantic_config.py`` -> parents[2] is the repo root.
_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "config" / "semantic_layer"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return loaded if isinstance(loaded, dict) else {}


def load_semantic_layer(
    settings: Settings | None = None, *, directory: Path | None = None
) -> SemanticLayer:
    """Build the certified layer, or an empty (fail-closed) one when the files are absent."""
    _ = settings  # reserved: a deployment may later point this at a tenant-scoped layer path
    base = directory or _DEFAULT_DIR
    metrics_doc = _read_yaml(base / "metrics.yaml")
    policies_doc = _read_yaml(base / "policies.yaml")

    row_access = policies_doc.get("row_access") or {}
    column_masks = policies_doc.get("column_masks") or {}

    datasets: dict[str, DatasetSpec] = {}
    for name, spec in (metrics_doc.get("datasets") or {}).items():
        access = row_access.get(name) or {}
        masks = column_masks.get(name) or []
        datasets[str(name)] = DatasetSpec(
            name=str(name),
            table=str(spec["table"]),
            columns=tuple(str(c) for c in spec.get("columns", ())),
            tenant_column=str(spec.get("tenant_column", "tenant")),
            row_cap=int(spec.get("row_cap", 1000)),
            # Fail closed: a dataset absent from row_access is still tenant-scoped, so forgetting
            # to list it does not silently drop the predicate.
            tenant_scoped=bool(access.get("tenant_scoped", True)),
            column_masks=tuple(str(m) for m in masks),
        )

    metrics: dict[str, MetricDefinition] = {}
    for metric_id, spec in (metrics_doc.get("metrics") or {}).items():
        metrics[str(metric_id)] = MetricDefinition(
            id=str(metric_id),
            title=str(spec.get("title", metric_id)),
            aggregation=str(spec["aggregation"]),
            grain=str(spec.get("grain", "")),
            backing_dataset=str(spec["backing_dataset"]),
            allowed_dimensions=tuple(str(d) for d in spec.get("allowed_dimensions", ())),
            definition_version=str(spec.get("definition_version", "")),
        )

    return SemanticLayer(
        metrics=metrics, datasets=datasets, version=str(metrics_doc.get("version", ""))
    )
