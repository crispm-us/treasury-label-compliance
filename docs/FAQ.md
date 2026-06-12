# FAQ

Two-part structure: **Part I** is product/prototype oriented (for anyone using, integrating, or reviewing labels through the system). **Part II** is meta/evaluation oriented (for interviewers, reviewers, and architects assessing the project as a deliverable). Some topics appear in both parts because the same question serves different audiences differently.

---

# Part I — Prototype / production-oriented FAQs

*Read in this order.*

---

## 1. Everyone (first visit)

**What is this project?**
A research prototype REST API that checks US alcoholic beverage labels against TTB federal labeling rules (27 CFR Parts 4, 5, 7, and 16). It accepts label images and returns a structured compliance verdict with rule-mapped issues. Start at the root [README.md](../README.md).

**Is this an official TTB tool or legal advice?**
No. It is a prototype, not certified by TTB, and not a substitute for legal or regulatory counsel. Verdicts come from a vision model plus a deterministic rule checker.

**How does it work at a high level?**
Two layers: (1) a vision model extracts 18 structured fields from the image; (2) pure Python applies TTB rules with no AI. See [ADR-009](adr/009-two-layer-architecture.md).

**What beverage types are supported?**
Beer/malt beverages, distilled spirits, and wine. The checker selects rules based on detected `beverage_class`.

**What regulations does it check?**
Federal TTB rules only — not state requirements, COLA approval status, or nutritional labeling. Rule references: [`docs/rules/`](rules/).

**Is there a web UI?**
Not in this prototype. The deliverable is API-only ([ADR-005](adr/005-frontend-framework.md) deferred).

**Which document should I trust if docs disagree?**
**Code → `IMPLEMENTATION_STATUS.md` → `README.md` → ADRs → `requirements-analysis.md`**. See [docs/README.md](README.md).

---

## 2. Compliance reviewers and label specialists

**What do the four verdicts mean?**

| Verdict | Meaning |
|---|---|
| `COMPLIANT` | All checked rules pass |
| `NONCOMPLIANT` | At least one definitive violation (error severity) |
| `UNVERIFIABLE` | No errors, but something could not be verified |
| `ERROR` | Image unreadable or model/API failure |

See [README.md](../README.md) and [ADR-011](adr/011-extraction-schema.md).

**What is `partial_verification`?**
When `verdict=NONCOMPLIANT` and any issue has `not_found=true`: a violation is confirmed, but some fields were not visible in the submitted image(s).

**What is the difference between "not found" and "confirmed absent"?**
`not_found` means the field was not visible in what was submitted — it may exist on another panel. A confirmed absence (e.g. GWS not present at high confidence) is a definitive `NONCOMPLIANT` (R-GW-01).

**Which rules are enforced?**
Government Warning (R-GW-01–03), plus mandatory field rules per beverage class. Full inventory: [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md). Authoritative definitions: [`docs/rules/`](rules/).

**Is the Government Warning checked word-for-word?**
Yes for presence (R-GW-01), verbatim body (R-GW-02), and all-caps header (R-GW-03). **Bold formatting (R-GW-04) is extracted but not enforced** — vision-model bold detection needs calibration before production use.

**What about GWS type size, contrast, and legibility?**
Documented in [`docs/rules/government-warning-statement.md`](rules/government-warning-statement.md) (R-GW-05+) but largely **not enforced** — they require physical measurement or unreliable visual classification.

**Does it verify COLA approval?**
No. COLA integration is out of scope.

**Does it apply US rules to export/EU labels?**
Yes — it applies US TTB rules regardless of intended market. A EU-market label with no GWS will flag `NONCOMPLIANT` under US rules; that reflects jurisdiction, not necessarily a defect for its home market.

**Should I treat `NONCOMPLIANT` as final?**
No for production use. Human review is recommended for `NONCOMPLIANT` and `UNVERIFIABLE` due to OCR false positives (e.g. GWS colon misread) and model hallucination on rotated or poor images. See [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md).

**How do rule IDs map to regulations?**
Each issue includes a `rule_id` (e.g. `R-GW-01`, `R-DS-03`) linking to [`docs/rules/*.md`](rules/) with CFR citations.

**What does `schema_violations` mean in the response?**
Count of malformed field values from the model. Higher values signal lower extraction confidence — useful for triage.

---

## 3. Test labels and evaluation (using the corpus)

**Where are test images?**
[`test-labels/`](../test-labels/) — `beer/`, `wine/`, `spirits/`. See [test-labels/README.md](../test-labels/README.md).

**What are synthetic vs. real labels?**
Synthetics (`*-synth*`) are Pillow-generated with known compliant/noncompliant defects embedded in the artwork. Reals are photographs of commercial products.

**How do I use them with the API?**
Single panel: `-F "front=@test-labels/beer/sunset-ale-synth-R-GW-01-front.jpg"`. Two panels: add `-F "back=@..."`. Smoke test: `bash scripts/smoke-test.sh`.

