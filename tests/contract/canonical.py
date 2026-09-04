"""ONE canonical request per port, shared by the structural and behavioural contract suites.

Parity means the same request through every implementation, so the request needs a single home.
Retyping it per suite is how two "parity" tests end up asserting different things.

Each :class:`PortCase` answers three questions about one port:

* ``invoke``   : what a single canonical call to this port looks like;
* ``answered`` : what it means for the OFFLINE family to have actually answered (a port that
  returns ``None`` and records nothing has not answered, it has merely not raised);
* ``managed_refusal`` : what the MANAGED family must do when called with no cloud reachable.
  Never a silent success: either it refuses because it is unconfigured, or its lazy SDK import
  fails. Both are honest; returning as if the work happened is not.

Adding a port means adding a case here. ``test_port_parity.py`` fails the build if this table
and the port map ever disagree, so the touch list in ``CONTRIBUTING.md`` is enforced rather than
merely written down.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_eval_kit import EvalReport
from hex_service_kit.identity import IdentityError, Principal, RequestContext
from hex_service_kit.observability import TokenUsage

from nl2sql_analytics.domain.kernel import (
    AuditEvent,
    Citation,
    Decision,
    Severity,
)
from nl2sql_analytics.domain.models import CertificationStatus

from tests.fixtures import sample_cases

#: The audit record every audit-port implementation is handed. Already redacted, as the port
#: requires: a raw identifier must never reach a WORM record.
CANONICAL_EVENT = AuditEvent(
    action="analyst_answer",
    actor=sample_cases.ACTOR,
    decision=Decision.ESCALATED,
    severity=Severity.HIGH,
    redacted_summary="Active customers: 2 row(s)",
    citations=(Citation(source_id="metric:active_customers", title="Active customers"),),
)

#: The escalated answer every review-router implementation is handed (rule R8's payload).
CANONICAL_RESULT = sample_cases.CANONICAL_ANSWER

#: The inbound transport context every identity implementation is handed.
CANONICAL_CONTEXT = RequestContext(headers={"x-dev-persona": "auditor"})


@dataclass(frozen=True, slots=True)
class PortCase:
    """One port's canonical call plus the two verdicts the parity suites need."""

    invoke: Callable[[Any], Any]
    answered: Callable[[Any, Any], bool]
    managed_refusal: tuple[type[BaseException], ...]
    detail: str


def _audit_invoke(adapter: Any) -> Any:
    return adapter.record(CANONICAL_EVENT)


def _audit_answered(adapter: Any, _result: Any) -> bool:
    stored = adapter.log.read_all()
    return bool(stored) and stored[-1]["actor"] == sample_cases.ACTOR and adapter.verify().ok


def _identity_invoke(adapter: Any) -> Any:
    return adapter.resolve(CANONICAL_CONTEXT)


def _identity_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, Principal) and bool(result.actor)


def _review_invoke(adapter: Any) -> Any:
    return adapter.route(CANONICAL_RESULT, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)


def _review_answered(adapter: Any, result: Any) -> bool:
    return bool(result) and len(adapter.outbox.pending()) == 1


def _certification_invoke(adapter: Any) -> Any:
    return adapter.dataset_status("orders_daily")


def _certification_answered(_adapter: Any, result: Any) -> bool:
    return result.status is CertificationStatus.CERTIFIED and "revenue" in result.certified_metrics


def _dictionary_invoke(adapter: Any) -> Any:
    return adapter.lookup("total revenue by region")


def _dictionary_answered(_adapter: Any, result: Any) -> bool:
    return any(hit.metric_id == "revenue" for hit in result)


def _llm_invoke(adapter: Any) -> Any:
    return adapter.propose_intent("total revenue by region", ())


def _llm_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, dict) and result.get("metric_id") == "revenue"


def _query_engine_invoke(adapter: Any) -> Any:
    return adapter.execute(sample_cases.CANONICAL_QUERY)


