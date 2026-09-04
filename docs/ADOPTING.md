# Adopting this repo as your base

This repository (H1, the NL2SQL Semantic Analyst) is a **common base** that a bank or other
regulated institution forks to build its own **governed natural-language analytics service**: a
service that turns an analytical question into a certified metric, composes the SQL itself from
that metric's certified fragments, executes a bounded and tenant-scoped read-only query, cites
every figure to the definition that produced it, and refuses anything the semantic layer does not
certify. It ships a reusable hexagonal core (a pure-stdlib domain, typed ports, three swappable
adapter profiles, a green offline gate) plus a fully worked semantic-layer vertical you can keep,
retune, or replace with your own metric catalogue.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical rebrand**
(one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (the layout, the port table and audit
> integrity), [`CONTRIBUTING.md`](../CONTRIBUTING.md) (adding an adapter, adding a port),
> [`model-card.md`](model-card.md) (what the model may and may not do), the [`faq/`](faq/)
> directory.

---

## 1. What you keep vs what you rewrite

The core is hexagonal, and the boundary between reusable machinery and your analytics vertical is
a physical module split with an enforced dependency direction (practices-audit check A7).
`domain/kernel.py` owns the vertical-neutral contracts and imports nothing from this package;
`domain/models.py` holds only the H1 vertical and imports `kernel`, never the reverse.

| Layer | Where | For a new analytics vertical |
|---|---|---|
| **Kernel** (vertical-neutral) | `domain/kernel.py`: `Severity`, `Decision`, `Citation`, `AuditEvent`, `utcnow`. Plus every Protocol in `ports/`, the container wiring in `config.py`, and the audit, identity, review-router and tracer adapters | keep untouched |
| **Policy** (your numbers) | the certified layer under `config/semantic_layer/` (metric definitions, `allowed_dimensions`, `row_cap`, `tenant_scoped`), `JURISDICTIONS` in `domain/pii.py`, `MAX_SUMMARY_CHARS` in `domain/narration.py`, the `THRESHOLDS` bundle in `eval/run_eval.py` | change deliberately, mostly by config rather than engine code |
| **Vertical** (analytics artifacts) | the artifact models in `domain/models.py` (`Question`, `AnalyticalIntent`, `MetricDefinition`, `DatasetSpec`, `ResolvedIntent`, `CompiledQuery`, `AnalystAnswer`, `Refusal`), the offline warehouse and dictionary fixtures in `adapters/local/_fixtures.py`, the eval golden set, the UI answer views | rewrite and reseed for your data |

The three deterministic engines transfer directly to any other governed-query fork:
`domain/semantic_resolver.py` (does the certified layer allow this ask?),
`domain/sql_builder.py` (compose from certified fragments, then validate the composed text), and
`domain/narration.py` (discard a narration that invents a figure). What you replace is the metric
catalogue and the physical datasets behind it, not the engines.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly.

- **Upstream-owned** (take our changes): `domain/kernel.py`, `domain/intent.py`,
  `domain/semantic_resolver.py`, `domain/sql_builder.py`, `domain/narration.py`, everything in
  `ports/`, `tests/contract/`, the eval harness mechanics (`eval/run_eval.py` scaffolding), the
  hexagon wiring (`config.py` `Container`, `assembly.py`) and the CI workflows.
- **Adopter-owned** (yours; expect to edit): the whole of `config/semantic_layer/`, the offline
  warehouse and dictionary fixtures, `config/settings.yaml` *values*, `adapters/onprem/*`, UI
  theming, the golden eval dataset, and the jurisdiction rows in `COMPLIANCE.md`.

**The certified semantic layer and the business dictionary are the adopter-owned surface here.**
Everything the service will ever answer is decided by them, so treat them as governed
configuration and not as fixtures:

- `config/semantic_layer/metrics.yaml` declares the physical `datasets:` (each with its closed
  `columns` allow-list, its `tenant_column` and its `row_cap`) and the certified `metrics:` (each
  with its SQL `aggregation` fragment, its `grain`, its `backing_dataset`, its closed
  `allowed_dimensions` and its `definition_version`, which is cited on every answer).
  `config/semantic_layer/policies.yaml` carries the row-access and column-mask policy.
  `semantic_config.py` is the I/O boundary that reads both into the frozen
  `domain/semantic_layer.py` value; a missing or unreadable file yields an EMPTY layer, and an
  empty layer refuses every question rather than allowing everything.
- `domain/semantic_resolver.py` is the gate that spends those files: a metric the layer does not
  certify, a dimension outside `allowed_dimensions`, a filter on a column the dataset does not
  declare, or a grain that contradicts the metric's own all refuse, with the certified
  alternatives attached to the refusal. Adding a metric is a YAML change; widening what can be
  answered is never a code change.
- The **business dictionary** is the `dictionary` port. It is retrieval only: it returns
  `DictionaryEntry` hints that help the model map a business word to a certified metric id, and
  it authorises nothing, because the resolver still refuses anything the layer does not certify.
  The offline adapter derives its hints from `METRIC_SYNONYMS` in
  `adapters/local/_fixtures.py`; the managed adapter is where you point at your institution's own
  data dictionary index.
- The **certification** port is the hand-off to H4, the Data-Quality and PII-Governance Agent. It
  answers with a `DatasetCertification` per dataset, and `domain/analyst_service.py` refuses
  unless the backing dataset is currently `certified` or `conditionally_certified` AND lists the
  metric being asked for. An unreachable certification source resolves to `UNKNOWN`, which
  refuses. A conditionally certified backing answers with a caveat and escalates.

Track upstream via git tags; rebase your adopter-owned changes onto each release rather than
merging `main` continuously.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the python package name (`nl2sql_analytics`), the
console-script name (which in this template is the same token, see `[project.scripts]`), the
`NL2SQL` env-var prefix stem, the Terraform `name_prefix` resource stem (`h1-svc`) and the
distribution / git id (`nl2sql-analytics`) across the tree in one simultaneous pass.
Preview first, then apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_analyst --cli acme-analyst \
    --env-prefix ACME --resource acme-analyst --dry-run

# Apply:
python scripts/rename_fork.py --package acme_analyst --cli acme-analyst \
    --env-prefix ACME --resource acme-analyst --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make gate
```

`--dist` defaults to the package with underscores hyphenated; pass it explicitly if your git id
differs from that. Add `--include-docs` to sweep Markdown prose too. The script renames
`src/nl2sql_analytics/` last, after rewriting its contents. It deliberately does NOT touch
the human decisions below.

## 4. The human decisions (the script can't make these)

1. **Region / residency.** This build is pinned to `asia-southeast1`. Set `GCP_REGION` and, in
   tfvars, BOTH the Terraform `region` and `allowed_regions` (the residency allowlist the region
   is validated against at plan time) to your in-country region. The KMS key ring, the WORM log
   bucket and the Cloud Run service all take their location from that one value. See
   [`runbook.md`](runbook.md).
2. **Identity / IdP.** This repo owns no login flow. `gcp` verifies the Cloud IAP-injected
   assertion against `NL2SQL_IAP_AUDIENCE` (unset or emptied REFUSES, because an unverified
   audience accepts any Google-signed token); `local` uses seeded dev personas chosen by an
   `X-Dev-Persona` header, which authenticate nobody and keep the service on loopback; `onprem`
   is a client-IdP placeholder that raises. Wire your issuer on the deployed service and set the
   audience. The verified principal, never the request body, supplies both the audit actor and
   the tenant the row-level predicate is bound to.
3. **The certified semantic layer, and who certifies it.** The shipped layer certifies two
   fictional metrics (`revenue`, `active_customers`) over two fictional datasets. Replace it with
   your own metric catalogue, and decide the workflow around it: who may add a metric, what
   review a `definition_version` bump needs, and how your data-governance function publishes the
   per-dataset certification the `certification` port reads. The shipped offline adapter serves a
   fixture feed mirroring H4's response schema; in a deployment that feed is H4's live verdict,
   and everything not currently certified is refused.
4. **Row caps and the query guardrails you actually want.** The composer enforces four things
   today, all in `domain/sql_builder.py`: a `LIMIT` taken from the dataset's `row_cap` (1000 in
   the shipped layer), a `WHERE <tenant_column> = :tenant` predicate injected on every
   tenant-scoped dataset with the tenant BOUND as a parameter, a single-statement read-only
   `SELECT` with no comment and no forbidden token, and an identifier check that refuses anything
   outside the certified table and columns. Set your own row caps per dataset, decide whether any
   dataset is legitimately not tenant-scoped, and add the controls this repo does not yet have: a
   query timeout, a bytes-scanned ceiling and a per-caller rate limit are all deployment-side
   today. Column masks are declared in `policies.yaml` and carried on `DatasetSpec`, but the
   composer does not yet apply them, so do not rely on that field as a control.
5. **Reference data is fictional.** The offline warehouse (`adapters/local/_fixtures.py`), the
   certification feed, the dictionary synonyms and the injection corpus all use obviously
   invented parties, tenants and figures, and deliberately hold a second tenant's rows so the
   row-level predicate has something to exclude. Replace them with your own synthetic data. **Do
   not point this at a production warehouse without your own security, data-governance and
   model-risk sign-off.**
6. **Eval golden set.** Rebuild `eval/datasets/golden_cases.jsonl` and the `THRESHOLDS` bundle in
   `eval/run_eval.py` for your metric catalogue: a fork inherits a green gate that measures the
   WRONG semantic layer until you do. The gate structure and the strict
   `refusal_completeness = 1.00` and `pii_safety >= 0.99` bars are generic; the golden cases are
   yours. Register your bundle with `model-quality-gate`, which owns the promotion verdict.
7. **Deployment posture.** Review the Dockerfile (digest-pinned base, non-root uid 10001,
   healthcheck on `/healthz`), `infra/terraform/` (region allowlist, Org Policy, CMEK, dry-run
   VPC-SC, locked WORM logging) and the loopback-by-default API binding before you expose
   anything. Note that `infra/terraform/managed_readiness.tf` and the API process preflight both
   refuse a managed deploy while the `gcp` adapters listed in `managed_readiness.py` (in the
   package root) are still placeholders, so implementing those is part of your adoption, not an
   optional extra.

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems. Several concerns it *touches* are
owned by sibling systems, and you should integrate rather than rebuild them. The `gcp` adapter
family is where each integration lands; see [`faq/features-faq.md`](faq/features-faq.md) for the
full boundary map and [`../COMPLIANCE.md`](../COMPLIANCE.md) for the per-rule status.

- `agent-guardrail-gateway` Agent Guardrail Gateway: **this repo binds a `GuardrailPort`**, which most of its
  siblings do not. That port is a client, not an engine: `ports/guardrail.py` screens every
  question before generation, and `adapters/gcp/guardrail.py` is the seam that calls the `agent-guardrail-gateway` as a trusted service. `agent-guardrail-gateway` owns the injection corpus, the classifier and the output
  filter; this repo owns only the decision that an unreachable screen REFUSES. Do not grow your
  own screening engine behind that port.
- `agent-registry` and Governance: the agent publishes an A2A card at
  `/.well-known/agent-card.json` built from the same tool table the runtime binds. Register the
  card with `agent-registry` and take the agent's identity and entitlements from it.
- `model-quality-gate` AI Quality and Model-Risk Platform: owns the promotion verdict.
  `eval/run_eval.py --mode gate` is the client half and refuses to run off the managed profile;
  `--mode smoke` is the offline pre-merge check.
- `agent-observability` Agent Observability, Audit and FinOps: the shared trace and immutable-audit sink. The
  `tracer` port emits one structural span per answered question, and the managed audit adapter
  writes to the locked Cloud Logging bucket.
- `human-review-console` Case, Workflow and Human-Review Platform: every `requires_human_review` answer is
  routed there over the shared `review-kit` in the same call that produced it (rule R8). You
  wire your endpoint; you do not re-implement the console.
- **H4** Data-Quality and PII-Governance Agent: owns dataset certification. H1 consumes its
  verdict as DATA through the `certification` port and never imports it.

`enterprise-knowledge-base` (the governed knowledge base) is deliberately NOT integrated: this service grounds its
answers in a certified semantic layer and an executed query, not in retrieved documents, so there
is no RAG surface to place behind a knowledge-base port. The `dictionary` port is retrieval that
authorises nothing, which is why it is not a knowledge base.

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py`, recreated the venv, `make gate` and `make docs-check` green.
- [ ] Set region plus Terraform `region` and `allowed_regions` tfvars to your in-country region.
- [ ] Wired your IdP audience on the deployed service (this repo owns no login flow).
- [ ] Replaced `config/semantic_layer/` with your own certified metrics and datasets.
- [ ] Agreed the certification workflow with your data-governance function and pointed the
      `certification` port at it.
- [ ] Set your own `row_cap` per dataset, confirmed every dataset's `tenant_scoped` value, and
      added the query timeout, bytes ceiling and rate limit this repo leaves to the deployment.
- [ ] Replaced the offline warehouse, the dictionary synonyms and every other fixture.
- [ ] Rebuilt the eval golden set and thresholds, and registered the bundle with `model-quality-gate`.
- [ ] Implemented the `gcp` adapters listed in `managed_readiness.py` and removed them from that
      tuple, so a managed deploy stops being refused at preflight and at plan time.
- [ ] Reviewed the deploy posture (Dockerfile, Terraform, bind address).
- [ ] Decided which sibling platform systems you integrate vs stub.
- [ ] Recorded your baseline upstream tag so you can take future fixes.
