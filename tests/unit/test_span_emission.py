"""The governed answer path opens ONE span, and that span carries no content.

A trace backend is not the WORM audit trail. It has no redaction stage, no retention policy
written against a regulator's requirement, and a far wider read audience than the audit
store. So the value of tracing the answer path depends entirely on the span carrying
structural attributes only: which action, whose, which tenant. A question's free text, a
proposed intent, a SQL fragment, a figure, a refusal reason or a planted identifier
reaching a span has left the boundary the service's ``redact`` calls exist to hold, and it
has left it silently.

The content case drives the question whose text carries a planted NRIC, so the check runs
against input that would actually leak if any attribute were content-shaped. The refusal
cases matter as much as the answered one: a refusal must not explain itself on the span.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from nl2sql_analytics.config import build_container
from nl2sql_analytics.domain.analyst_service import AnalystService
from nl2sql_analytics.domain.models import AnalystAnswer, Question
from nl2sql_analytics.semantic_config import load_semantic_layer

from tests.conftest import local_settings
from tests.fixtures import sample_cases

#: Every attribute key the answer span is allowed to carry. A refusal that started
#: explaining itself on the span (a reason, a metric, a SQL fragment) would widen this set,
#: which is the point of asserting on the set rather than on the individual keys.
_ANSWER_KEYS = {"action", "actor", "tenant"}


class _RecordingTracer:
    """Captures every span name and attribute so the test can inspect what was emitted."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    @contextmanager
    def span(self, name: str, **attributes: str) -> Iterator[None]:
        self.spans.append((name, dict(attributes)))
        yield

    def record_token_usage(self, usage: object, model: str) -> None:
        return None


def _answer(question: Question) -> tuple[_RecordingTracer, AnalystAnswer]:
    """The REAL local adapters, exactly as ``assembly.analyst_service`` wires them."""
    tracer = _RecordingTracer()
    container = build_container(local_settings())
    service = AnalystService(
        layer=load_semantic_layer(container.settings),
        guardrail=container.guardrail,
        dictionary=container.dictionary,
        llm=container.llm,
        certification=container.certification,
        query_engine=container.query_engine,
        audit=container.audit,
        tracer=tracer,  # type: ignore[arg-type]
    )
    answer = service.answer(question, actor=sample_cases.ACTOR)
    return tracer, answer


def _emitted(tracer: _RecordingTracer) -> str:
    """Every attribute KEY and VALUE that was emitted, as one searchable blob."""
    parts: list[str] = []
    for name, attributes in tracer.spans:
        parts.append(name)
        parts.extend(attributes)
        parts.extend(attributes.values())
    return " ".join(parts)


def test_answering_a_question_opens_exactly_one_named_span() -> None:
    tracer, _ = _answer(sample_cases.CERTIFIED_QUESTION)
    assert [name for name, _ in tracer.spans] == ["nl2sql.answer"]


def test_the_span_carries_the_structural_attributes_an_operator_needs() -> None:
    """Enough to answer "whose questions are slow, in which tenant", and nothing more."""
    tracer, _ = _answer(sample_cases.CERTIFIED_QUESTION)
    _, attributes = tracer.spans[0]
    assert attributes["action"] == "answer"
    assert attributes["actor"] == sample_cases.ACTOR
    assert attributes["tenant"] == sample_cases.TENANT


@pytest.mark.parametrize(
    "question",
    [
        sample_cases.CERTIFIED_QUESTION,
        sample_cases.UNCERTIFIED_QUESTION,
        sample_cases.INJECTION_QUESTION,
        sample_cases.PII_QUESTION,
    ],
    ids=["answered", "refused", "screened", "pii"],
)
def test_the_attribute_set_is_a_fixed_allowlist_whatever_the_outcome(question: Question) -> None:
    """A refusal must not start attaching its reason, or the question, to the span."""
    tracer, _ = _answer(question)
    for _, attributes in tracer.spans:
        assert set(attributes) == _ANSWER_KEYS, (
            "a new span attribute appeared; confirm it is structural, then widen "
            "_ANSWER_KEYS here deliberately"
        )


def test_no_span_attribute_carries_question_content_or_the_planted_identifier() -> None:
    """The question used here has an NRIC planted in its text, so a leak would show."""
    tracer, answer = _answer(sample_cases.PII_QUESTION)
    emitted = _emitted(tracer).lower()
    forbidden = [
        sample_cases.PLANTED_NRIC,
        sample_cases.PII_QUESTION.text,
        "ops@gamma.example",
    ]
    if answer.sql:
        forbidden.append(answer.sql)
    if answer.summary:
        forbidden.append(answer.summary)
    for literal in forbidden:
        assert literal, "an empty needle would pass this test for the wrong reason"
        assert literal.lower() not in emitted, f"a span attribute carried {literal!r}"


def test_every_emitted_attribute_value_is_a_string_the_port_declares() -> None:
    """``span(name, **attributes: str)``: a non-string would serialise however the SDK felt."""
    tracer, _ = _answer(sample_cases.CERTIFIED_QUESTION)
    values = [v for _, attributes in tracer.spans for v in attributes.values()]
    assert values
    assert all(isinstance(value, str) for value in values)