def _query_engine_answered(_adapter: Any, result: Any) -> bool:
    return bool(result.rows) and "region" in result.columns


def _guardrail_invoke(adapter: Any) -> Any:
    return adapter.screen("total revenue by region")


def _guardrail_answered(_adapter: Any, result: Any) -> bool:
    return result.allowed is True


def _channel_invoke(adapter: Any) -> Any:
    return adapter.deliver(CANONICAL_RESULT)


def _channel_answered(adapter: Any, result: Any) -> bool:
    return bool(result) and len(adapter.transcript) == 1


def _tracer_invoke(adapter: Any) -> Any:
    with adapter.span("canonical.unit", action="canonical"):
        adapter.record_token_usage(TokenUsage(input_tokens=7, output_tokens=2), "canonical-model")
    return True


def _tracer_answered(adapter: Any, result: Any) -> bool:
    return bool(result)


def _evaluation_invoke(adapter: Any) -> Any:
    return adapter.evaluate("eval/datasets/canonical.jsonl")


def _evaluation_answered(adapter: Any, result: Any) -> bool:
    return isinstance(result, EvalReport) and result.dataset.endswith("canonical.jsonl")


CANONICAL_CALLS: dict[str, PortCase] = {
    "audit": PortCase(
        invoke=_audit_invoke,
        answered=_audit_answered,
        # The lazy `google.cloud` import is the first thing the managed sink does.
        managed_refusal=(ImportError,),
        detail="write one already-redacted WORM record",
    ),
    "identity": PortCase(
        invoke=_identity_invoke,
        answered=_identity_answered,
        # No IAP assertion header offline, so the managed adapter refuses before importing.
        managed_refusal=(IdentityError,),
        detail="resolve a verified principal from transport context",
    ),
    "review_router": PortCase(
        invoke=_review_invoke,
        answered=_review_answered,
        # Rule R8: with no console configured the managed router must refuse, not swallow.
        managed_refusal=(RuntimeError,),
        detail="route one escalated answer to human review",
    ),
    "certification": PortCase(
        invoke=_certification_invoke,
        answered=_certification_answered,
        # The lazy `google.auth` import is the first thing the managed adapter does.
        managed_refusal=(ImportError,),
        detail="report a dataset's certification status",
    ),
    "dictionary": PortCase(
        invoke=_dictionary_invoke,
        answered=_dictionary_answered,
        managed_refusal=(ImportError,),
        detail="return data-dictionary hints for a question",
    ),
    "llm": PortCase(
        invoke=_llm_invoke,
        answered=_llm_answered,
        managed_refusal=(ImportError,),
        detail="propose a schema-valid analytical intent",
    ),
    "query_engine": PortCase(
        invoke=_query_engine_invoke,
        answered=_query_engine_answered,
        managed_refusal=(ImportError,),
        detail="execute a composed query and return rows",
    ),
    "guardrail": PortCase(
        invoke=_guardrail_invoke,
        answered=_guardrail_answered,
        managed_refusal=(ImportError,),
        detail="screen a question before generation",
    ),
    "channel": PortCase(
        invoke=_channel_invoke,
        answered=_channel_answered,
        managed_refusal=(ImportError,),
        detail="deliver a finished answer to the channel",
    ),
    "tracer": PortCase(
        invoke=_tracer_invoke,
        answered=_tracer_answered,
        # NOTHING. Tracing is not essential to correctness, so the managed adapter must not refuse
        # offline either: with no SDK it degrades to a no-op and the traced body still runs. An
        # adapter that raised here would take a request down over a diagnostic.
        managed_refusal=(),
        detail="open one span and report the cost of a model call",
    ),
    "evaluation": PortCase(
        invoke=_evaluation_invoke,
        answered=_evaluation_answered,
        # The managed gate reaches model-quality-gate over HTTP, which is unreachable offline.
        managed_refusal=(Exception,),
        detail="score one golden dataset through the promotion authority",
    ),
}
