# Security FAQ

For an AppSec reviewer sizing up a natural-language-to-SQL service, which is a category with an
obvious worst case: a question that becomes a query nobody authorised. This file answers that
first, then the rest of the surface, and says plainly where a control is not built yet.

## Can a prompt make this service emit arbitrary SQL?

No, because the model never emits SQL at all. That is the design, not a mitigation.

The model's only structured output is an `AnalyticalIntent`: a `metric_id`, a list of
`dimensions`, a list of `filters` and a `grain` (`ports/llm.py`). That mapping is validated for
SHAPE by `domain/intent.parse_intent` (any wrong type, any missing metric id, and the proposal is
DISCARDED, never repaired) and then for AUTHORITY by `domain/semantic_resolver.py` against the
certified semantic layer. Only if every element resolves does a `ResolvedIntent` exist, and
`domain/sql_builder.py` accepts nothing else.

The composer then writes the SQL itself, from certified fragments:

```
SELECT <certified dimensions>, <metric aggregation> AS <metric id>
FROM   <certified table>
WHERE  <tenant_column> = :tenant [AND <certified filter column> = :fN]
GROUP BY <certified dimensions>
LIMIT  <dataset row_cap>
```

Identifiers (the table, the dimension columns, the filter columns) come only from the layer's
closed allow-lists in `config/semantic_layer/metrics.yaml`, which is why they are safe to place
in the text. Every caller-supplied VALUE (the tenant, each filter value) is a bound parameter
(`:tenant`, `:f0`) and is never interpolated. A filter value containing `'; DROP TABLE ...` is a
string bound by the driver, not SQL.

## What constrains the composed query, beyond how it was built?

`validate_sql` in `domain/sql_builder.py` runs on the COMPOSED TEXT inside `compile()`, before a
`CompiledQuery` exists, and raises `UnsafeQueryError` unless all of the following hold:

- a single statement: no `;` anywhere;
- no SQL comment: neither `--` nor `/*`;
- it starts with `SELECT`;
- it contains none of `DROP DELETE UPDATE INSERT ALTER CREATE REPLACE ATTACH PRAGMA VACUUM GRANT
  TRUNCATE` (word-boundary matched, case-insensitive);
- it carries a row-capping `LIMIT <n>`;
- its `FROM` names exactly the certified table for the resolved metric;
- every identifier in the text is either a certified column of that dataset, the metric alias, or
  one of a small set of keywords the composer itself emits.

This is deliberately a re-derivation rather than a trust of the caller: it catches a future
composition bug that reached beyond the certified surface however it got there. `QueryEnginePort`
takes a `CompiledQuery` and nothing else, so there is no path by which unvalidated text reaches
SQLite (`local`) or BigQuery (`gcp`).

## What happens to an uncertified metric?

It is refused, with a typed `Refusal` that names the nearest certified alternatives. There are
two independent gates and both fail closed:

1. **The semantic layer.** `SemanticResolver` refuses when the layer certifies no metrics at all
   (an empty or unreadable `config/semantic_layer/` yields an EMPTY layer, which refuses
   everything rather than allowing everything), when the metric id is not certified, when a
   dimension is outside that metric's `allowed_dimensions`, when a filter names a column the
   backing dataset does not declare, or when the grain contradicts the metric's own.
2. **The certification gate.** `domain/analyst_service.py` then reads the backing dataset's
   status from the `certification` port (H4, the Data-Quality and PII-Governance Agent). Only
   `certified` or `conditionally_certified` AND a dataset whose `certified_metrics` list contains
   this metric proceeds. An unreachable certification source resolves to `UNKNOWN`, which
   refuses. A `conditionally_certified` backing answers with a caveat, sets
   `requires_human_review` and is ROUTED to Hrz7 in the same call.

A refusal is a first-class outcome, not an error: it is audited, it carries a
`policy:semantic-layer` citation, and it is scored by the `refusal_completeness` eval metric at a
threshold of 1.00, so a fork whose gate lets one uncertified ask through goes red.

## Is the row set ACL-scoped?

Yes, at the row level, by construction. Every dataset marked `tenant_scoped` in
`config/semantic_layer/policies.yaml` gets a `WHERE <tenant_column> = :tenant` predicate injected
by the composer with the tenant BOUND as a parameter, and the fail-closed default is that a
dataset absent from the policy file is still treated as tenant-scoped. The tenant is the verified
principal's tenant: `api/app.py` passes `principal.tenant`, and `domain/models.Question.tenant` is
documented as never coming from the question text or a client-asserted field. The offline
warehouse deliberately holds a second tenant's rows, so a dropped predicate turns a test red
rather than passing quietly.

