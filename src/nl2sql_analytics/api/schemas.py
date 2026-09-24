"""API request/response schemas (Pydantic) mapped to/from the pure-domain models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..domain.models import AnalystAnswer


class AskRequest(BaseModel):
    """One governed analytical question. The tenant is taken from the verified principal, never
    from the body: a caller cannot widen its own row-level access by asserting a tenant here."""

    question: str


class CitationModel(BaseModel):
    source_id: str
    title: str
    snippet: str = ""


class ResultTable(BaseModel):
    columns: list[str] = []
    rows: list[list[str]] = []


class AskResponse(BaseModel):
    question: str
    #: The certified metric answered, or "" when the question was refused.
    metric_id: str
    certification_status: str
    refused: bool
    #: The typed refusal reason, or "" when the question was answered.
    refusal_reason: str = ""
    #: The certified metrics a caller may ask instead, when refused.
    alternatives: list[str] = []
    summary: str
    #: The composed, validated SQL that ran, or "" when refused. Free-form model SQL never runs.
    sql: str = ""
    result: ResultTable = ResultTable()
    caveats: list[str] = []
    requires_human_review: bool
    #: Where the escalation WENT (rule R8): the human-review-console review id, or the local queue
    #: reference. Empty exactly when ``review_routing`` is not ``routed``.
    review_ref: str = ""
    #: What happened to the hand-off: routed, failed, off or not_required. ``failed`` means the
    #: answer is NOT queued for review, and the console says so.
    review_routing: Literal["routed", "failed", "off", "not_required"] = "not_required"
    citations: list[CitationModel] = []

    @classmethod
    def from_domain(
        cls,
        answer: AnalystAnswer,
        *,
        review_ref: str = "",
        review_routing: str = "not_required",
    ) -> AskResponse:
        refusal = answer.refusal
        return cls(
            question=answer.question,
            metric_id=answer.metric_id,
            certification_status=answer.certification_status.value,
            refused=answer.refused,
            refusal_reason=refusal.reason if refusal is not None else "",
            alternatives=list(refusal.alternatives) if refusal is not None else [],
            summary=answer.summary,
            sql=answer.sql,
            result=ResultTable(
                columns=list(answer.result.columns),
                rows=[list(row) for row in answer.result.rows],
            ),
            caveats=list(answer.caveats),
            requires_human_review=answer.requires_human_review,
            review_ref=review_ref,
            review_routing=review_routing,  # type: ignore[arg-type]
            citations=[
                CitationModel(source_id=c.source_id, title=c.title, snippet=c.snippet)
                for c in answer.citations
            ],
        )


class HealthResponse(BaseModel):
    status: str
    profile: str
    region: str
    #: Provenance the UI banner states on every page: where the runtime sits and which model
    #: answers. Both are read off the service because the browser cannot know either.
    runtime: str = "local"  # "gcp" | "local"
    generator_model: str = "deterministic-offline-stub"
