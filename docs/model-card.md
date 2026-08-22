# Model card: NL2SQL Semantic Analyst (H1)

This is a STARTER model card. It records the model boundary as built and the controls that must be
completed before a managed deployment. The deterministic engines are the system of record; the
model is a bounded, replaceable component that cannot widen what the service will answer.

## What the model does, and does not do

- **Does**: two narrow jobs behind one port (`ports/llm.py`, `AnalystLlmPort`).
  1. `propose_intent(question, hints)` returns a plain mapping proposing a `metric_id`,
     `dimensions`, `filters` and a `grain`. The question it sees is already redacted, and the
     `hints` are data-dictionary entries that authorise nothing.
  2. `narrate(facts)` returns prose restating a finished result table. The facts it sees are the
     metric title, the dimension names, the result columns and rows, the row count and the
     deterministic caveats, never the original question, the SQL, or the certification verdict.
- **Does NOT**: write SQL, choose what may be answered, authorise a dataset, or produce any
  figure, severity, escalation or citation. `domain/sql_builder.py` composes the query from
  certified fragments; `domain/semantic_resolver.py` decides whether an ask is inside the
  certified surface; `domain/analyst_service.py` computes the severity band, the
  `requires_human_review` flag and the two citations. With the model stubbed the SQL, the figures
  and the verdict are byte-identical, so a model change cannot move a number.

The whole safety story is that boundary: **no SQL the model wrote is ever executed, because the
model never writes SQL.** `SqlBuilder.compile` takes a `ResolvedIntent` (a value that only exists
once every element resolved against the certified layer) and emits
`SELECT <certified dimensions>, <metric aggregation> AS <metric id> FROM <certified table>
WHERE <tenant_column> = :tenant [AND <certified filter> = :fN] GROUP BY <dimensions>
LIMIT <dataset row_cap>`. Identifiers come only from the layer's closed allow-lists; every
caller-supplied value (the tenant, each filter value) is a bound parameter and never interpolated.

## Boundary and validation

- **Redaction first.** `domain/analyst_service.py` calls `redact(question.text, PII_PATTERNS)`
  before the guardrail, before the dictionary lookup and before `propose_intent`. It redacts
  again before the audit write, so no raw identifier reaches a WORM record. The pattern set is
  `domain/pii.py`, national rows first and the universal email and phone rows last.
- **Screen before generation.** The `guardrail` port screens the redacted question BEFORE the
  generation port is reached. A block refuses; a screen that could not be reached also refuses
  (the call is wrapped and any exception fails closed), so an injection corpus never gets as far
  as the model.
- **The proposal is schema-validated, not repaired.** `domain/intent.parse_intent` checks types
  and required fields and returns `None` on any failure. A discarded proposal becomes a typed
  refusal carrying the certified metric ids, never a guess.
- **An uncertified proposal is refused, never widened.** `SemanticResolver.resolve` returns a
  `Refusal` when the layer is empty, when the metric is not certified, when a dimension is
  outside the metric's `allowed_dimensions`, when a filter names a column the backing dataset
  does not declare, or when the grain contradicts the metric's own. The refusal names the nearest
  certified alternatives; the caller gets a first-class governed outcome, not an error.
- **The certification gate is separate and fail-closed.** After resolution,
  `CertificationPort.dataset_status` supplies H4's verdict for the backing dataset. Only
  `certified` or `conditionally_certified` AND a dataset that lists this metric proceeds;
  anything else, including an unreachable certification source (which resolves to `UNKNOWN`),
  refuses. A `conditionally_certified` backing answers with a caveat, sets
  `requires_human_review` and is routed to Hrz7 in the same call.
- **The composed SQL is validated before it can execute.** `validate_sql` runs inside
  `compile()`, on the composed text, and raises `UnsafeQueryError` unless the query is a single
  statement with no `;`, carries no SQL comment, starts with `SELECT`, contains none of
  `DROP DELETE UPDATE INSERT ALTER CREATE REPLACE ATTACH PRAGMA VACUUM GRANT TRUNCATE`, carries a
  row-capping `LIMIT`, reads only the certified table, and names no identifier outside the
  certified columns plus the metric alias plus a small emitted-keyword set. `QueryEnginePort`
  only ever receives a `CompiledQuery`, so there is no path by which unvalidated text reaches an
  engine.
- **The row set is tenant-scoped by construction.** The tenant predicate is injected on every
  `tenant_scoped` dataset with the tenant BOUND as a parameter, and the tenant comes from the
  verified principal (`api/app.py` passes `principal.tenant`), never from the request body or the
  question text. The offline warehouse deliberately holds a second tenant's rows so a dropped
  predicate turns a test red.
