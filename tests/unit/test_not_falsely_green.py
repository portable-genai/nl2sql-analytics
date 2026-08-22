"""Prove every h1-nl2sql bundle metric can go RED, with the SAME scorer the gate runs.

A metric that cannot fail is not a metric: it is a green light wired to nothing. For each metric
in the bundle this drives ``agent_eval_kit.assert_each_can_go_red`` over a clean (green) and a
degraded (red) observation, using the exact scorer ``eval/run_eval.py`` uses, so a metric proven
red here is the one that actually runs. Each scorer compares against the DATASET'S OWN oracle
(the golden expectation), never the pipeline's own answer.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any

from agent_eval_kit import assert_can_go_red, assert_each_can_go_red
from pii_kit import pack_leak, redact

from nl2sql_analytics.domain.pii import (
    PII_PATTERNS,
)

from tests import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "eval"))
import run_eval  # noqa: E402 - loaded from eval/ after the path is extended above

#: Per metric: the golden expectation, a clean observation that must PASS, and a degraded one
#: that must FAIL. The scorer is the same callable the gate runs (run_eval.SCORERS).
_CASES: dict[str, tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]] = {
    "resolver_accuracy": (
        {"expected_metric": "revenue"},
        {"metric_id": "revenue"},
        {"metric_id": "profit_margin"},
    ),
    "refusal_completeness": (
        {"expected_refuse": True},
        {"refused": True},
        {"refused": False},
    ),
    "sql_correctness": (
        {"expected_numbers": ["3000", "1300"]},
        {"result_numbers": {"3000", "1300"}},
        {"result_numbers": {"9999"}},
    ),
    "citation_accuracy": (
        {"expected_metric": "revenue"},
        {"citation_metrics": {"revenue"}},
        {"citation_metrics": set()},
    ),
    "answer_groundedness": (
        {"expected_numbers": ["3000", "1300"]},
        {"summary_numbers": {"3000", "1300", "2"}},
        {"summary_numbers": {"9999"}},
    ),
    "review_safety": (
        {"expected_review": True},
        {"review": True},
        {"review": False},
    ),
}


def test_every_bundle_metric_can_go_red() -> None:
    for name, (golden, green, red) in _CASES.items():

        def _score(
            observed: Mapping[str, Any],
            _scorer: Any = run_eval.SCORERS[name],
            _golden: Mapping[str, Any] = golden,
        ) -> float:
            return float(_scorer(_golden, observed))

        assert_each_can_go_red(
            _score,
            {"h1": (green, red)},
            threshold=run_eval.THRESHOLDS[name],
            metric=name,
        )


_RAW_SUMMARY = "revenue for NRIC S1234567D on file at ops@fictional.example"


def _pii_safety(summary: str) -> float:
    """1.0 unless a raw identifier (per the shared pack) survives into the summary."""
    return 0.0 if pack_leak(summary, PII_PATTERNS) else 1.0


def test_pii_safety_can_go_red() -> None:
    assert_can_go_red(
        _pii_safety,
        green=redact(_RAW_SUMMARY, PII_PATTERNS),  # redaction on: the NRIC is masked
        red=_RAW_SUMMARY,  # redaction off (the mutant): the raw NRIC survives
        threshold=0.99,
        metric="pii_safety",
    )