**Why does front-only Tito's return NONCOMPLIANT but front+back COMPLIANT?**
GWS is on the back. Front-only correctly flags missing GWS; two-panel submission finds it. This demonstrates why panel coverage matters.

**Can I get images from TTB COLA Online?**
Public registry shows metadata only; label images require a TTB industry account. Alternatives: TTB Beverage Alcohol Manual PDFs, Open Food Facts, Wikimedia, or your own photos — documented in [test-labels/README.md](../test-labels/README.md).

**Which synthetics exercise which rules?**
`sunset-ale-synth-R-GW-01` (missing GWS), `iron-ridge-bourbon-synth-R-GW-03` (title-case header), `copper-creek-merlot-synth-R-WN-09` (missing sulfite declaration). Compliant baselines: `prairie-creek-lager-synth`, `blue-ridge-rye-synth`, `silverleaf-chardonnay-synth`.

**How should I submit real bottle photos?**
Front = brand/class face when possible. Back = GWS and bottler info. Slots are semantic, not geometric — swapped panels still merge correctly. Multi-face cans may need choosing two of three faces; the missed face yields `not_found` → often `UNVERIFIABLE` rather than false `NONCOMPLIANT`. See [DEPLOYMENT_CHECKLIST.md §6](DEPLOYMENT_CHECKLIST.md).

---

## 4. Technical readers — developers, integrators, and architects

### Running and integrating

