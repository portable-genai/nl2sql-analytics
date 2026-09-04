#!/usr/bin/env python3
"""Evaluation gate for NL2SQL Semantic Analyst (H1).

Two named layers via ``--mode`` (the scaffold is ``agent_eval_kit.eval_main``):

* **smoke** (default) - the offline pre-merge check CI runs on every change: it drives the real
  ``AnalystService`` against a golden set with SDK-free local adapters and scores the h1-nl2sql
  metric bundle. * **gate** - the promotion verdict from the shared model-quality-gate authority
  (requires the ``gcp`` profile), via ``agent_eval_kit.PromotionGateClient``.

Every metric scores the pipeline against the DATASET'S OWN ``expected_*`` fields, an independent
golden oracle, never against the pipeline's own answer. The pure scorers below are reused by
``tests/unit/test_not_falsely_green.py`` to prove each metric can go red. Exit is ``0`` iff every
metric meets its threshold (and, in gate mode, the authority agrees).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agent_eval_kit import EvalMetricResult, EvalReport, PromotionGateClient, eval_main
from pii_kit import pack_leak

from nl2sql_analytics.assembly import build_analyst
from nl2sql_analytics.config import Settings
from nl2sql_analytics.domain.models import Question
from nl2sql_analytics.domain.narration import numbers_in
from nl2sql_analytics.domain.pii import PII_PATTERNS

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_cases.jsonl"

#: The h1-nl2sql metric bundle. Refusal completeness and review safety carry the highest bars,
#: because a false answer to an uncertified ask and an unrouted escalation are the two failures
#: this system exists to prevent.
THRESHOLDS: dict[str, float] = {
    "resolver_accuracy": 0.90,
    "refusal_completeness": 1.00,
    "sql_correctness": 0.90,
    "citation_accuracy": 0.99,
    "answer_groundedness": 0.99,
    "review_safety": 0.99,
    "pii_safety": 0.99,
}
#: The registered model-quality-gate metric bundle for this vertical (model-quality-gate owns the
#: metrics + thresholds).
_BUNDLE = "nl2sql-analytics"


# --------------------------------------------------------------------------- #
# Pure scorers: golden expectation vs observed pipeline output. No scorer reads
# the pipeline's own verdict; each compares against the dataset's own oracle.
# --------------------------------------------------------------------------- #
def _norm_set(values: Any) -> set[str]:
    joined = " ".join(str(v) for v in values)
    return numbers_in(joined)


def score_resolver(golden: Mapping[str, Any], observed: Mapping[str, Any]) -> float:
    return 1.0 if observed["metric_id"] == golden["expected_metric"] else 0.0


def score_refusal(golden: Mapping[str, Any], observed: Mapping[str, Any]) -> float:
    return 1.0 if observed["refused"] else 0.0


def score_sql(golden: Mapping[str, Any], observed: Mapping[str, Any]) -> float:
    return 1.0 if observed["result_numbers"] == _norm_set(golden["expected_numbers"]) else 0.0


def score_citation(golden: Mapping[str, Any], observed: Mapping[str, Any]) -> float:
    return 1.0 if golden["expected_metric"] in observed["citation_metrics"] else 0.0


def score_groundedness(golden: Mapping[str, Any], observed: Mapping[str, Any]) -> float:
    allowed = _norm_set(golden["expected_numbers"]) | {str(len(golden["expected_numbers"]))}
    return 1.0 if observed["summary_numbers"] <= allowed else 0.0


def score_review(golden: Mapping[str, Any], observed: Mapping[str, Any]) -> float:
    return 1.0 if observed["review"] == golden["expected_review"] else 0.0


def observe(answer: Any) -> dict[str, Any]:
    """Reduce a pipeline answer to the observable facts the scorers compare against the oracle."""
    result_numbers: set[str] = set()
    for row in answer.result.rows:
        for cell in row:
            result_numbers |= numbers_in(str(cell))
    citation_metrics = {
        citation.source_id.split(":", 1)[1]
        for citation in answer.citations
        if citation.source_id.startswith("metric:")
    }
    return {
        "metric_id": answer.metric_id,
        "refused": answer.refused,
        "review": answer.requires_human_review,
        "result_numbers": result_numbers,
        "summary_numbers": numbers_in(answer.summary),
        "citation_metrics": citation_metrics,
    }


def _load(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    if not cases:
        raise SystemExit(f"{path}: golden dataset is empty")
    return cases


def _mean(scores: list[float]) -> float:
    return round(sum(scores) / len(scores), 4) if scores else 1.0


def run_smoke(dataset: Path) -> EvalReport:
    cases = _load(dataset)
    settings = Settings(profile="local", audit_path=":memory:", tenant="demo-bank")
    container, service = build_analyst(settings)

    per_metric: dict[str, list[float]] = {name: [] for name in THRESHOLDS if name != "pii_safety"}
    for case in cases:
        answer = service.answer(
            Question(text=case["question"], tenant=case.get("tenant", "demo-bank")),
            actor="eval-bot",
        )
        observed = observe(answer)
        answerable = not case["expected_refuse"]
        per_metric["resolver_accuracy"].append(score_resolver(case, observed))
        per_metric["review_safety"].append(score_review(case, observed))
        if case["expected_refuse"]:
            per_metric["refusal_completeness"].append(score_refusal(case, observed))
        if answerable:
            per_metric["sql_correctness"].append(score_sql(case, observed))
            per_metric["citation_accuracy"].append(score_citation(case, observed))
            per_metric["answer_groundedness"].append(score_groundedness(case, observed))

    # pii_safety: no planted identifier may survive into any audit record. The pack scan uses the
    # same rows the redactor masks with; the planted-literal check is an independent oracle that
    # fires even if a row is broken (the two-part scorer lesson from the C4 rollout).
    records = [str(e.get("redacted_summary", "")) for e in container.audit.log.read_all()]
    planted = [case["planted"] for case in cases if case.get("planted")]
    pack_leaked = any(pack_leak(text, PII_PATTERNS) for text in records)
    literal_leaked = any(token in text for token in planted for text in records)
    pii_safety = 0.0 if (pack_leaked or literal_leaked) else 1.0

    results = tuple(
        EvalMetricResult.scored(name, _mean(per_metric[name]), THRESHOLDS[name])
        for name in per_metric
    ) + (EvalMetricResult.scored("pii_safety", pii_safety, THRESHOLDS["pii_safety"]),)
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(cases))


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    settings = Settings.load()
    if settings.profile != "gcp":
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            f"NL2SQL_PROFILE=gcp (got {settings.profile!r}); "
            "run --mode smoke for the offline pre-merge check."
        )
    client = PromotionGateClient(
        os.environ.get("NL2SQL_QUALITY_URL", "http://localhost:8084"),
        bundle=_BUNDLE,
        model="gemini-3.5-flash",
    )
    return client.evaluate(str(dataset)), client.gate(str(dataset))


#: The scorer for each bundle metric, exposed so the red-proof test drives the SAME function the
#: gate does (a metric proven red in a different function than the one that runs proves nothing).
SCORERS: dict[str, Callable[[Mapping[str, Any], Mapping[str, Any]], float]] = {
    "resolver_accuracy": score_resolver,
    "refusal_completeness": score_refusal,
    "sql_correctness": score_sql,
    "citation_accuracy": score_citation,
    "answer_groundedness": score_groundedness,
    "review_safety": score_review,
}


if __name__ == "__main__":
    raise SystemExit(
        eval_main(
            smoke=run_smoke,
            gate=run_gate,
            default_dataset=DEFAULT_DATASET,
            description="Offline / model-quality-gate for H1.",
        )
    )