Two honest limits. First, the scoping is TENANT-level; there is no per-user or per-row entitlement
model beyond the tenant partition, which is why `COMPLIANCE.md` still carries a Partial on tenant
isolation and the practices audit marks object-level authorisation as day-one N/A. Second,
**column masks are declared but not applied**: `policies.yaml` has a `column_masks` block,
`semantic_config.py` parses it into `DatasetSpec.column_masks`, and nothing reads that field. Do
not treat it as a control.

## What does the `guardrail` port screen, and when?

`ports/guardrail.py` screens the ALREADY REDACTED question BEFORE the generation port is called,
which is the whole point of the ordering in `domain/analyst_service.py`: an injection corpus never
reaches the model, because generation happens after the screen. Both a block and a screen that
could not be reached refuse the question; the call is wrapped so any exception fails closed.

What the screen actually is depends on the profile, and only one of the three is real today:

- `local`: `LocalGuardrailAdapter` matches the question against the `INJECTION_MARKERS` corpus in
  `adapters/local/_fixtures.py`. It is a working screen, deliberately not a no-op, so the demo and
  the gate can prove the block path.
- `gcp`: `CloudGuardrailAdapter` is the declared seam to Hrz1, the Agent Guardrail Gateway. It
  performs its lazy `google.auth` import and then raises: the gateway call is not implemented.
  It is listed in `managed_readiness.py`, so the API refuses to start on this profile at all.
- `onprem`: raises `NotImplementedError` naming the client gateway to bind.

Hrz1 owns the injection corpus, the classifier and the output filter in every case. This repo owns
only where the call sits (before generation) and the rule that an unreachable screen refuses.
Rule R1 in [`../../COMPLIANCE.md`](../../COMPLIANCE.md) is the standing statement that the Hrz1
binding is still outstanding.

## What reaches the model, and what reaches an outbound sink?

`redact(question.text, PII_PATTERNS)` runs first, before the screen, before the dictionary lookup
and before `propose_intent`. The narration call receives only the metric title, the dimension
names, the result columns and rows, the row count and the deterministic caveats, never the
question, the SQL or the verdict. The audit write redacts again. The Hrz7 review payload is
redacted in `adapters/_review_payload.py` against EVERY jurisdiction's rows, not just this
deployment's, because the console is a shared sink. The trace span carries structural attributes
only (action, actor, tenant), never content.

The gap to know about: the result ROWS are passed to `narrate` as returned by the query engine.
Aggregate figures over a certified dataset are the expected content, but with column masks unapplied
a certified dimension carrying sensitive values would reach the model unmasked. See the remaining
controls in [`../model-card.md`](../model-card.md).

## How is identity handled? Can a caller spoof the actor or the tenant?

No. Identity is resolved server-side on every route and the client-asserted actor is discarded.
`api/schemas.py`'s request model carries no actor and no tenant; `get_principal` resolves a
verified `Principal` through the bound `IdentityPort`, and both the audit actor and the row-level
tenant come from it.

`ports/identity.py` makes each adapter DECLARE what it provides (`VERIFIED`, `CLIENT_ASSERTED` or
`UNIMPLEMENTED`), and the loopback exposure guard is derived from that declaration and from
nothing else, so setting the inbound service credential cannot switch the guard off for the
end-user routes it protects. Under `local` the seeded personas are chosen by an `X-Dev-Persona`
header, declare themselves `CLIENT_ASSERTED`, and refuse to construct unless the `local` profile
was chosen DELIBERATELY (`NL2SQL_PROFILE` set, not inherited). Under `gcp`,
`adapters/gcp/identity.py` verifies the IAP assertion with `id_token.verify_token` against the
configured `NL2SQL_IAP_AUDIENCE` (unset or emptied REFUSES, because an unverified audience accepts
any Google-signed token from any project) and against IAP's own key set, and checks the issuer
itself. `onprem` is a placeholder that raises.

## What are the profiles, and can one be selected by accident?