**How do I run it locally?**
Python ≥ 3.10, [uv](https://github.com/astral-sh/uv), copy `.env.example` → `.env`, set an API key, `uv run uvicorn backend.app.main:app --reload`. Details: [README.md](../README.md).

**Main endpoint?**
`POST /v1/check` — multipart `front` (required), optional `back`. OpenAPI at `/docs`.

**Accepted formats and limits?**
JPEG, PNG, WebP; 10 MB per panel. HEIC/TIFF/PDF return 415. See [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md), [ADR-008](adr/008-image-preprocessing.md).

**Deployment auth?**
Set `API_KEY`; send `X-API-Key` on every request. Unset locally = no auth.

**Tests without an API key?**
`uv run --with pytest pytest tests/ -v` — extraction is mocked throughout.

**Model configuration?**
`EXTRACTION_MODEL` (primary) and `EXTRACTION_FALLBACK_MODELS` (comma-separated, sequential on retryable errors). Benchmarks favor Gemini 2.5 Flash-Lite for speed; see [latency-benchmarks.md](latency-benchmarks.md).

**Batch endpoint or verify-without-model mode?**
Neither. Batch ([ADR-007](adr/007-batch-processing-design.md)) and Mode A verify harness ([ADR-003](adr/003-dual-mode-input.md)) were not built. Tests mock extraction instead.

**What comes back besides the verdict?**
`request_id`, token usage, filenames, SHA-256 hashes, label references. Server-side JSONL audit logs in `audit_logs/` (gitignored, sensitive). See [ADR-010](adr/010-audit-logging.md).

### Architecture and design

**Why two layers instead of asking the LLM "is this compliant?"**
Reading labels is uncertain (vision); applying fixed legal rules is deterministic (Python). Mixing them produces untestable, unauditable verdicts. Layer 2 has no AI imports; every issue maps to a rule ID in [`docs/rules/`](rules/). See [ADR-009](adr/009-two-layer-architecture.md).

**How are rules maintained?**
Markdown reference files in [`docs/rules/`](rules/), validated against `compliance_checker.py` ad hoc — not loaded at runtime. Workflow: [docs/rules/README.md](rules/README.md).

**What is the extraction schema?**
18 fields, confidence `high | low | not_found`, four verdicts, two-panel merge by highest confidence. Normative: [ADR-011](adr/011-extraction-schema.md).

**Why LiteLLM?**
Provider abstraction and multi-model fallback without vendor lock-in. Library in prototype; proxy recommended for production ([ADR-002](adr/002-litellm-library-vs-proxy.md)).

**How is hallucination mitigated?**
Prompt forbids completing GWS from memory; text evidence overrides false `gws_present`; R-META-02 cross-checks `abv_pct` vs `abv_text`. Still a known limitation on poor images.

**What is built vs. deferred?**
[IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md) is authoritative. [docs/adr/README.md](adr/README.md) maps each ADR to implementation status — several ADRs describe accepted designs not yet built.

**Does it meet the original <5 s SLA?**
Single-panel yes with Flash-Lite (~2.5 s warm). Two-panel borderline (~5.1 s). Full accounting: [latency-benchmarks.md](latency-benchmarks.md).

---

# Part II — Meta FAQs (evaluating this work)

*For interviewers, reviewers, and architects assessing the project as a deliverable. Assumes you have read Part I.*

---

## 5. Evaluating the project — scope, process, and architecture

**What was the original ask vs. what was delivered?**
[requirements-analysis.md](requirements-analysis.md) specified React UI, batch upload, Mode A verify harness, HEIC conversion, 5 s SLA, and image resize/backoff. [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md) is the honest built-vs-deferred accounting. When they conflict, implementation status and code win.

**What is the core design insight worth explaining?**
Strict separation of AI extraction (Layer 1) from deterministic compliance checking (Layer 2). Compliance logic is auditable, version-controlled, and unit-testable independent of the model. Everything else — multi-provider fallback, audit logging, rule files as repo artifacts — supports that separation.

**Where is design thinking documented?**
[docs/adr/](adr/) — decisions with explicit trade-offs and alternatives rejected. [docs/project-log.md](project-log.md) — stakeholder inputs, iteration, debugging (sanitize before public push per [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)).

**How do I quickly assess architectural completeness?**
Read [docs/adr/README.md](adr/README.md) status table alongside [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md). Built: two-layer pipeline (009), extraction schema (011), FastAPI (004), Railway target (006), partial audit (010), partial preprocessing (008). Not built: UI (005), batch (007), Mode A (003).

**Why keep `requirements-analysis.md` if much is deferred?**
Historical context for scope decisions and stakeholder constraints (no COLA integration, no persistent storage, verbatim GWS requirement). Not current behavior.

**What would production need beyond this prototype?**
Human review queue for NONCOMPLIANT/UNVERIFIABLE; schema version gate; Unicode normalization for GWS; calibrated R-GW-04 bold check; full image preprocessing; rate limiting; COLA integration; net-contents parsing; appellation verification; deployment hardening. Listed in [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md).

**How was quality validated beyond unit tests?**
Synthetic labels with embedded defect markers; real bottle/can photographs; `scripts/smoke-test.sh`; `scripts/benchmark-latency.sh`. Real labels exposed rotation, multi-panel, and hallucination edge cases documented in [DEPLOYMENT_CHECKLIST.md §6](DEPLOYMENT_CHECKLIST.md) and [project-log.md](project-log.md).

**What known failure modes should an evaluator probe?**
GWS OCR false positives on punctuation (R-GW-03); hallucinated GWS body on rotated images (Glenlivet); ABV numeric hallucination vs correct text (Mike's Harder); three-face cans missing net contents when only two panels submitted (Henninger). These motivate human review, not algorithmic fixes alone.

**What artifacts demonstrate honest scoping?**
[IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md) (built/deferred/not started); ADR status icons in [docs/adr/README.md](adr/README.md); prototype notice in [README.md](../README.md); deferred rules (R-GW-04, R-MB-03) explained with *why*, not just *what*.

---

## 6. Test labels and evaluation (assessing the test strategy)

*Same corpus as Part I §3, but framed for evaluators judging coverage and rigor.*

**Does the test corpus demonstrate the architecture or production readiness?**
It demonstrates the architecture and rule coverage honestly. Synthetics prove deterministic checker paths; reals reveal model limitations. It is not a statistically validated production test suite.

**What defect coverage exists vs. gaps?**
Covered: R-GW-01, R-GW-03, R-WN-09 (synthetics). Not yet generated: R-GW-04 (full body bold), R-DS-03 ABV/proof defects, R-WN-03 tolerance band, R-MB-03 flavored-malt ABV. Matrix in [test-labels/README.md](../test-labels/README.md).

**What did real-label testing reveal that synthetics did not?**
EXIF/rotation handling (Glenfiddich, Glenlivet); mixed-case GWS headers on otherwise compliant labels (Ron Ron); vertical GWS layout; flavored malt ABV cross-field mismatch (Mike's Harder); EU-market label behavior (Jack Daniel's EU). Documented with expected verdicts in [DEPLOYMENT_CHECKLIST.md §6](DEPLOYMENT_CHECKLIST.md).

**How complete is the real-label smoke matrix?**
Several products are confirmed (Tito's, Henninger, Stiegl, Heineken, Ron Ron, Mike's Harder, etc.); others marked `unverified*` pending smoke-test runs. Checklist tracks progress.

**Why include TTB COLA research if images aren't public?**
Shows domain research: TTB submits one image per panel (aligns with two-panel API design); COLA images require industry login (explains why corpus uses BAM, Open Food Facts, and own photos). Recorded in [project-log.md](project-log.md).

**What scripts should an evaluator run?**
`uv run --with pytest pytest tests/ -v` (no keys); `bash scripts/smoke-test.sh` (needs running server + key); `./scripts/benchmark-latency.sh` (optional, needs keys).

---

## Structure summary

| Part | Sections | Audience |
|---|---|---|
| **I — Product** | 1 Everyone → 2 Compliance → 3 Test labels (usage) → 4 Technical (dev + architect) | Users of the prototype / eventual production |
| **II — Meta** | 5 Evaluating the project → 6 Test labels (assessment) | Interviewers and technical evaluators |

Overlap is intentional: test labels appear in I §3 (how to use) and II §6 (what they prove). Architecture appears in I §4 (how it works) and II §5 (why it matters for assessment). Evaluators read both; product readers can stop after Part I.
