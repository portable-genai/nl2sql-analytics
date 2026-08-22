"""Groundedness checks for model narration: a figure the result does not contain is discarded.

The model narrates; it never produces a number. This module enforces that on the OUTPUT side: a
narrated summary is accepted only if every number in it also appears in the query result (or is
the row count). A summary that invents a figure is DISCARDED and replaced with a deterministic
caveated one, so a fabricated number can never reach a caller, whichever model produced the text.

Pure stdlib. ``allowed_figures`` is built from the result table by the caller, so this module has
no view of the pipeline's own verdict; it only compares text against a set of permitted numbers.
"""

from __future__ import annotations

import re

from .models import QueryResult

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
#: A narrated summary longer than this is rejected as unbounded and replaced deterministically.
MAX_SUMMARY_CHARS = 400


def _normalise(token: str) -> str:
    """Canonicalise a numeric token so ``3000`` and ``3000.0`` compare equal."""
    if "." in token:
        token = token.rstrip("0").rstrip(".")
    return token or "0"


def numbers_in(text: str) -> set[str]:
    """Every numeric token in ``text``, normalised."""
    return {_normalise(match.group(0)) for match in _NUMBER.finditer(text)}


def allowed_figures(result: QueryResult) -> set[str]:
    """The set of numbers a grounded summary may contain: every result cell, plus the row count."""
    figures: set[str] = {_normalise(str(len(result.rows)))}
    for row in result.rows:
        for cell in row:
            for match in _NUMBER.finditer(str(cell)):
                figures.add(_normalise(match.group(0)))
    return figures


def is_grounded(summary: str, result: QueryResult) -> bool:
    """True when the summary is bounded in length and invents no figure the result lacks."""
    if not summary.strip() or len(summary) > MAX_SUMMARY_CHARS:
        return False
    return numbers_in(summary) <= allowed_figures(result)
