# Compliance FAQ

For compliance, data governance and model-risk reviewers. The authoritative per-principle mapping
with its evidence files is [`../../COMPLIANCE.md`](../../COMPLIANCE.md); this file answers the
questions people ask around it, and is deliberately explicit about what is not yet covered.

## What is the regulatory posture, and what does this repo NOT claim?

The mapping in `COMPLIANCE.md` is to the catalog's own principles (P-01 to P-13) and platform
dependency rules (R1 to R8), aligned to MAS TRM, APRA CPS 234 and CPS 230, HKMA and PDPA-class
regimes. The mapping from those to a specific regulation, and the judgement that a control is
SUFFICIENT for it, is adopter-owned: it depends on the institution's risk appetite, its
regulator, its licence conditions and its existing control library. No row in that file should be
quoted as regulatory assurance on this repository's behalf.

What an adopter is expected to add in their own control library: the crosswalk to their MAS TRM,
CPS 234, CPS 230, HKMA or PDPA control ids; the risk acceptance for every row still marked
Partial or TODO at go-live; the second-line review of the deterministic policy in `domain/`,
which is bank-owned logic and not a vendor default to inherit unexamined; and the retention
schedule and legal basis for the audit trail this service writes.

## How is personal data handled?

Minimised at every boundary rather than once. `domain/analyst_service.py` redacts the question
with the shared `pii-kit` BEFORE the guardrail screen, before the dictionary lookup and before
the model call, and redacts again before the audit write, so no raw identifier reaches a WORM
record. `adapters/_review_payload.py` redacts before the Hrz7 payload leaves the process, against
EVERY jurisdiction's patterns rather than only this deployment's, because the console is a shared
sink. Trace spans carry structural attributes only (action, actor, tenant), never content.

Which national patterns apply is a per-deployment choice: `domain/pii.py` selects and ORDERS rows
from the shared pack, national-ID rows first and the universal email and phone rows last, and the
shipped `JURISDICTIONS` tuple is `SG`, `HK`, `JP`, `AU`. The safety metric can go red:
`tests/unit/test_not_falsely_green.py` proves it, scoring `pii_safety` two ways (the shared pack
scan plus an independent planted-literal oracle) so a metric that silently stopped measuring
anything would fail the build.

The honest gap: the query RESULT rows are handed to the narration call as the engine returned
them, and the `column_masks` block in `config/semantic_layer/policies.yaml` is parsed into
`DatasetSpec.column_masks` but applied by nothing. Aggregate figures over a certified dataset are
the expected content, but do not treat column masking as an implemented control.

## Is there maker-checker, and is it enforced or merely flagged?

Enforced, and routed. Rule R8 in this catalog says setting `requires_human_review` and calling
`ReviewRouterPort.route` are ONE act, and `api/app.py`, `cli/main.py` and `agent/tools.py` all
route in the same call that produced the answer. `domain/analyst_service.py` sets the flag by
pure code, for a conditionally certified backing dataset or an empty result, and never by model
output. `tests/unit/test_review_routing.py` asserts the ROUTING rather than the flag, because a
local router that silently did nothing would let a producer ship R8 unwired and green; the
offline router therefore enqueues to the review kit's outbox, the managed router REFUSES when no
console is configured rather than swallowing the escalation, and the on-premises router raises.
`CRITICAL` demands two approvals.

## How is data residency enforced, rather than described?

The region is chosen once (`asia-southeast1` in this build), carried by `config/settings.yaml`,
reported by `/healthz` and printed on the agent card, so a drifting deployment is visible. At
deploy time, four things in `infra/terraform/` make it enforcement rather than documentation:

- `variables.tf` validates the EFFECTIVE region against `var.allowed_regions` at plan time, so an
  unvetted region fails `terraform plan` rather than putting regulated data out of jurisdiction;
- `org_policy.tf` restricts `constraints/gcp.resourceLocations` to `in:<region>-locations`, and
  also disables service-account key creation and requires uniform bucket-level access
  (`var.enable_org_policies`, default true);
