"""GCP GuardrailPort: screen every question through Model Armor (lazy imports).

Implements :class:`GuardrailPort` against **Model Armor**, the runtime AI-safety service of the
Gemini Enterprise Agent Platform, over its REST API. Each (already redacted) question is screened
with ``:sanitizeUserPrompt`` on the REGIONAL endpoint ``modelarmor.<region>.rep.googleapis.com``,
so screening stays inside the residency boundary. The question is BLOCKED when Model Armor
reports ``filterMatchState: MATCH_FOUND`` (or, if that aggregate is absent, when any filter
reports a match), and the reason names the filters that matched.

The template and project come from settings (``NL2SQL_MODEL_ARMOR_TEMPLATE`` and
``GOOGLE_CLOUD_PROJECT``). With the guardrail on under ``gcp`` an empty one refuses at boot
(``config._refuse_unconfigured_controls``), so a served process never builds a malformed URL; a
caller that builds this adapter directly with either empty gets a ``RuntimeError`` from
:meth:`screen` before any request is made.

``google-auth`` is imported FIRST and lazily, on the first screen, so the offline profiles import
this module with no cloud SDK installed and a screen there refuses with ``ImportError`` rather
than reaching the network. A tests-only ``client`` and ``token`` may be injected; the container
passes neither. Any error here (transport, HTTP status, auth) raises, and
the orchestrator reads that as "screen unavailable" and refuses the question: an unreachable
screen fails closed, never open.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...config import Settings
from ...domain.models import ScreenResult

_MATCH_FOUND = "MATCH_FOUND"


class CloudGuardrailAdapter:
    """Screen a question through Model Armor's regional REST API."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: Any | None = None,
        token: Callable[[], str] | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._token = token

    def screen(self, text: str) -> ScreenResult:
        """Screen one (already redacted) question; ``allowed`` false means do not answer it."""
        token = self._bearer_token()
        url = self._url()
        response = self._http_client().post(
            url,
            json={"userPromptData": {"text": text}},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return parse_sanitize_response(response.json())

    def _url(self) -> str:
        template = self._settings.model_armor_template.strip()
        project = self._settings.project_id.strip()
        if not template or not project:
            raise RuntimeError(
                "the Model Armor guardrail needs a template and a project; set "
                "NL2SQL_MODEL_ARMOR_TEMPLATE and GOOGLE_CLOUD_PROJECT, or NL2SQL_GUARDRAIL=off"
            )
        region = self._settings.region
        return (
            f"https://modelarmor.{region}.rep.googleapis.com/v1/projects/{project}"
            f"/locations/{region}/templates/{template}:sanitizeUserPrompt"
        )

    def _http_client(self) -> Any:
        if self._client is None:
            self._client = _live_http_client()
        return self._client

    def _bearer_token(self) -> str:
        if self._token is None:
            self._token = _adc_token_source()
        return self._token()


def _adc_token_source() -> Callable[[], str]:  # pragma: no cover - live GCP
    """A bearer-token source over Application Default Credentials, refreshed when stale.

    ``google.auth`` is imported here, on the first screen, so the offline profiles import this
    module with no SDK and a screen there raises ``ImportError`` before any request is built.
    """
    import google.auth
    from google.auth.transport.requests import Request

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    request = Request()

    def token() -> str:
        if not credentials.valid:
            credentials.refresh(request)
        value: str = credentials.token
        return value

    return token


def _live_http_client() -> Any:  # pragma: no cover - live GCP
    import httpx

    return httpx.Client()


def parse_sanitize_response(response: dict[str, Any]) -> ScreenResult:
    """Map a ``sanitizeUserPrompt`` response onto an allow/block verdict.

    Blocks when the aggregate ``filterMatchState`` is ``MATCH_FOUND``; when the aggregate is
    absent, blocks when any filter result reports a match. The reason names the matched filters
    (``pi_and_jailbreak``, ``sdp``, ``malicious_uris``, ``rai``, ``csam``), never the text.
    """
    result = response.get("sanitizationResult") or {}
    filters = result.get("filterResults") or {}
    matched = sorted(str(name) for name, node in filters.items() if _reports_a_match(node))
    state = result.get("filterMatchState")
    allowed = state != _MATCH_FOUND if state is not None else not matched
    if allowed:
        return ScreenResult(allowed=True, reason="no blocking Model Armor filter matched")
    detail = ", ".join(matched) if matched else "a filter"
    return ScreenResult(allowed=False, reason=f"Model Armor matched {detail}")


def _reports_a_match(node: Any) -> bool:
    """True when any ``matchState`` under ``node`` is exactly ``MATCH_FOUND``.

    Compared exactly, never as a substring: the negative state is ``NO_MATCH_FOUND``, which
    contains ``MATCH_FOUND``, so a substring test would name every filter that ran.
    """
    if isinstance(node, dict):
        if node.get("matchState") == _MATCH_FOUND:
            return True
        return any(_reports_a_match(value) for value in node.values())
    if isinstance(node, list):
        return any(_reports_a_match(value) for value in node)
    return False
