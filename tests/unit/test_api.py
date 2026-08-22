"""API surface: verified-principal identity, fail-closed S2S, security headers.

The client comes from the shared ``api_client`` fixture, which pins a loopback peer: the
app-object exposure guard refuses the unauthenticated local posture to any other peer, and
TestClient's default peer is the literal host "testclient".
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

_TOKEN_ENV = "NL2SQL_S2S_TOKEN"


def test_a_certified_question_answers_and_cites(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/ask",
        json={"question": "What was total revenue by region?"},
        headers={"X-Dev-Persona": "auditor"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["refused"] is False
    assert body["metric_id"] == "revenue"
    assert body["certification_status"] == "certified"
    assert body["requires_human_review"] is False
    assert body["review_ref"] == "", "a fully certified answer must not manufacture a review"
    assert "SELECT" in body["sql"]
    assert any(c["source_id"] == "metric:revenue" for c in body["citations"])


def test_a_conditionally_certified_answer_escalates_and_routes(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/ask",
        json={"question": "How many active customers by segment?"},
        headers={"X-Dev-Persona": "auditor"},
    )
    body = resp.json()
    assert body["metric_id"] == "active_customers"
    assert body["requires_human_review"] is True
    # Rule R8: the escalation was routed, not merely flagged (see test_review_routing.py).
    assert body["review_ref"], "a conditionally certified answer was flagged but not routed"


def test_an_uncertified_metric_is_refused_with_alternatives(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/ask",
        json={"question": "Show me profit margin by region"},
        headers={"X-Dev-Persona": "auditor"},
    )
    body = resp.json()
    assert body["refused"] is True
    assert body["metric_id"] == ""
    assert body["sql"] == "", "a refused question must never run SQL"
    assert "revenue" in body["alternatives"]


def test_unknown_persona_is_401(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/ask",
        json={"question": "What was total revenue by region?"},
        headers={"X-Dev-Persona": "ghost"},
    )
    assert resp.status_code == 401


def test_healthz_reports_profile_and_region(api_client: TestClient) -> None:
    body = api_client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["profile"] == "local"
    assert body["region"] == "asia-southeast1"


def test_security_headers_present(api_client: TestClient) -> None:
    headers = api_client.get("/healthz").headers
    assert headers["Content-Security-Policy"] == "frame-ancestors 'self'"
    assert headers["X-Content-Type-Options"] == "nosniff"


@pytest.fixture()
def token_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv(_TOKEN_ENV, "s3cret-service-token")
    yield "s3cret-service-token"


def test_s2s_endpoint_open_when_secret_unset(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(_TOKEN_ENV, raising=False)
    assert api_client.post("/v1/audit/ping").status_code == 200


def test_s2s_endpoint_rejects_missing_token_when_enforced(
    api_client: TestClient, token_env: str
) -> None:
    assert api_client.post("/v1/audit/ping").status_code == 401


def test_s2s_endpoint_accepts_correct_token(api_client: TestClient, token_env: str) -> None:
    resp = api_client.post("/v1/audit/ping", headers={"Authorization": f"Bearer {token_env}"})
    assert resp.status_code == 200