- `kms.tf` creates a REGIONAL CMEK key ring and key with 90-day rotation, bound per service agent
  because CMEK does not cascade;
- `vpc_sc.tf` stands up a VPC Service Controls perimeter around the AI and control-plane APIs,
  DRY-RUN first (`var.vpc_sc_enforce`, default false) so violations are watched before they are
  enforced, and `logging_worm.tf` puts the locked WORM audit bucket in the same region.

The caveat that keeps this Partial rather than Covered: `infra/terraform/production_edge.tftest.hcl`
asserts several of those claims with a mock provider, but no `make` target and no workflow in this
repo runs `terraform test`, so nothing in the offline gate fails if the posture regresses. Both
the org-policy layer and the perimeter are also switchable off for a project-scoped evaluation
deploy, which is documented as NOT a compliant production posture.

## How long is the audit trail kept, and is it immutable?

Offline, `adapters/local/audit.py` is append-only and hash-chained with an EXTERNAL head anchor
(`NL2SQL_AUDIT_ANCHOR`) on a different volume, because the chain alone cannot detect a truncated
tail. In a deployment the WORM property comes from `logging_worm.tf`: a Cloud Logging bucket with
`var.retention_days` (minimum 180, default 180) and `var.worm_locked` (default true), where the
lock is IRREVERSIBLE and a plan may never request a retention lower than a bucket already locked
at. The bucket is CMEK-encrypted and DATA_READ audit logging is on, so a read of the evidence is
itself recorded. The retention schedule and its legal basis remain an adopter decision.

## What is the model-risk evidence?

[`../model-card.md`](../model-card.md) is the starter model card: what the model does (propose an
intent, narrate a result), what it structurally cannot do (write SQL, choose what is answered,
produce a figure or a verdict), how each output is validated and discarded on failure, the
adapter behaviour per profile, and the controls still outstanding.

The quantitative half is `eval/run_eval.py`. `--mode smoke` runs in the offline gate on every
change and scores the real pipeline against the golden set's OWN `expected_*` fields, an
independent oracle, never against the pipeline's own answer: `resolver_accuracy` (0.90),
`refusal_completeness` (1.00), `sql_correctness` (0.90), `citation_accuracy` (0.99),
`answer_groundedness` (0.99), `review_safety` (0.99), `pii_safety` (0.99). `--mode gate`
delegates the promotion verdict to Hrz4, the AI Quality and Model-Risk Platform, and refuses to
run off the managed profile, because a promotion certified by a laptop is certified by nothing.
Registering this repo's bundle and thresholds with Hrz4 is still outstanding.

## Is every answer explainable?

Yes, and by construction rather than by prompting. Every answered question carries two citations
built by pure code: `metric:<id>` with the metric title, its `definition_version` and its grain,
and `cert:<dataset>` with H4's status and scorecard reference. Every refusal carries
`policy:semantic-layer` with the reason. The composed SQL is returned with the answer, and the
`CompiledQuery` records exactly which tables and columns the validator proved it touches, so a
reviewer can see the query stayed inside the certified surface. The decision path itself is pure
stdlib and replayable: the same question over the same layer and the same certification feed
produces the same SQL, the same figures and the same verdict.

## What is still open?

Read `COMPLIANCE.md` for the authoritative list; the ones a compliance reviewer usually asks
about first are:

- the managed adapter family is placeholders, so the Hrz1 guardrail binding (R1), the Hrz5
  observability binding (R2), the Hrz3 registration (R4) and the Hrz4 bundle registration (R5)
  are all declared seams rather than live integrations;
- resilience (P-10): timeouts, a circuit breaker, a documented kill switch and the CPS 230
  recovery objectives in the runbook;
- cost and latency control (P-11): a token budget, small-model-first routing and a cache;
- object-level authorisation below the tenant partition, and the column masks noted above;
- an Rsk3 intake validation reference (R6), which is an intake action rather than a code control.
