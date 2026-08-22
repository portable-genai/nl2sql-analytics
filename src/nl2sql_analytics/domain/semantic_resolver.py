"""The deterministic semantic resolver: an intent becomes a certified resolution, or a refusal.

Pure stdlib. Given a model-proposed :class:`AnalyticalIntent` and the certified
:class:`SemanticLayer`, it either returns a :class:`ResolvedIntent` (every element certified) or a
typed :class:`Refusal` naming the nearest certified alternatives. It is fail-closed at every step:

* an EMPTY layer refuses everything;
* a metric the layer does not certify refuses;
* a dimension outside the metric's ``allowed_dimensions`` refuses;
* a filter on a column the backing dataset does not declare refuses;
* a grain that contradicts the metric's declared grain refuses.

Nothing here reaches a database or a model. It decides, from data alone, whether a question is
inside the certified surface, so the refusal is replayable and auditable. Refusing an uncertified
ask is the governed behaviour, not an error: the alternatives let a caller ask something valid.
"""

from __future__ import annotations

from .models import AnalyticalIntent, Refusal, ResolvedIntent
from .semantic_layer import SemanticLayer


class SemanticResolver:
    """Resolve a proposed intent against the certified layer, fail-closed."""

    def __init__(self, layer: SemanticLayer) -> None:
        self._layer = layer

    def resolve(self, intent: AnalyticalIntent) -> ResolvedIntent | Refusal:
        alternatives = self._layer.certified_metric_ids()
        if self._layer.is_empty():
            return Refusal(
                reason="the semantic layer certifies no metrics, so nothing can be answered",
                alternatives=(),
            )
        metric = self._layer.metric(intent.metric_id)
        if metric is None:
            return Refusal(
                reason=(
                    f"metric {intent.metric_id!r} is not certified in the semantic layer; "
                    "only certified metrics can be answered"
                ),
                alternatives=alternatives,
            )
        dataset = self._layer.dataset(metric.backing_dataset)
        if dataset is None:
            # A metric certified against a dataset the layer does not declare is a broken layer,
            # not a caller error, but it still fails closed rather than composing against nothing.
            return Refusal(
                reason=(
                    f"metric {metric.id!r} names backing dataset {metric.backing_dataset!r}, "
                    "which the semantic layer does not declare"
                ),
                alternatives=alternatives,
            )
        allowed_dims = set(metric.allowed_dimensions)
        for dim in intent.dimensions:
            if dim not in allowed_dims:
                return Refusal(
                    reason=(
                        f"dimension {dim!r} is not certified for metric {metric.id!r}; "
                        f"certified dimensions are {', '.join(metric.allowed_dimensions) or 'none'}"
                    ),
                    alternatives=alternatives,
                )
        dataset_columns = set(dataset.columns)
        for flt in intent.filters:
            if flt.field not in dataset_columns:
                return Refusal(
                    reason=(
                        f"filter column {flt.field!r} is not a column of certified dataset "
                        f"{dataset.name!r}"
                    ),
                    alternatives=alternatives,
                )
        if intent.grain and intent.grain != metric.grain:
            return Refusal(
                reason=(
                    f"grain {intent.grain!r} contradicts metric {metric.id!r}'s certified grain "
                    f"{metric.grain!r}"
                ),
                alternatives=alternatives,
            )
        # De-duplicate dimensions while preserving order: a repeated group-by column is a
        # composition error, not a reason to widen the projection.
        seen: set[str] = set()
        ordered: list[str] = []
        for dim in intent.dimensions:
            if dim not in seen:
                seen.add(dim)
                ordered.append(dim)
        dimensions = tuple(ordered)
        return ResolvedIntent(
            metric=metric,
            dataset=dataset,
            dimensions=dimensions,
            filters=intent.filters,
            grain=metric.grain,
        )
