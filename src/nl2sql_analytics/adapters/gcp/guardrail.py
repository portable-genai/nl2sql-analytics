"""GCP GuardrailPort: screen every question through Model Armor (lazy imports).

Implements :class:`GuardrailPort` against **Model Armor**, the runtime AI-safety service of the
Gemini Enterprise Agent Platform, over its REST API. Each (already redacted) question is screened
with ``:sanitizeUserPrompt`` on the REGIONAL endpoint ``modelarmor.<region>.rep.googleapis.com``,
so screening stays inside the residency boundary, with a per-call deadline.

The verdict FAILS CLOSED. The question is ALLOWED only when the response says both
``filterMatchState: NO_MATCH_FOUND`` and ``invocationResult: SUCCESS`` (and no filter under it
reports a match). Everything else blocks:

- ``MATCH_FOUND`` (aggregate, or any single filter), and the reason names the matched filters;
- ``NO_MATCH_FOUND`` with ``invocationResult`` ``PARTIAL``, ``FAILURE``, unspecified or absent.
  A filter that was skipped (text over its token limit, an unsupported language, a detector
  error) reports ``EXECUTION_SKIPPED`` and no match, so "no match" from a screen that did not
  run every filter is not a clean pass: padding a question past the prompt-injection filter's
  limit is refused rather than let through unscreened;
- a missing, empty or malformed ``sanitizationResult``, and ``FILTER_MATCH_STATE_UNSPECIFIED``,
  whether it arrives by name or, as proto3 JSON may omit a zero-valued enum, as an absent field:
  a screen that did not say "no match" has not said "allowed";
- an API error (transport, HTTP status, auth, the deadline) raises; see below.

Both fields are compared as the exact enum NAME strings of the REST JSON mapping, never by
substring (``NO_MATCH_FOUND`` contains ``MATCH_FOUND``) and never by truthiness.

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
#: The one aggregate state that can allow.
_NO_MATCH_FOUND = "NO_MATCH_FOUND"
#: The one invocation result that can allow: every configured filter ran.
_ALL_FILTERS_RAN = "SUCCESS"
#: The per-call deadline: a stalled Model Armor raises, and the orchestrator refuses.
_TIMEOUT_SECONDS = 30.0


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
            timeout=_TIMEOUT_SECONDS,
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
        value = credentials.token
        if not value:
            raise RuntimeError("Application Default Credentials produced no bearer token")
        return str(value)

    return token


def _live_http_client() -> Any:  # pragma: no cover - live GCP
    import httpx

    return httpx.Client()


def parse_sanitize_response(response: Any) -> ScreenResult:
    """Map a ``sanitizeUserPrompt`` response onto an allow/block verdict, failing closed.

    Allowed ONLY on a complete, clean screen: ``filterMatchState`` is exactly ``NO_MATCH_FOUND``,
    ``invocationResult`` is exactly ``SUCCESS``, and no filter result reports ``MATCH_FOUND``.
    A match blocks however many filters ran; a missing or unspecified decision blocks; an
    incomplete screen (``PARTIAL``, ``FAILURE``, unspecified or absent) blocks. The reason names
    the matched filters (``pi_and_jailbreak``, ``sdp``, ``malicious_uris``, ``rai``, ``csam``) or
    the missing decision, never the text.
    """
    body = response if isinstance(response, dict) else {}
    result = body.get("sanitizationResult")
    if not isinstance(result, dict):
        result = {}
    filters = result.get("filterResults")
    matched = (
        sorted(str(name) for name, node in filters.items() if _reports_a_match(node))
        if isinstance(filters, dict)
        else []
    )
    state = result.get("filterMatchState")
    invocation = result.get("invocationResult")
    if state == _NO_MATCH_FOUND and invocation == _ALL_FILTERS_RAN and not matched:
        return ScreenResult(allowed=True, reason="no blocking Model Armor filter matched")
    if state == _MATCH_FOUND or matched:
        detail = ", ".join(matched) if matched else "a filter"
        return ScreenResult(allowed=False, reason=f"Model Armor matched {detail}")
    if state == _NO_MATCH_FOUND:
        return ScreenResult(
            allowed=False,
            reason=(
                "Model Armor returned no complete filter decision "
                f"(invocationResult={_named(invocation)}): not every filter ran"
            ),
        )
    return ScreenResult(
        allowed=False,
        reason=f"Model Armor returned no filter decision (filterMatchState={_named(state)})",
    )


def _named(value: Any) -> str:
    """The enum name as reported, or ``absent``; bounded so a hostile body cannot flood a log."""
    return str(value)[:64] if value is not None else "absent"


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
