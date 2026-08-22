"""Vertical artifact models: the governed NL-to-SQL analyst's own request and result types.

The artifacts THIS vertical produces, as opposed to the vertical-neutral machinery in
``kernel.py``. The service's own name is deliberately not substituted into this docstring: a
rendered line whose length depends on ``friendly_name`` fails the repo's own format check for no
reason but the length of its name.

Everything here is a frozen, pure-stdlib dataclass. The consequential path (which metric, which
dataset, which SQL, whether to escalate) is decided over these types by pure code; a model only
proposes an intent and narrates a result, and it never produces a number or a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hex_service_kit.enums import LenientStrEnum

from .kernel import Citation, Decision, Severity


class CertificationStatus(LenientStrEnum):
    """A backing dataset's certification, as reported by the H4 data-governance agent.

    ``UNKNOWN`` is the fail-closed value: a dataset H4 has never certified, or one whose status
    could not be read, is UNKNOWN, and an UNKNOWN dataset is never answered from.
    """

    CERTIFIED = "certified"
    CONDITIONAL = "conditionally_certified"
    UNCERTIFIED = "uncertified"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Question:
    """One inbound analytical question and the tenant partition asking it."""

    text: str
    #: The verified tenant partition the row-level policy scopes every query to. Never taken from
    #: the question text or a client-asserted field; the surface fills it from the principal.
    tenant: str = ""


@dataclass(frozen=True, slots=True)
class Filter:
    """One equality filter proposed for a query. ``value`` is always bound, never interpolated."""

    field: str
    value: str


@dataclass(frozen=True, slots=True)
class AnalyticalIntent:
    """The schema-validated intent a model PROPOSES from a question, before any authorisation.

    Proposing this is the model's whole job. Every field is then checked by the deterministic
    resolver against the certified layer, and anything the layer does not certify is refused, so
    a wrong or adversarial intent cannot widen access; it can only be refused.
    """

    metric_id: str
    dimensions: tuple[str, ...] = ()
    filters: tuple[Filter, ...] = ()
    grain: str = ""


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    """One certified metric from the semantic layer: the fragment plus its closed allow-lists."""

    id: str
    title: str
    aggregation: str
    grain: str
    backing_dataset: str
    allowed_dimensions: tuple[str, ...]
    definition_version: str


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    """A physical dataset the composer may target: its closed column allow-list and its bounds."""

    name: str
    table: str
    columns: tuple[str, ...]
    tenant_column: str
    row_cap: int
    tenant_scoped: bool = True
    column_masks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Refusal:
    """A typed refusal: why the question was not answered, and the nearest certified alternatives.

    A refusal is a first-class outcome, not an error. Refusing an uncertified ask is the governed
    behaviour the buyer is paying for, so it carries the alternatives a caller CAN ask instead.
    """

    reason: str
    alternatives: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedIntent:
    """An intent the resolver certified: the metric, the vetted dimensions and filters, the grain.

    Reaching this type means every element resolved to something the layer certifies. It is the
    only input the SQL composer accepts, so no uncertified fragment can reach composition.
    """

    metric: MetricDefinition
    dataset: DatasetSpec
    dimensions: tuple[str, ...]
    filters: tuple[Filter, ...]
    grain: str


@dataclass(frozen=True, slots=True)
class CompiledQuery:
    """A deterministically composed, validated, bounded, read-only query ready to execute.

    Composed from certified fragments alone. ``params`` are bound at execution; the SQL text
    never carries a caller value. ``tables`` and ``columns`` are exactly what the validator
    proved the SQL touches, so a reviewer can see the query is inside the certified surface.
    """

    sql: str
    params: tuple[tuple[str, str], ...]
    tables: tuple[str, ...]
    columns: tuple[str, ...]
    row_cap: int
    tenant_predicate_applied: bool


@dataclass(frozen=True, slots=True)
class QueryResult:
    """The rows a query engine returned: a column header and the value rows, as strings."""

    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class DatasetCertification:
    """H4's certification verdict for one dataset (the wire H1 consumes, mirrored offline)."""

    dataset_id: str
    status: CertificationStatus
    certified_metrics: tuple[str, ...] = ()
    scorecard_ref: str = ""


@dataclass(frozen=True, slots=True)
class DictionaryEntry:
    """One data-dictionary hit: a business term mapped to a certified metric, with a gloss."""

    term: str
    metric_id: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class ScreenResult:
    """A guardrail screen verdict. ``allowed`` false means the question must not be answered."""

    allowed: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class AnalystAnswer:
    """The whole outcome of one question: either a cited answer, or a typed refusal.

    Carries the fields the vertical-neutral audit and review paths read (``subject``,
    ``severity``, ``decision``, ``summary``, ``requires_human_review``, ``citations``) so the
    R8 routing and WORM audit machinery is reused unchanged, plus this vertical's own artifacts
    (the resolved metric, the composed SQL, the result table, the certification status).
    """

    question: str
    subject: str
    metric_id: str
    certification_status: CertificationStatus
    severity: Severity
    decision: Decision
    summary: str
    sql: str
    result: QueryResult
    requires_human_review: bool
    refused: bool
    citations: tuple[Citation, ...] = ()
    refusal: Refusal | None = None
    caveats: tuple[str, ...] = field(default_factory=tuple)
