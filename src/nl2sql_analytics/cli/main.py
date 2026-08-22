"""Minimal stdlib CLI: ask a governed question (argparse, no extra deps)."""

from __future__ import annotations

import argparse
import sys

from ..assembly import build_analyst
from ..domain.models import Question


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nl2sql_analytics")
    sub = parser.add_subparsers(dest="command", required=True)

    ask_cmd = sub.add_parser("ask", help="Ask one governed analytical question.")
    ask_cmd.add_argument("question")
    ask_cmd.add_argument("--actor", default="cli-user@bank.example")
    ask_cmd.add_argument("--tenant", default="demo-bank", help="Tenant the query scopes to.")

    args = parser.parse_args(argv)
    container, service = build_analyst()

    if args.command == "ask":
        answer = service.answer(Question(text=args.question, tenant=args.tenant), actor=args.actor)
        if answer.refused:
            print(f"REFUSED: {answer.summary}")
            if answer.refusal is not None and answer.refusal.alternatives:
                print("  certified alternatives: " + ", ".join(answer.refusal.alternatives))
            return 0
        print(f"{answer.subject} ({answer.certification_status.value}): {answer.summary}")
        print(f"  sql: {answer.sql}")
        for citation in answer.citations:
            print(f"  cite: {citation.source_id} ({citation.snippet})")
        if answer.requires_human_review:
            # Rule R8 on the CLI path too: the same escalation, the same router. A surface that
            # only printed the flag would be a second place for an escalation to stop.
            ref = container.review_router.route(answer, maker=args.actor, tenant=args.tenant)
            print(f"  routed to human review: {ref}")
        return 0

    return 2  # pragma: no cover - argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
