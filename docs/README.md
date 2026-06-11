# Documentation Map

This directory has multiple doc layers written at different stages of the project. Start here.

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

**Pre-deploy steps:** `../docs/DEPLOYMENT_CHECKLIST.md`

**Test label corpus:** `../test-labels/README.md`

**Design evolution / interview narrative:** `project-log.md` (sanitize before public push — see DEPLOYMENT_CHECKLIST §1)
