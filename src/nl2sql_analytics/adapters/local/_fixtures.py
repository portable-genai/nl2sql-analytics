"""Seeded, obviously fictional data for the offline adapter family.

Every party, region, tenant and figure here is invented. The warehouse deliberately holds rows
for MORE than one tenant so the row-level access predicate has something to exclude: a query that
lost the predicate would return ``other-bank``'s rows, and a test notices.
"""

from __future__ import annotations

#: The tenant the offline demo and tests answer as. The warehouse also holds a second tenant's
#: rows, which the tenant predicate must exclude.
DEMO_TENANT = "demo-bank"
OTHER_TENANT = "other-bank"

#: The fictional warehouse: table name -> (column names, rows). Seeded into an in-memory SQLite
#: by the local query engine. Amounts and counts are round, invented numbers.
WAREHOUSE: dict[str, tuple[tuple[str, ...], tuple[tuple[object, ...], ...]]] = {
    "orders_daily": (
        ("order_date", "region", "tenant", "amount", "status"),
        (
            ("2026-08-01", "APAC", DEMO_TENANT, 1000.0, "settled"),
            ("2026-08-01", "EMEA", DEMO_TENANT, 500.0, "settled"),
            ("2026-08-02", "APAC", DEMO_TENANT, 2000.0, "settled"),
            ("2026-08-02", "EMEA", DEMO_TENANT, 800.0, "pending"),
            ("2026-08-01", "APAC", OTHER_TENANT, 9999.0, "settled"),
        ),
    ),
    "customers": (
        ("signup_date", "region", "tenant", "segment", "active"),
        (
            ("2026-08-01", "APAC", DEMO_TENANT, "retail", 1),
            ("2026-08-01", "EMEA", DEMO_TENANT, "retail", 1),
            ("2026-08-02", "APAC", DEMO_TENANT, "wealth", 0),
            ("2026-08-01", "APAC", OTHER_TENANT, "retail", 1),
        ),
    ),
}

#: The offline certification feed, mirroring the H4 response schema (dataset -> status, certified
#: metric list, scorecard reference). ``orders_daily`` is certified; ``customers`` is only
#: conditionally certified, which is what drives the escalate-and-route demo beat. A dataset not
#: listed here is UNKNOWN to H4 and therefore refused.
CERTIFICATION_FEED: dict[str, dict[str, object]] = {
    "orders_daily": {
        "status": "certified",
        "certified_metrics": ["revenue"],
        "scorecard_ref": "SC-ORD-001",
    },
    "customers": {
        "status": "conditionally_certified",
        "certified_metrics": ["active_customers"],
        "scorecard_ref": "SC-CUS-002",
    },
}

#: Business-term synonyms the offline dictionary and model map to certified metric ids.
METRIC_SYNONYMS: dict[str, str] = {
    "revenue": "revenue",
    "sales": "revenue",
    "turnover": "revenue",
    "active customers": "active_customers",
    "active customer": "active_customers",
    "customers": "active_customers",
    "profit margin": "profit_margin",
    "profit": "profit_margin",
    "margin": "profit_margin",
}

#: Certified dimension words a question may name, mapped to the dataset column.
DIMENSION_WORDS: dict[str, str] = {
    "region": "region",
    "segment": "segment",
    "status": "status",
    "date": "order_date",
    "day": "order_date",
}

#: Prompt-injection / policy-violation markers the offline guardrail blocks. A question containing
#: any of these is screened out before the generation port is ever called.
INJECTION_MARKERS: tuple[str, ...] = (
    "ignore previous instructions",
    "ignore all previous",
    "disregard the semantic layer",
    "drop table",
    "delete from",
    "system prompt",
    "reveal the prompt",
    "bypass the guardrail",
)
