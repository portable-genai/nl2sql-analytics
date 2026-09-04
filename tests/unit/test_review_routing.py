"""Rule R8: an escalated answer is ROUTED to human-review-console, not left in a per-repo boolean.

This is the standing gate for the failure the rule exists to prevent. A repo can set
``requires_human_review = True``, pass every other test, and still auto-execute in practice
because nothing ever reads the flag. So the assertions here are about the ROUTING, not the flag:
a conditionally certified answer produces an outbound review, a certified answer produces none,
the payload leaves redacted, and the on-prem placeholder refuses rather than swallowing it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nl2sql_analytics.adapters.gcp.review_router import (
    CloudReviewRouter,
)
from nl2sql_analytics.adapters.local.review_router import (
    LocalReviewRouter,
)
from nl2sql_analytics.adapters.onprem.review_router import (
    OnPremReviewRouter,
)
from nl2sql_analytics.api.app import (
    app,
)
from nl2sql_analytics.assembly import build_analyst
from nl2sql_analytics.config import (
    Settings,
)
from nl2sql_analytics.domain.kernel import Citation, Decision, Severity
from nl2sql_analytics.domain.models import (
    AnalystAnswer,
    CertificationStatus,
    QueryResult,
    Question,
)


def _settings(profile: str = "local") -> Settings:
    return Settings(profile=profile, audit_path=":memory:", tenant="demo-bank")


def _escalating_answer() -> AnalystAnswer:
    _container, service = build_analyst(_settings())
    return service.answer(
        Question("How many active customers by segment?", "demo-bank"),
        actor="analyst@bank.example",
    )


def _pii_answer(planted: str) -> AnalystAnswer:
    """A contrived answer carrying a raw identifier in its summary and a citation, for the wire
    redaction proof: the review payload is built from these fields, so they must be masked."""
    return AnalystAnswer(
        question="q",
        subject="Total revenue",
        metric_id="revenue",
        certification_status=CertificationStatus.CONDITIONAL,
        severity=Severity.HIGH,
        decision=Decision.ESCALATED,
        summary=f"revenue for NRIC {planted}",
        sql="",
        result=QueryResult(columns=(), rows=()),
        requires_human_review=True,
        refused=False,
        citations=(Citation(source_id="metric:revenue", title="Total revenue", snippet=planted),),
    )


def test_an_escalated_answer_produces_an_outbound_review() -> None:
    router = LocalReviewRouter(_settings())
    ref = router.route(_escalating_answer(), maker="analyst@bank.example")
    assert ref, "routing must return a reference, so the caller can record where it went"
    pending = router.outbox.pending()
    assert len(pending) == 1
    review = pending[0].review
    assert review.maker == "analyst@bank.example"
    assert review.tenant == "demo-bank"
    assert review.severity == Severity.HIGH.value
    assert review.source_key, "a durable outbox needs an idempotency key"


def test_a_critical_answer_demands_dual_control() -> None:
    router = LocalReviewRouter(_settings())
    critical = AnalystAnswer(
        question="q",
        subject="Total revenue",
        metric_id="revenue",
        certification_status=CertificationStatus.CONDITIONAL,
        severity=Severity.CRITICAL,
        decision=Decision.ESCALATED,
        summary="s",
        sql="",
        result=QueryResult(columns=(), rows=()),
        requires_human_review=True,
        refused=False,
    )
    router.route(critical, maker="analyst@bank.example")
    assert router.outbox.pending()[0].review.required_approvals == 2


def test_the_payload_is_redacted_before_it_leaves_the_process() -> None:
    """human-review-console is a shared sink; a raw identifier must never reach the wire."""
    router = LocalReviewRouter(_settings())
    router.route(_pii_answer("S1234567D"), maker="analyst@bank.example")
    review = router.outbox.pending()[0].review
    wire = repr(review.to_payload())
    assert "S1234567D" not in wire
    assert "REDACTED" in wire


def test_the_managed_router_refuses_when_no_console_is_configured() -> None:
    """An escalation with nowhere to go must fail loudly, not return as if it were reviewed."""
    router = CloudReviewRouter(Settings(profile="gcp", audit_path=":memory:", review_url=""))
    with pytest.raises(RuntimeError, match="R8"):
        router.route(_escalating_answer(), maker="analyst@bank.example")


def test_the_onprem_placeholder_refuses_rather_than_dropping_the_escalation() -> None:
    router = OnPremReviewRouter(_settings("onprem"))
    with pytest.raises(NotImplementedError, match="R8"):
        router.route(_escalating_answer(), maker="analyst@bank.example")


def test_the_api_routes_the_escalation_in_the_same_request() -> None:
    """The serving path, not just the adapter: an escalation must not depend on a later job."""
    client = TestClient(app, client=("127.0.0.1", 50000))
    escalated = client.post(
        "/v1/ask",
        json={"question": "How many active customers by segment?"},
        headers={"X-Dev-Persona": "auditor"},
    ).json()
    assert escalated["requires_human_review"] is True
    assert escalated["review_ref"], "an escalation with no routing reference went nowhere"

    certified = client.post(
        "/v1/ask",
        json={"question": "What was total revenue by region?"},
        headers={"X-Dev-Persona": "auditor"},
    ).json()
    assert certified["requires_human_review"] is False
    assert certified["review_ref"] == "", "a certified answer must not manufacture a review"
