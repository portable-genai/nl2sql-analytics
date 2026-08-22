"""The governed NL-to-SQL orchestrator: propose, authorise, compose, execute, cite, escalate.

This is the vertical's consequential path, and every consequential decision on it is PURE CODE.
The model has exactly two narrow jobs, both untrusted and both bounded: it PROPOSES a structured
intent (validated against a schema and discarded on failure), and it NARRATES the result (checked
for groundedness and discarded on failure). It never chooses a metric that gets answered, never
authorises a dataset, never composes SQL and never produces a figure or a verdict.

The order is deliberate and fail-closed at every hop:

1. redact the question with the shared pack BEFORE anything outbound or any model call;
2. screen it through the guardrail; a block, or an unavailable screen, REFUSES (the injection
   corpus never reaches the generation port because generation is step 5, after this);
3. retrieve data-dictionary hints for the model;
4. the model proposes an intent; a malformed proposal REFUSES;
5. the resolver certifies the intent against the semantic layer, or REFUSES with alternatives;
6. the certification gate reads the backing dataset's H4 status; anything but a currently
   certified (or conditionally certified) dataset that lists this metric REFUSES;
7. the composer builds a bounded, read-only, tenant-scoped SELECT from certified fragments and
   VALIDATES it; only then does the query engine execute it;
8. the model narrates, grounded; every figure is cited to its metric definition and the dataset's
   certification; a conditionally certified backing, or an empty result, sets human review.

Redaction happens again before the audit write, so no raw identifier reaches the WORM record.
"""

from __future__ import annotations

from pii_kit import redact

from ..ports.audit import AuditSinkPort
from ..ports.certification import CertificationPort
from ..ports.dictionary import DictionaryPort
from ..ports.guardrail import GuardrailPort
from ..ports.llm import AnalystLlmPort
from ..ports.observability import ObservabilityTracerPort
from ..ports.query_engine import QueryEnginePort
from .intent import parse_intent
from .kernel import AuditEvent, Citation, Decision, Severity, utcnow
from .models import (
    AnalystAnswer,
    CertificationStatus,
    DatasetCertification,
    QueryResult,
    Question,
    Refusal,
    ResolvedIntent,
)
from .narration import is_grounded
from .pii import PII_PATTERNS
from .semantic_layer import SemanticLayer
from .semantic_resolver import SemanticResolver
from .sql_builder import SqlBuilder, UnsafeQueryError

_EMPTY_RESULT = QueryResult(columns=(), rows=())

#: One span per answered question. Structural attributes only: see :meth:`AnalystService.answer`.
_ANSWER_SPAN = "nl2sql.answer"


