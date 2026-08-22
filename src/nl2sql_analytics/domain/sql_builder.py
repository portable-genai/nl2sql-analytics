"""The deterministic SQL composer and validator: the model proposes, this engine authorises.

Pure stdlib. A :class:`ResolvedIntent` (already certified by the resolver) is COMPOSED into a
bounded, read-only ``SELECT`` from the metric's certified fragment and the dataset's certified
columns alone. No free-form model SQL ever reaches this module and none ever executes: the query
is BUILT here, from certified pieces, which makes the "only certified surface" guarantee
structural rather than a thing a parser has to police after the fact.

Two properties the query engine relies on, both enforced here before a :class:`CompiledQuery` is
returned:

* **Row-level access is injected, not optional.** A tenant-scoped dataset gets a
  ``WHERE <tenant_column> = :tenant`` predicate with the tenant BOUND as a parameter. A test goes
  red if the predicate is dropped, because the fixture warehouse holds another tenant's rows and
  they reappear the moment the predicate is gone.
* **The result is validated and bounded.** :func:`validate_sql` refuses anything that is not a
  single read-only ``SELECT`` carrying a ``LIMIT`` and touching only the certified table and
  columns. It runs on the composed text, so a future composition bug that reached an uncertified
  column is caught before execution, not after.

Identifiers (table, dimension and filter-column names) come only from the CERTIFIED layer's
closed allow-lists, so they are safe to place in the text; every caller-supplied VALUE (the
tenant, each filter value) is a bound parameter and never interpolated.
"""

from __future__ import annotations

import re

from .models import CompiledQuery, ResolvedIntent

#: Tokens that must never appear in a composed query. It is read-only analytics: no statement that
#: writes, changes schema, attaches a file or chains a second statement is ever legitimate here.
_FORBIDDEN = re.compile(
    r"(?i)(?<![A-Za-z_])(?:DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|REPLACE|ATTACH|PRAGMA|"
    r"VACUUM|GRANT|TRUNCATE)(?![A-Za-z_])"
)
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class UnsafeQueryError(ValueError):
    """A composed query failed validation: not a bounded, read-only, certified-surface SELECT."""


def _columns_referenced(expression: str, dataset_columns: tuple[str, ...]) -> set[str]:
    """Which certified columns an expression names (word-boundary match against the allow-list)."""
    present: set[str] = set()
    for column in dataset_columns:
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(column)}(?![A-Za-z0-9_])", expression):
            present.add(column)
    return present


def validate_sql(
    sql: str, *, allowed_table: str, allowed_columns: tuple[str, ...], require_limit: bool = True
) -> None:
    """Raise :class:`UnsafeQueryError` unless ``sql`` is a bounded, read-only, certified SELECT.

    This is the deterministic authorisation gate the task requires: no query runs that this
    validator did not pass. It re-derives what the text touches rather than trusting the caller,
    so it catches a composition that reached beyond the certified surface however it got there.
    """
    text = sql.strip()
    if text.count(";") > 0:
        raise UnsafeQueryError("a composed query must be a single statement with no ';'")
    if "--" in text or "/*" in text:
        raise UnsafeQueryError("a composed query must carry no SQL comment")
    if not re.match(r"(?is)^\s*SELECT\b", text):
        raise UnsafeQueryError("a composed query must be a read-only SELECT")
    forbidden = _FORBIDDEN.search(text)
    if forbidden is not None:
        raise UnsafeQueryError(f"forbidden token {forbidden.group(0)!r} in a composed query")
    if require_limit and not re.search(r"(?i)\bLIMIT\b\s+\d+", text):
        raise UnsafeQueryError("a composed query must carry a row-capping LIMIT")
    from_match = re.search(r"(?is)\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)", text)
    if from_match is None or from_match.group(1) != allowed_table:
        found = from_match.group(1) if from_match else "none"
        raise UnsafeQueryError(
            f"a composed query must read only the certified table {allowed_table!r}, not {found!r}"
        )
    # Every identifier that is not a SQL keyword, the allowed table, a bound-parameter name or a
    # certified column is a reference outside the certified surface.
    allowed = set(allowed_columns) | {allowed_table} | _SQL_WORDS
    for token in _IDENT.findall(text):
        if token.upper() in _SQL_WORDS_UPPER or token in allowed:
            continue
        raise UnsafeQueryError(f"identifier {token!r} is outside the certified surface")


#: SQL words the composer legitimately emits. Kept small: the composer only ever writes these.
_SQL_WORDS = {
    "SELECT",
    "FROM",
    "WHERE",
    "AND",
    "GROUP",
    "BY",
    "ORDER",
    "LIMIT",
    "AS",
    "SUM",
    "COUNT",
    "AVG",
    "MIN",
    "MAX",
}
_SQL_WORDS_UPPER = {word.upper() for word in _SQL_WORDS}


class SqlBuilder:
    """Compose a certified ``ResolvedIntent`` into a validated, bounded ``CompiledQuery``."""

    def compile(
        self, resolved: ResolvedIntent, *, tenant: str, inject_tenant_predicate: bool = True
    ) -> CompiledQuery:
        """Build the query. ``inject_tenant_predicate`` exists ONLY so a policy test can prove the
        predicate is load-bearing by omitting it; production callers never pass it False.
        """
        metric = resolved.metric
        dataset = resolved.dataset
        dims = resolved.dimensions

        projection = [*dims, f"{metric.aggregation} AS {metric.id}"]
        select_clause = "SELECT " + ", ".join(projection)
        from_clause = f"FROM {dataset.table}"

        params: list[tuple[str, str]] = []
        predicates: list[str] = []
        tenant_applied = False
        if inject_tenant_predicate and dataset.tenant_scoped:
            predicates.append(f"{dataset.tenant_column} = :tenant")
            params.append(("tenant", tenant))
            tenant_applied = True
        for index, flt in enumerate(resolved.filters):
            name = f"f{index}"
            predicates.append(f"{flt.field} = :{name}")
            params.append((name, flt.value))

        where_clause = f"WHERE {' AND '.join(predicates)}" if predicates else ""
        group_clause = f"GROUP BY {', '.join(dims)}" if dims else ""
        limit_clause = f"LIMIT {dataset.row_cap}"

        sql = " ".join(
            part
            for part in (select_clause, from_clause, where_clause, group_clause, limit_clause)
            if part
        )

        referenced = set(dims)
        referenced |= {flt.field for flt in resolved.filters}
        referenced |= _columns_referenced(metric.aggregation, dataset.columns)
        if tenant_applied:
            referenced.add(dataset.tenant_column)
        # The metric id is the projection ALIAS (``... AS revenue``), a legitimate identifier the
        # composer emits, so it is allowed alongside the dataset's certified columns.
        validate_sql(
            sql,
            allowed_table=dataset.table,
            allowed_columns=(*dataset.columns, metric.id),
        )

        return CompiledQuery(
            sql=sql,
            params=tuple(params),
            tables=(dataset.table,),
            columns=tuple(sorted(referenced)),
            row_cap=dataset.row_cap,
            tenant_predicate_applied=tenant_applied,
        )
