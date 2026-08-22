# Portability FAQ

For architecture, cloud and exit-planning reviewers who want to know how real the "no lock-in"
claim is, and how an off-cloud or sovereign exit would actually work for a service that reads a
warehouse and calls a model.

## What is the no-lock-in claim, concretely?

`src/nl2sql_analytics/domain/` is pure standard library plus the stdlib-only shared
commons: no Google Cloud SDK, no FastAPI, no HTTP client, no SQL driver, no YAML parser. Even the
certified semantic layer is a frozen dataclass (`domain/semantic_layer.py`); the YAML under
`config/semantic_layer/` is read by `semantic_config.py` in the package root, which is the I/O
boundary, so a test can build a layer in memory without touching disk.

Every boundary is a `@runtime_checkable` `Protocol` in `ports/`, re-exported once with the
`PORT_PROTOCOLS` map: `audit`, `certification`, `channel`, `dictionary`, `guardrail`, `identity`,
`llm`, `observability`, `query_engine`, `review_router`. `tests/unit/test_core_purity.py` holds
the domain to it, and `tests/contract/test_port_parity.py` asserts set equality across ALL FIVE
homes of a port (the Protocol map, `config.DEFAULT_BINDINGS`, the `Container` accessor,
`config/settings.yaml`, and the canonical-call table), so an unregistered port cannot run
untested.

## What are the three profiles?

`NL2SQL_PROFILE` selects the whole adapter stack from the `adapters:` block in
`config/settings.yaml`. Switching a port is a configuration change, not a code edit.

- **`local`**: a real, working, SDK-free offline stack. Stdlib `sqlite3` over a seeded fictional
  warehouse for the query engine, a deterministic intent proposer and narrator for the model, a
  real screen over an injection corpus for the guardrail, a fixture feed mirroring H4's response
  schema for certification, and a hash-chained audit log. This is the dev, test and CI default,
  and the working proof that the domain runs entirely off-cloud.
- **`gcp`**: the managed stack (Gemini, BigQuery, Vertex AI Search for the data dictionary, the
  Hrz1 guardrail gateway, Cloud Logging, Cloud Trace, IAP identity), each importing its SDK
  LAZILY inside the method so the other two profiles import the module tree with no cloud SDK
  installed. Be clear about its state: these adapters are still placeholders that raise, listed
  in `managed_readiness.py`, and the API process refuses to start on this profile while any
  listed operation is active.
- **`onprem`**: fail-fast placeholders that satisfy the same Protocols and raise
  `NotImplementedError` naming the client component to bind. They RAISE rather than pretending,
  which is what makes the exit seams honest rather than decorative (P-12).

## Is the portability claim tested, or just asserted?

Tested, and bounded. `make portability` runs `scripts/portability_demo.py`, which prints a pass
or fail for each named check and exits non-zero on any failure: every port bound in every
profile, every adapter constructing from one `Settings` and satisfying its Protocol, the offline
family ANSWERING a canonical call rather than merely not raising, the exit family REFUSING, an
in-place rewrite detected, an anchored trail detecting a truncated tail with its control case,
the JSONL export reloading into a foreign store with its chain intact, and no cloud SDK imported
anywhere along the way.

It also prints what it does NOT prove: that an on-premises deployment exists or that anyone has
run one; infrastructure, model, network or whole-system portability; and anything at all about
the managed profile's live behaviour, which needs a cloud project and lives in
`tests/integration/`. Bounding the claim is deliberate.

## How would a sovereign or on-premises exit actually go?

`adapters/onprem/` is the scaffold, and for this vertical the seams are unusually concrete
because the deterministic half moves unchanged:

- **The query engine** is the big one. `CompiledQuery` is plain ANSI-shaped SQL with named bound
  parameters, a single certified table, a `GROUP BY` and a `LIMIT`. Any SQL engine that accepts
  named parameters can run it; the offline profile already proves that with stdlib `sqlite3`.
  Point the on-premises adapter at your own warehouse.
- **The model** is two narrow calls (`propose_intent`, `narrate`), both of whose outputs are
  discarded on failure by pure code. Binding a client-hosted model is an adapter, not a redesign,
  and the deterministic fallback means the service degrades to a caveated summary rather than
  stopping.
- **The certified layer** is already YAML you own, and the resolver and composer that spend it
  are pure stdlib. Nothing about them is cloud-shaped.
- **Identity, audit, review routing and the guardrail** are the same seams every catalog service
  has: your IdP, your audit store, your review console, your screening gateway.

See [`../onprem-migration.md`](../onprem-migration.md) for the migration guide and
[`../runbook.md`](../runbook.md) for operations.

## Can the data be exported in an open format?

Yes. The audit trail exports to and restores from JSON Lines, carrying its chain anchor with it,
and `portability_demo.py` proves a foreign reload keeps the chain intact while a truncated export
is refused. So the audit exit is a file copy rather than a migration project. The certified
semantic layer is already plain YAML in the repository, and an `AnalystAnswer` is a frozen
dataclass of strings and tuples with no cloud type anywhere in it.

## How is data residency handled?

The region is chosen once and shared. `config/settings.yaml` carries `region`
(`${GCP_REGION:-asia-southeast1}`), `/healthz` reports it and the agent card prints it, so a
drifting deployment is visible. At deploy time `infra/terraform/variables.tf` validates the
effective region against `var.allowed_regions` at PLAN time, `org_policy.tf` restricts
`constraints/gcp.resourceLocations` to that region's location group, `kms.tf` creates a REGIONAL
CMEK key ring, `logging_worm.tf` puts the locked audit bucket in the same region, and `vpc_sc.tf`
stands up a dry-run-first VPC Service Controls perimeter around the AI and control-plane APIs. A
second region is a tfvars change, not a fork.

## What is honestly NOT portable, or not proven?

- The managed profile's live behaviour is unproven, because the `gcp` adapters are placeholders.
  Every claim about Gemini, BigQuery or the Hrz1 gateway in this repo is a claim about a declared
  seam, not about a call anyone has made.
- Tamper evidence is scoped to what the local sink can prove. Production tamper evidence is the
  managed WORM sink's job (Hrz5, or the locked Cloud Logging bucket), reached through the `gcp`
  audit adapter.
- The `channel` port (delivery of a finished answer to a conversational surface) is bound in all
  three profiles but is exercised only by the demo today; the API, CLI and agent paths return the
  answer directly.
- Terraform is Google-specific. The residency, CMEK and perimeter controls are GCP constructs; an
  exit to another cloud reuses the application and rewrites `infra/`.