class AnalystService:
    """Answer a governed analytical question, or refuse it, deterministically."""

    def __init__(
        self,
        *,
        layer: SemanticLayer,
        guardrail: GuardrailPort,
        dictionary: DictionaryPort,
        llm: AnalystLlmPort,
        certification: CertificationPort,
        query_engine: QueryEnginePort,
        audit: AuditSinkPort,
        tracer: ObservabilityTracerPort,
    ) -> None:
        self._layer = layer
        self._guardrail = guardrail
        self._dictionary = dictionary
        self._llm = llm
        self._certification = certification
        self._engine = query_engine
        self._audit = audit
        self._tracer = tracer
        self._resolver = SemanticResolver(layer)
        self._builder = SqlBuilder()

    def answer(self, question: Question, *, actor: str) -> AnalystAnswer:
        """Answer ``question`` on the governed path, or refuse it, inside one span.

        The span's attributes are STRUCTURAL only, never the question text, a proposed
        intent, a SQL fragment, a figure or a refusal reason: a trace backend is not the
        WORM audit trail; it has no redaction stage, a wider read audience and no retention
        rule written against a regulator's requirement, so anything content-shaped that
        reaches a span has left the boundary the ``redact`` calls below exist to hold, and
        left it silently.
        """
        with self._tracer.span(_ANSWER_SPAN, action="answer", actor=actor, tenant=question.tenant):
            return self._answer_question(question, actor=actor)

    def _answer_question(self, question: Question, *, actor: str) -> AnalystAnswer:
        redacted_question = redact(question.text, PII_PATTERNS)

        # 2. Screen BEFORE generation. A block, or a screen we could not reach, refuses; the
        # generation port is never called for a screened-out question.
        try:
            screen = self._guardrail.screen(redacted_question)
        except Exception:  # noqa: BLE001 - an unreachable screen must fail closed, not crash
            return self._refuse(
                question,
                Refusal(reason="input screening is unavailable, so the question is refused"),
                actor,
            )
        if not screen.allowed:
            return self._refuse(
                question,
                Refusal(reason=f"input screening blocked the question: {screen.reason}"),
                actor,
            )

        # 3-4. Retrieve dictionary hints and let the model propose an intent; validate the shape.
        hints = tuple(self._dictionary.lookup(redacted_question))
        proposal = self._llm.propose_intent(redacted_question, hints)
        intent = parse_intent(proposal)
        if intent is None:
            return self._refuse(
                question,
                Refusal(
                    reason="the question could not be formed into a valid analytical intent",
                    alternatives=self._layer.certified_metric_ids(),
                ),
                actor,
            )

        # 5. Certify the intent against the layer.
        resolved = self._resolver.resolve(intent)
        if isinstance(resolved, Refusal):
            return self._refuse(question, resolved, actor)

        # 6. The certification gate on H4.
        cert = self._dataset_certification(resolved.dataset.name)
        gate = self._gate(resolved, cert)
        if gate is not None:
            return self._refuse(question, gate, actor)

        # 7. Compose, validate and execute.
        try:
            compiled = self._builder.compile(resolved, tenant=question.tenant)
        except UnsafeQueryError as exc:  # pragma: no cover - composition is proven safe by tests
            return self._refuse(
                question, Refusal(reason=f"query composition failed validation: {exc}"), actor
            )
        result = self._engine.execute(compiled)

        return self._answer(question, resolved, cert, compiled.sql, result, actor)

    # ------------------------------------------------------------------ helpers

    def _dataset_certification(self, dataset_id: str) -> DatasetCertification:
        """Read the backing dataset's H4 status, failing closed to UNKNOWN if it cannot be read."""
        try:
            return self._certification.dataset_status(dataset_id)
        except Exception:  # noqa: BLE001 - an unreachable certification source is UNKNOWN, refuses
            return DatasetCertification(dataset_id=dataset_id, status=CertificationStatus.UNKNOWN)

    def _gate(self, resolved: ResolvedIntent, cert: DatasetCertification) -> Refusal | None:
        """None means the answer may proceed; a Refusal means the certification gate closed it."""
        metric_id = resolved.metric.id
        certified_here = metric_id in cert.certified_metrics
        if cert.status is CertificationStatus.CERTIFIED and certified_here:
            return None
        if cert.status is CertificationStatus.CONDITIONAL and certified_here:
            return None
        return Refusal(
            reason=(
                f"backing dataset {resolved.dataset.name!r} is not currently certified for "
                f"metric {metric_id!r} (H4 status: {cert.status.value}); the question is refused"
            ),
            alternatives=self._layer.certified_metric_ids(),
        )

    def _answer(
        self,
        question: Question,
        resolved: ResolvedIntent,
        cert: DatasetCertification,
        sql: str,
        result: QueryResult,
        actor: str,
    ) -> AnalystAnswer:
        metric = resolved.metric
        conditional = cert.status is CertificationStatus.CONDITIONAL
        empty = not result.rows
        needs_review = conditional or empty

        caveats: list[str] = []
        if conditional:
            caveats.append(
                "backing data is conditionally certified; figures are provisional and under review"
            )
        if empty:
            caveats.append("no rows matched the certified query; the result may be incomplete")

        summary = self._narrate(metric.title, resolved.dimensions, result, caveats)
        severity = Severity.HIGH if needs_review else Severity.LOW
        decision = Decision.ESCALATED if needs_review else Decision.ALLOWED
        citations = (
            Citation(
                source_id=f"metric:{metric.id}",
                title=metric.title,
                snippet=f"definition {metric.definition_version}, grain {metric.grain}",
            ),
            Citation(
                source_id=f"cert:{resolved.dataset.name}",
                title="H4 dataset certification",
                snippet=f"{cert.status.value}; scorecard {cert.scorecard_ref or 'n/a'}",
            ),
        )
        self._record(
            actor=actor,
            decision=decision,
            severity=severity,
            summary=f"{metric.title}: {summary}",
            question=question,
            citations=citations,
        )
        return AnalystAnswer(
            question=question.text,
            subject=metric.title,
            metric_id=metric.id,
            certification_status=cert.status,
            severity=severity,
            decision=decision,
            summary=summary,
            sql=sql,
            result=result,
            requires_human_review=needs_review,
            refused=False,
            citations=citations,
            refusal=None,
            caveats=tuple(caveats),
        )

    def _narrate(
        self,
        metric_title: str,
        dimensions: tuple[str, ...],
        result: QueryResult,
        caveats: list[str],
    ) -> str:
        """Ask the model to narrate, then DISCARD its text if it invents a figure or runs long."""
        facts = {
            "metric": metric_title,
            "dimensions": list(dimensions),
            "columns": list(result.columns),
            "rows": [list(row) for row in result.rows],
            "row_count": len(result.rows),
            "caveats": list(caveats),
        }
        try:
            drafted = self._llm.narrate(facts)
        except Exception:  # noqa: BLE001 - a failed narrator degrades to the deterministic summary
            drafted = ""
        if isinstance(drafted, str) and is_grounded(drafted, result):
            return drafted
        return self._deterministic_summary(metric_title, dimensions, result)

    @staticmethod
    def _deterministic_summary(
        metric_title: str, dimensions: tuple[str, ...], result: QueryResult
    ) -> str:
        by = ", ".join(dimensions) if dimensions else "total"
        return f"{metric_title} by {by}: {len(result.rows)} row(s) returned."

    def _refuse(self, question: Question, refusal: Refusal, actor: str) -> AnalystAnswer:
        citation = Citation(
            source_id="policy:semantic-layer",
            title="Governed semantic layer",
            snippet=refusal.reason[:120],
        )
        self._record(
            actor=actor,
            decision=Decision.ALLOWED,
            severity=Severity.LOW,
            summary=f"refused: {refusal.reason}",
            question=question,
            citations=(citation,),
        )
        return AnalystAnswer(
            question=question.text,
            subject="refused",
            metric_id="",
            certification_status=CertificationStatus.UNKNOWN,
            severity=Severity.LOW,
            decision=Decision.ALLOWED,
            summary=refusal.reason,
            sql="",
            result=_EMPTY_RESULT,
            requires_human_review=False,
            refused=True,
            citations=(citation,),
            refusal=refusal,
            caveats=(),
        )

    def _record(
        self,
        *,
        actor: str,
        decision: Decision,
        severity: Severity,
        summary: str,
        question: Question,
        citations: tuple[Citation, ...],
    ) -> None:
        """Write one already-redacted WORM audit record. The raw question never reaches it."""
        redacted = redact(f"{summary} :: {question.text}", PII_PATTERNS)
        self._audit.record(
            AuditEvent(
                action="analyst_answer",
                actor=actor,
                decision=decision,
                severity=severity,
                redacted_summary=redacted,
                citations=citations,
                timestamp=utcnow(),
            )
        )