`NL2SQL_PROFILE` selects `local`, `gcp` or `onprem`, and it resolves ONCE at import into a
`ProfileChoice`. UNSET is treated as NO CHOICE rather than a silent `local`; SET-AND-EMPTY raises;
SET-AND-UNKNOWN raises. Both raises kill the process before it can serve a request. Only
`config.py` may read the variable, and `tests/unit/test_profile_single_source.py` fails the build
if another module re-derives it. Two postures are derived from the choice rather than one string,
because they fail closed in opposite directions: relaxations (CORS, the dev-persona header, HSTS)
key off `exposure_profile`, which is `unconfigured` when nobody chose, and the loopback bound keys
off `bind_profile`, which is `local` when nobody chose.

`tests/unit/test_three_state_env_reads.py` walks the AST of `src/`, `scripts/` and `eval/` and
fails the build on any two-state environment read that ships; `ui/tests/three-state-env-reads.test.mjs`
does the same for the micro-frontend.

## Is the audit trail tamper-evident?

Yes, within honest limits. `adapters/local/audit.py` wraps `hex_service_kit.audit.HashChainedAuditLog`:
append-only, SHA-256 hash-chained, with JSONL export and restore. The chain alone catches an
in-place edit, an interior deletion and a reorder, but NOT a truncated tail, because dropping the
newest rows leaves a shorter chain that verifies perfectly. That is why `audit_anchor_path`
(`NL2SQL_AUDIT_ANCHOR`) writes the chain head to a file on a different volume under different
credentials; `tests/unit/test_audit_anchor.py` proves the detection, proves the control case goes
UNDETECTED without an anchor, and proves an append after truncation refuses rather than
re-anchoring. The store itself is `NL2SQL_AUDIT_PATH`, defaulting to `:memory:` for the gate; a
durable deployment sets both. In the managed profile the WORM property comes from the locked
Cloud Logging bucket in `infra/terraform/logging_worm.tf` instead.

## Are there secrets in the repo?

No literal secret material. `config/settings.yaml` and `.env.example` carry variable NAMES and
non-secret defaults only; `.env.secrets.example` carries placeholders. Inbound and outbound
credentials are deliberately distinct variables: `NL2SQL_S2S_TOKEN` authenticates a calling
service INTO this one, while `HRZ7_S2S_TOKEN` and `HRZ7_S2S_SIGNING_KEY` are what this service
presents to the Hrz7 console. In a deployment they arrive as Secret Manager versions through
Terraform's `additional_secret_env`, which refuses a moving `latest` version and refuses to
shadow a name the stack sets itself.

## What is the supply-chain posture?

Committed `requirements-dev.lock` and `requirements-gcp.lock`, installed with `--no-deps` by
`make install`, by CI and by the Dockerfile, with the shared catalog commons pinned to 40-character
COMMIT shas rather than tags (a tag can be moved, so a tag pin lets what installs change with no
diff). A digest-pinned, multi-stage, non-root (uid 10001) Dockerfile with a healthcheck.
SHA-pinned Actions, dependabot per ecosystem, and `pip-audit` over both locks plus `npm audit` as
hard failures. `tests/unit/test_repo_artifacts.py` asserts each of these from inside the repo.

## What is explicitly out of scope, or not built yet?

Out of scope by design, because a sibling system owns it: the guardrail engine (Hrz1), the agent
registry (Hrz3), the promotion gate (Hrz4), the shared trace and WORM audit sink (Hrz5), the
human-review console (Hrz7), and dataset certification (H4). This repo integrates each through a
port rather than re-implementing it; see [features-faq.md](features-faq.md).

Not built yet, and tracked as such rather than implied:

- the managed adapter family is placeholders. Every `gcp` method performs its lazy import and
  raises, so the Hrz1 screen, the Gemini calls, the BigQuery execution and the H4 call are all
  unimplemented. `managed_readiness.py` lists them, the API preflight refuses to start on a
  managed profile while any is active, and `infra/terraform/managed_readiness.tf` fails
  `terraform plan` when `production_edge_enabled` is true;
- column masks are declared and not applied (above);
- a query timeout, a bytes-scanned ceiling and a per-caller rate limit are deployment-side today;
- an unreachable `dictionary` or `llm` port raises out of the request rather than producing a
  typed refusal, unlike the guardrail and certification ports which are explicitly wrapped;
- object-level authorisation below the tenant partition, and the remaining `TODO (repo owner)`
  rows in [`../../COMPLIANCE.md`](../../COMPLIANCE.md).
