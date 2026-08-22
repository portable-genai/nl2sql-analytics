# Adoption FAQ

For an engineering lead forking this repository as the base for an institution's own governed
analytics service. The step-by-step lives in [`../ADOPTING.md`](../ADOPTING.md); this answers the
questions people ask before and during that.

## How do I rebrand the fork?

One script, one pass. `scripts/rename_fork.py` rewrites the python package
(`nl2sql_analytics`), the console-script name (the same token in this template, see
`[project.scripts]`), the `NL2SQL` env-var prefix stem, the Terraform `name_prefix` resource stem
(`h1-svc`) and the distribution / git id (`nl2sql-analytics`).

```bash
python scripts/rename_fork.py --package acme_analyst --cli acme-analyst \
    --env-prefix ACME --resource acme-analyst --dry-run
```

It prints the plan and writes nothing without `--yes`. Every rule is applied in ONE simultaneous
alternation, so no rule can rewrite another rule's output, which matters because the CLI name and
the package name are the same string upstream. Add `--include-docs` to sweep Markdown prose too.
It renames `src/<package>/` last, after rewriting the contents. Then recreate the venv
(`pip install -e ".[dev]"`, because the distribution name changed) and run `make gate`.

## What is the real adoption surface, beyond the rename?

The certified semantic layer. Everything this service will ever answer is decided by
`config/semantic_layer/metrics.yaml` and `policies.yaml`, so adopting the repo means replacing
that file pair with your institution's own metric catalogue and agreeing the governance around
it: who may add a metric, what review a `definition_version` bump needs, and how your
data-governance function publishes the per-dataset certification the `certification` port reads.
The engines that spend the layer (resolver, composer, validator, groundedness check) transfer
unchanged.

The second surface is the business dictionary: the hints that map a business word to a certified
metric id. Offline that is `METRIC_SYNONYMS` and `DIMENSION_WORDS` in
`adapters/local/_fixtures.py`; in a deployment it is your own data-dictionary index behind the
`dictionary` port. It authorises nothing, so getting it wrong makes the analyst worse at guessing,
never more permissive.

## Which files should I avoid diverging from, so I can take upstream fixes?

- **Upstream-owned**: `domain/kernel.py`, `domain/intent.py`, `domain/semantic_resolver.py`,
  `domain/sql_builder.py`, `domain/narration.py`, everything in `ports/`, `tests/contract/`, the
  eval harness mechanics, the container wiring (`config.py`, `assembly.py`) and the CI workflows.
- **Adopter-owned**: the whole of `config/semantic_layer/`, the offline warehouse and dictionary
  fixtures, `config/settings.yaml` values, `adapters/onprem/*`, UI theming, the golden eval
  dataset, and the jurisdiction rows in `COMPLIANCE.md`.

Track upstream by git tag and rebase your adopter-owned changes onto each release, rather than
merging `main` continuously.

## Where are the extension points?

`CONTRIBUTING.md` carries the file-by-file touch list with the test that enforces each row. The
short version:

- **A new adapter**: the class under `adapters/<family>/` with one constructor shape,
  `Adapter(settings)`, and cloud imports inside the method; the same `module:Class` target in
  `config.DEFAULT_BINDINGS` AND `config/settings.yaml` (`tests/unit/test_settings_file.py` fails
  if the two disagree); plus any new variable in `.env.example`.
- **A new port**: it must be registered in FIVE places or it runs with no enforcement at all:
  `ports/__init__.py` (`PORT_PROTOCOLS`), `config.DEFAULT_BINDINGS`, a `Container` accessor,
  `config/settings.yaml`, and a `PortCase` in `tests/contract/canonical.py`. Then bind it in all
  three families. `tests/contract/test_port_parity.py` asserts set equality across the five.
- **A new metric**: YAML only. Add it to `metrics.yaml` with its aggregation fragment, grain,
  backing dataset, `allowed_dimensions` and `definition_version`, make sure the backing dataset's
  `columns` list carries every column the fragment names, and add a golden case.
- **A new demo step**: the `Step` and its `_step_<key>` method in `scripts/demo.py`, plus the
  matching entry in `walkthrough.CHECKS`; `tests/unit/test_demo_surface.py` holds the two equal.

## What does the gate run, and how long does it take?

`make gate` is `ruff check` plus `ruff format --check` plus `mypy src` plus
`pytest -m 'not integration'` plus the offline eval, and it takes seconds. It is deliberately
OFFLINE and credential-free: no cloud SDK, no project, no network. If a change makes the gate need
any of those, the change is wrong rather than the gate. `make docs-check` additionally proves
every relative link resolves, every code fence closes and no em-dash or en-dash reached shipped
prose. `make audit` (pip-audit over both lockfiles) is separate because it needs a vulnerability
feed. `make demo-selftest` and `make portability` are the demo surface's own checks.

## How is this versioned?

`pyproject.toml`'s `version` plus git tags. The practice that would require a hand-maintained
release narrative is retired upstream in the catalog's common-base practices: a tag and a version
bump already state what a narrative would restate, and the two drift the moment anyone forgets one
of them. Record your own baseline upstream tag when you fork, so you can take future fixes.

## What is the first thing to do after `make gate` goes green?

Rebuild the eval golden set. `eval/datasets/golden_cases.jsonl` scores the pipeline against the
dataset's OWN `expected_*` fields, an independent oracle, never against the pipeline's own answer;
a fork inherits a green gate that measures the WRONG semantic layer until the cases are yours. The
metric bundle and its thresholds in `eval/run_eval.py` (`refusal_completeness` at 1.00,
`citation_accuracy`, `answer_groundedness` and `pii_safety` at 0.99) are generic and worth
keeping; register your bundle with Hrz4, which owns the promotion verdict.

## Can I deploy the fork straight away?

Not to the managed profile, and the repo enforces that rather than warning about it. Every `gcp`
adapter is still a placeholder, `managed_readiness.py` lists the operations that are, the API
process preflight refuses to start on a managed profile while any listed operation is active, and
`infra/terraform/managed_readiness.tf` fails `terraform plan` when `production_edge_enabled` is
true. Implementing those adapters and their integration tests is part of adoption. The `local`
profile is a complete, working, offline product today.
