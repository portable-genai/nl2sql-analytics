# Features FAQ

For product, data-and-analytics and delivery people: what this system actually does, what is
decided by code rather than by a model, and where its responsibility stops and a sibling
system's begins.

## What does the analyst do, in one pass?

It answers one governed analytical question, or refuses it, in eight fail-closed steps
(`domain/analyst_service.py`):

1. **Redact** the question with the shared `pii-kit` before anything outbound or any model call.
2. **Screen** it through the `guardrail` port. A block, or a screen that could not be reached,
   refuses. Generation happens after this, so a screened-out question never reaches the model.
3. **Look up** data-dictionary hints that map business words to certified metric ids.
4. **Propose** an intent (metric, dimensions, filters, grain). This is the model's first job. A
   proposal that fails schema validation is discarded and the question refuses.
5. **Resolve** the intent against the certified semantic layer, or refuse with the nearest
   certified alternatives.
6. **Gate** on the backing dataset's certification status from H4. Anything other than a
   currently certified (or conditionally certified) dataset that lists this metric refuses.
7. **Compose, validate and execute** a bounded, read-only, tenant-scoped `SELECT` built from
   certified fragments. Only a validated `CompiledQuery` reaches the query engine.
8. **Narrate and cite.** The model restates the result; a narration that invents a figure is
   discarded for a deterministic summary. Every answer carries a citation to the metric
   definition and to H4's certification, and a conditionally certified backing or an empty result
   sets human review and routes it.

## What is deterministic, and what is the model allowed to do?

The model has exactly two jobs, both untrusted and both bounded: propose an intent, and narrate a
finished result. It never chooses what is answered, never authorises a dataset, never writes SQL
and never produces a figure or a verdict. Everything consequential is pure stdlib and replayable:
`domain/semantic_resolver.py` decides admissibility, `domain/sql_builder.py` composes and
validates the query, and `domain/analyst_service.py` computes the severity band, the
`requires_human_review` flag and the citations. Stub the model and the SQL, the figures and the
verdict are identical. [`../model-card.md`](../model-card.md) is the full boundary statement.

## What are the surfaces?

- **HTTP API** (`api/app.py`): `POST /v1/ask` is the product surface; `GET /healthz`,
  `GET /.well-known/agent-card.json` and `GET /v1/personas` are operational, and
  `POST /v1/audit/ping` is a service-to-service stand-in. Interactive docs (`/docs`, `/redoc`,
  `/openapi.json`) are registered only under a deliberate `local` exposure profile.
- **CLI** (`cli/main.py`): `ask "<question>" [--actor ...] [--tenant ...]`, printing the answer,
  the composed SQL, every citation, and the review reference when it escalated.
- **Agent surface** (`agent/`): two plain tool callables, `ask_question` and
  `verify_audit_trail`, plus an A2A card at `/.well-known/agent-card.json` built from the same
  tool table the runtime binds. It imports with no ADK and no cloud SDK.
- **Micro-frontend** (`ui/`): the embeddable console, whose whole security boundary is one policy
  module and one server-side identity module.
- **Demo surface** (`scripts/`): the scripted arc, the static renderer, the live click-through
  server and the presenter walkthrough that doubles as the self-test. See
  [`../../scripts/README.md`](../../scripts/README.md).

## What is the certified semantic layer, and why is it the product?

`config/semantic_layer/metrics.yaml` declares the physical datasets (each with a closed `columns`
allow-list, a `tenant_column` and a `row_cap`) and the certified metrics (each with a SQL
aggregation fragment, a grain, a backing dataset, a closed `allowed_dimensions` set and a
`definition_version`). `policies.yaml` carries the row-access policy. A metric that is not
written there does not exist to this service.

That is the whole governance story: the answer set is a reviewable YAML file rather than an
emergent property of a prompt, the `definition_version` is cited on every figure so a number is
traceable to the definition that produced it, and widening what can be answered is a change to
governed configuration, never a code change. An empty or unreadable layer refuses everything.

## What does a refusal look like, and why is it a feature?

`Refusal` is a first-class outcome carrying a reason and the certified alternatives a caller CAN
ask instead. Refusing an uncertified ask is the behaviour a regulated buyer is paying for, so it
is audited, cited (`policy:semantic-layer`) and scored: the `refusal_completeness` eval metric
sits at a threshold of 1.00, alongside `resolver_accuracy`, `sql_correctness`,
`citation_accuracy`, `answer_groundedness`, `review_safety` and `pii_safety`.

## When does a human get involved?

When the answer is consequential. `requires_human_review` is set by pure code for a
conditionally certified backing dataset or an empty result, and rule R8 says setting the flag and
routing are ONE act: `api/app.py`, `cli/main.py` and `agent/tools.py` all call
`ReviewRouterPort.route` in the same call that produced the answer. The payload is redacted
before the wire against every jurisdiction's patterns, because the console is a shared sink.
`tests/unit/test_review_routing.py` asserts the routing rather than the flag.

## What does this repo own, and what does a sibling system own?

This repo owns the certified semantic layer, the deterministic resolver, the SQL composer and its
validator, the groundedness check, the refusal vocabulary, the audit chain with its external
anchor, and the offline demo and eval. It integrates the rest through ports:

| Concern | Owner | How this repo reaches it |
|---|---|---|
| Prompt-injection screening, output filtering | `agent-guardrail-gateway` Agent Guardrail Gateway | `ports/guardrail.py`, screened before generation. This repo owns only the placement and the fail-closed rule. |
| Governed RAG over a document corpus | `enterprise-knowledge-base` | Not integrated, by design: this service grounds in a certified layer and an executed query, not in retrieved documents. |
| Agent discovery, identity and entitlements | `agent-registry` and Governance | The A2A card at `/.well-known/agent-card.json`; registration is outstanding. |
| The promotion verdict for a model or agent | `model-quality-gate` AI Quality and Model-Risk Platform | `eval/run_eval.py --mode gate`, which refuses to run off the managed profile. `--mode smoke` is the offline pre-merge check. |
| Shared traces, immutable audit, spend | `agent-observability` Agent Observability, Audit and FinOps | The `tracer` port (one structural span per answered question) and the managed audit adapter. |
| The maker-checker console and case queue | `human-review-console` Case, Workflow and Human-Review Platform | `ports/review_router.py` over the shared `review-kit` (rule R8). |
| Dataset certification and data-quality scorecards | **H4** Data-Quality and PII-Governance Agent | `ports/certification.py`. H4's verdict crosses as DATA; H1 never imports H4. |

The `dictionary` port is retrieval that authorises nothing, which is why it is not a knowledge
base: its hints only help the model guess a metric id, and the resolver still refuses anything the
layer does not certify.

## What is not built yet?

The managed adapter family. Every `gcp` adapter performs its lazy SDK import and then raises, so
Gemini, BigQuery, the data-dictionary index, the `agent-guardrail-gateway` and the H4 call are declared seams
rather than working integrations. `managed_readiness.py` lists them, the API process preflight
refuses to start on a managed profile while any is active, and
`infra/terraform/managed_readiness.tf` fails `terraform plan` when `production_edge_enabled` is
true. The `channel` port is bound in all three profiles but exercised only by the demo. Column
masks are declared in `policies.yaml` and not yet applied by the composer. See
[`../../COMPLIANCE.md`](../../COMPLIANCE.md) and [`../practices-audit.md`](../practices-audit.md)
for the full outstanding list.