- **The narration is discarded if it invents anything.** `domain/narration.is_grounded` rejects a
  draft that is blank, longer than `MAX_SUMMARY_CHARS` (400), or that contains any number the
  result table does not contain (the row count is also allowed). A rejected or failed draft falls
  back to `_deterministic_summary`, so a fabricated figure cannot reach a caller whatever the
  model produced.
- **Every answer is cited.** Pure code attaches `metric:<id>` (title, `definition_version` and
  grain) and `cert:<dataset>` (H4 status and scorecard reference); every refusal carries
  `policy:semantic-layer` with the reason. The model contributes no citation.
- **Traces carry no content.** The one span per answered question records the action, the actor
  and the tenant only. The question text, the proposed intent, the SQL, the figures and the
  refusal reason are deliberately kept out of a sink that has no redaction stage.

## Adapters and profiles

| Profile | Model adapter (`llm`) | Guardrail adapter | Behaviour |
|---|---|---|---|
| `local` | `adapters/local/llm.py` (`LocalAnalystLlm`) | `adapters/local/guardrail.py` (`LocalGuardrailAdapter`) | Deterministic and SDK-free. The proposal comes from dictionary hints plus keyword matching over `METRIC_SYNONYMS` / `DIMENSION_WORDS`, and falls back to a metric name the layer will not certify so an unrecognised question REFUSES. The narration is assembled from the facts. The screen is a real screen over the `INJECTION_MARKERS` corpus, not a no-op. Both outputs still pass through the same schema and groundedness checks a real model's would. |
| `gcp` | `adapters/gcp/llm.py` (`CloudAnalystLlm`) | `adapters/gcp/guardrail.py` (`CloudGuardrailAdapter`) | Placeholders. Each method performs its lazy SDK import (`google.generativeai`, `google.auth`) and then raises: the Gemini call and the Hrz1 gateway call are not implemented. Both `llm` methods and `guardrail.screen` are listed in `managed_readiness.py`, so the API process preflight refuses to start on this profile and `infra/terraform/managed_readiness.tf` fails `terraform plan` when `production_edge_enabled` is true. |
| `onprem` | `adapters/onprem/llm.py` (`OnPremAnalystLlm`) | `adapters/onprem/guardrail.py` (`OnPremGuardrailAdapter`) | Fail-fast portability placeholders that raise `NotImplementedError` naming the client component to bind (P-12). They satisfy the Protocols so the exit seam is real rather than decorative. |

So the honest reading of the guardrail port today: it is a REAL screen only under `local`. Under
`gcp` it is the declared seam to Hrz1 and nothing more, and under `onprem` it refuses. Hrz1 owns
the injection corpus, the classifier and the output filter in every case; this repo owns only the
placement of the call (before generation) and the rule that an unreachable screen refuses.

## Remaining controls (TODO, repo owner)

- **Implement the managed model adapter and pin what it is** (P-07, P-11). No model id, version,
  region, temperature, safety setting or prompt template is pinned anywhere in this repo today.
  Record them here when `CloudAnalystLlm` performs the real Gemini call, and remove the two `llm`
  entries from `INCOMPLETE_MANAGED_OPERATIONS` only when an integration test proves the response
  mapping.
- **Bind the guardrail to Hrz1 for real** (rule R1). Until `CloudGuardrailAdapter.screen` calls
  the gateway, injection defence and output filtering exist offline only.
- **Redact what the narrator sees, and apply the column masks** (P-04). `narrate` receives the
  result ROWS as they came back from the query engine. Aggregate figures over a certified dataset
  are the expected content, but `column_masks` declared in `config/semantic_layer/policies.yaml`
  are parsed into `DatasetSpec.column_masks` and then used by nothing, so a certified dimension
  carrying sensitive values would reach the model unmasked. Apply the masks in the composer, or
  redact the facts before the `narrate` call, before pointing this at real data.
- **Make an unavailable generation or dictionary port fail closed like the others** (P-10). The
  guardrail call and the certification call are wrapped and refuse on any exception; the
  `DictionaryPort.lookup` and `AnalystLlmPort.propose_intent` calls are not, so an unreachable
  model raises out of the request instead of producing a typed refusal. Only `narrate` degrades
  gracefully today.
- **Budget, rate and kill switch** (P-10, P-11): a per-tenant token budget, a request rate limit,
  a query timeout and a documented switch that forces refusal rather than generation.
- **Evaluate the live model** (P-08, rule R5). The offline eval scores the deterministic local
  stub against the golden oracle in `eval/datasets/golden_cases.jsonl`. Add a managed-profile run
  through the Hrz4 promotion gate that scores real intent accuracy, refusal completeness and
  narration groundedness against the same golden cases, and register the bundle with Hrz4.

Until these are complete the system is safe to run offline (deterministic engines plus the local
stub model) and the managed model path is not production-cleared. Both the process preflight and
the Terraform plan enforce that today rather than trusting this paragraph.
