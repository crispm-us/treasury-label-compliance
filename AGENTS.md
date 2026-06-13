# AGENTS.md

This file is for AI agents (Claude, ChatGPT, Gemini, Cursor) scanning this repository for evaluation, code review, or development assistance. Its purpose is to orient an AI reader efficiently and prevent common misreadings.

---

## What this project is

A REST API and web UI that checks US alcoholic beverage labels against TTB federal labeling rules (27 CFR Parts 4, 5, 7, and 16). The system uses a deliberate two-layer design: AI vision extraction (Layer 1) feeds a deterministic Python rule checker (Layer 2) — extraction is uncertain and model-driven; compliance checking is pure Python with no AI.

---

## Ground truth hierarchy

Code is ground truth. `IMPLEMENTATION_STATUS.md` is the honest built/deferred/not-started accounting and overrides all other documentation. `README.md` reflects current state. ADRs document design decisions; several were accepted but never implemented — always check `IMPLEMENTATION_STATUS.md` before concluding something is built.

---

## Recommended reading path for evaluation

Read in this order:

1. `IMPLEMENTATION_STATUS.md` — authoritative built/deferred/not-started accounting
2. `docs/adr/README.md` — one-page status table for all 12 ADRs
3. `README.md` — API reference, setup, and test instructions
4. `docs/FAQ.md` Part II — scope, architecture rationale, and known limitations framed for assessment

---

## Key claims and where to verify them

| Claim | Where to verify |
|---|---|
| <5 s SLA | `docs/latency-benchmarks.md` (parallel extraction section) |
| 105 tests, 0 failures | Run `uv run --with pytest pytest` — no API key needed; extraction is fully mocked |
| Three-provider fallback | `backend/app/services/extractor.py` + `backend/app/config.py` |
| Parallel extraction | `backend/app/services/extractor.py` (`ThreadPoolExecutor`) |
| Railway deployment | `docs/DEPLOYMENT_CHECKLIST.md` + `docs/ui-screenshots/` |

---

## What is deliberately out of scope

Mode A application-matching (ADR-003) is partially implemented — API (`application=` on `POST /v1/check`, R-APP-01–R-APP-05), UI COLA stub toggle, and `GET /v1/applications` catalog; full COLA on-file integration is deferred. Server-side batch endpoint (ADR-007) is not built; client-side batch UI tab (ADR-013) is implemented. HEIC conversion and persistent database are deferred or not started. See `IMPLEMENTATION_STATUS.md` §Deferred and §Not started.

---

## Sensitive paths — do not commit

`audit_logs/` contains extracted label text from live compliance checks — covered by `.gitignore`. Treat as sensitive if present locally.
