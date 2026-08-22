"""Schema validation for the intent a model proposes: parse it, or discard it.

The model's one job is to propose an :class:`AnalyticalIntent` as a plain mapping. That output is
untrusted: it is validated against this schema and DISCARDED on any failure, exactly as the
determinism rule requires. A discarded proposal becomes a refusal, never a guess, because the
resolver and composer downstream only ever act on a well-formed, then certified, intent.

Nothing here authorises anything. It only checks the SHAPE (types and required fields); whether
the named metric, dimensions and filters are CERTIFIED is the resolver's separate, deterministic
job. Keeping the two apart means a malformed proposal and an uncertified one both refuse, for
reasons a caller can tell apart.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import AnalyticalIntent, Filter


def parse_intent(raw: Mapping[str, Any]) -> AnalyticalIntent | None:
    """Validate a proposed intent mapping into an ``AnalyticalIntent``, or ``None`` on failure."""
    if not isinstance(raw, Mapping):
        return None
    metric_id = raw.get("metric_id")
    if not isinstance(metric_id, str) or not metric_id.strip():
        return None

    dimensions = raw.get("dimensions", [])
    if not _is_str_sequence(dimensions):
        return None

    grain = raw.get("grain", "")
    if not isinstance(grain, str):
        return None

    filters_raw = raw.get("filters", [])
    if not isinstance(filters_raw, (list, tuple)):
        return None
    filters: list[Filter] = []
    for item in filters_raw:
        if not isinstance(item, Mapping):
            return None
        field = item.get("field")
        value = item.get("value")
        if not isinstance(field, str) or not field.strip():
            return None
        if not isinstance(value, (str, int, float)):
            return None
        filters.append(Filter(field=field, value=str(value)))

    return AnalyticalIntent(
        metric_id=metric_id.strip(),
        dimensions=tuple(str(d) for d in dimensions),
        filters=tuple(filters),
        grain=grain.strip(),
    )


def _is_str_sequence(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value)
