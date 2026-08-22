# FAQ index

Answers to the questions different teams ask when evaluating, adopting, or reviewing this
repository (H1, the NL2SQL Semantic Analyst) as a common base for governed natural-language
analytics. Each file is written for a specific audience; skim the one that matches your role.

| FAQ | For | Answers |
|---|---|---|
| [security-faq.md](security-faq.md) | AppSec / security review | whether a prompt can emit arbitrary SQL, what constrains the composed query, what happens to an uncertified metric, row-level scoping, what the guardrail port screens, identity, secrets, supply chain, the audit chain |
| [portability-faq.md](portability-faq.md) | Architecture / cloud / exit planning | no-lock-in, the three profiles, the sovereign exit, data export, what is honestly not portable |
| [features-faq.md](features-faq.md) | Product / data and analytics / delivery | what the analyst does, what is deterministic vs model, and the boundary with sibling platform systems |
| [adoption-faq.md](adoption-faq.md) | Engineering leads forking the repo | rename, upstream fixes, extension points, the semantic layer as the real adoption surface |
| [compliance-faq.md](compliance-faq.md) | Compliance / data governance / model risk | regulatory posture, PII, maker-checker, residency, the eval gate, model-risk evidence |

These FAQs deliberately do **not** re-document capabilities owned by sibling systems in the GRC
catalog (the [organization front page](https://github.com/portable-genai), which is the
authoritative per-system list). Where a concern belongs to another repo
(the guardrail gateway, the human-review console, the eval platform, the data-quality agent, and
so on), the FAQ points at it and explains the boundary rather than duplicating it. See
[features-faq.md](features-faq.md) for the full "what this repo owns vs what it integrates" map,
[../model-card.md](../model-card.md) for the model boundary, and
[../../COMPLIANCE.md](../../COMPLIANCE.md) for the per-principle status with its evidence files.
