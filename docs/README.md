# Documentation Map

This directory has multiple doc layers written at different stages of the project. Start here.

---

## Ground truth

Code and `IMPLEMENTATION_STATUS.md` reflect current reality. ADRs describe accepted design decisions, some of which are not yet implemented. `requirements-analysis.md` is historical context only — treat it as the original stakeholder spec, not current behavior.

---

## Reading paths

### Evaluator / technical reviewer path

Read in this order:

1. `docs/FAQ.md` Part II — scope, architecture rationale, and known limitations framed for assessment
2. `IMPLEMENTATION_STATUS.md` — authoritative built/deferred/not-started accounting
3. `docs/adr/README.md` — one-page status table for all 12 ADRs
4. Selected ADRs: [009](adr/009-two-layer-architecture.md) (two-layer architecture), [011](adr/011-extraction-schema.md) (extraction schema), [001](adr/001-vision-model-selection.md) (model selection and SLA)
5. `README.md` — setup, API reference, and test instructions

### Developer / deployer path

Read in this order:

1. `README.md` — quick start, API reference, and configuration
2. `.env.example` — required environment variables
3. `docs/rules/` — TTB rule reference files by beverage class
4. `docs/DEPLOYMENT_CHECKLIST.md` — Railway deployment and real-label smoke test matrix

---

## Reading order

1. **`../README.md`** (repo root) — API contract, quick start, configuration. The entry point for everyone.
2. **`../IMPLEMENTATION_STATUS.md`** — what is built vs. deliberately deferred. Read this before the ADRs.
3. **`rules/`** — TTB rule definitions enforced by Layer 2. Start with `rules/README.md`.
4. **`adr/`** — design rationale. See `adr/README.md` for a status summary of each decision.

## When docs conflict, trust this order

```
Code  >  IMPLEMENTATION_STATUS.md  >  README.md  >  ADRs  >  requirements-analysis.md
```

Several ADRs (003, 005, 007) describe designs accepted during planning but not implemented in this prototype. `IMPLEMENTATION_STATUS.md` is the authoritative record of what is actually built. `requirements-analysis.md` is the original stakeholder spec written before scope decisions were made — treat it as historical context, not current behavior.

## By audience

**Running the API:** `../README.md` quick start → `../scripts/smoke-test.sh`

**Understanding compliance rules:** `rules/README.md` → individual rule files

**Architectural rationale:** `adr/README.md` (index) → individual ADRs for context

**Performance data:** `latency-benchmarks.md`

**Pre-deploy steps:** `DEPLOYMENT_CHECKLIST.md`

**Test label corpus:** `../test-labels/README.md`

**Design evolution / interview narrative:** [docs/adr/](adr/) (decision rationale), [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md) (built vs. deferred), [DEPLOYMENT_CHECKLIST.md §6](DEPLOYMENT_CHECKLIST.md) (real-label smoke matrix)

**Questions from any audience:** `FAQ.md` — Part I for users and integrators, Part II for evaluators and interviewers
