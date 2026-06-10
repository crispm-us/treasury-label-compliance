# Implementation Status

This document maps each Architecture Decision Record to its current build state, and lists what is deliberately deferred vs. not yet started. It exists so reviewers can assess scope honestly without having to diff ADRs against the code.

---

## Built and working

### Core two-layer pipeline (ADR-009)
The full request path is implemented end-to-end:
- `POST /v1/check` accepts one or two label images (JPEG, PNG, WebP)
- Layer 1 (`backend/app/services/extractor.py`) sends images to the Claude vision API with a structured extraction prompt and returns a typed `ExtractionResult`
- Layer 2 (`backend/app/services/compliance_checker.py`) applies deterministic TTB rules and returns a `ComplianceResult` with verdict and rule-mapped issues
- The two layers are fully decoupled — Layer 2 has no AI imports and is independently unit-testable

### Extraction schema (ADR-011)
The 18-field extraction schema is implemented, including:
- `confidence` enum (`high | low | not_found`) with documented semantics
- `verdict` enum (`COMPLIANT | NONCOMPLIANT | UNVERIFIABLE | ERROR`)
- Two-panel merge: field-by-field highest-confidence wins; ties to non-null value; `readable` is True if either panel is readable
- `partial_verification` flag: True when `verdict=NONCOMPLIANT` and any issue has `not_found=True`
- `not_found` flag on individual issues (distinct from a confirmed-absent field)
- Anti-hallucination prompt instructions (do not complete GWS text from memory)
- GWS flag contradiction fix: text evidence overrides `gws_present` boolean

### TTB compliance rules implemented
All rules are mapped to rule IDs documented in `docs/rules/`.

Government Warning Statement (27 CFR Part 16 — all beverage classes):
- **R-GW-01**: GWS must be present
- **R-GW-02**: GWS body must match verbatim canonical text (27 CFR §16.21)
- **R-GW-03**: GWS header must be exactly `GOVERNMENT WARNING:` in all-caps

Beer / malt beverages (27 CFR Part 7):
- **R-MB-01**: Brand name required
- **R-MB-02**: Class/type designation required
- **R-MB-03**: ABV warning (required for flavored malt beverages; not universal)
- **R-MB-04**: Net contents (metric) required
- **R-MB-05**: Brewer/bottler name and address required

Distilled spirits (27 CFR Part 5):
- **R-DS-01**: Brand name required
- **R-DS-02**: Class/type designation required
- **R-DS-03**: ABV required; range check (20%–95%); proof consistency check (proof = 2 × ABV ± 0.3)
- **R-DS-04**: Net contents (metric) required
- **R-DS-06**: Distiller/bottler name and address required

Wine (27 CFR Part 4):
- **R-WN-01**: Brand name required
- **R-WN-02**: Class/type designation required
- **R-WN-03**: ABV required; range check (0.5%–24.0%)
- **R-WN-04**: Net contents (metric) required
- **R-WN-05**: Winery/bottler name and address required
- **R-WN-08**: Appellation required when vintage is stated
- **R-WN-09**: Sulfite declaration warning (cannot verify SO₂ level from image)

### API and infrastructure (ADR-004, ADR-006, ADR-010)
- FastAPI with auto-generated OpenAPI docs (`/docs`)
- `GET /healthz` health check
- Optional `X-API-Key` authentication (enforced when `API_KEY` env var is set; bypassed for local dev)
- JSONL audit log with per-day rotation and thread-safe writes (`audit_logs/YYYY-MM-DD.jsonl`)
- `AUDIT_ENABLED` flag for disabling writes in tests
- Model error capture and classification in audit log (status codes 401, 400, 429, 500/529)
- `uv`-managed dependencies with `uv.lock` for reproducible installs

### Test suite
- 36 tests, 0 failures on Python 3.14
- All extraction mocked — no API key required, no network calls
- Coverage: all verdict paths, all implemented rule IDs, model API failures, partial verification flag, API key auth, two-panel readable merge, empty-string mandatory field bypass

---

## Deferred (design decisions documented, not yet built)

### R-GW-04 — GWS bold-type requirement
**ADR reference:** ADR-011 §Deferred rules

The GWS header must be bold and the body must not be bold (27 CFR §16.22(a)(2)). The `gws_header_bold` and `gws_body_bold` fields are extracted and stored in the schema but not evaluated. Vision-model bold detection is not reliable without a calibration baseline on real labels. Activate after evaluating accuracy on a representative sample.

### R-MB-03 — Flavored malt beverage ABV rule
**ADR reference:** ADR-011

ABV is mandatory for flavored malt beverages and products where flavor contributes alcohol, but not for traditional beer/ale/lager/stout. The current implementation issues a warning for any beer label where ABV is not visible. The correct production behavior requires detecting whether the product is a flavored malt beverage, which is difficult from label text alone.

### Multi-provider model routing (ADR-001, ADR-002)
**ADR reference:** ADR-001 §Multi-provider strategy, ADR-002

ADR-001 documents a multi-provider strategy (Claude primary, Gemini and GPT-4o as fallbacks) and ADR-002 selects LiteLLM as the abstraction layer. Currently only the Anthropic SDK is used directly. LiteLLM integration and provider fallback routing are not implemented. Budget-capped keys for Gemini and GPT-4o are pending.

### Retry and backoff (ADR-008)
**ADR reference:** ADR-008 §Retry strategy

The extractor makes a single model call per panel with no retry on transient failures. The audit log documents recommended actions per status code (exponential backoff for 429, do-not-retry for 401/400), but no retry loop is implemented.

### Image preprocessing pipeline (ADR-008)
**ADR reference:** ADR-008

ADR-008 documents preprocessing steps: upload size limit enforcement (beyond content-type check), magic-byte MIME validation, orientation correction (EXIF), resolution normalization, and contrast enhancement for low-quality scans. None of these are implemented. The current check is MIME type from the multipart header only.

### Frontend (ADR-005)
**ADR reference:** ADR-005

ADR-005 selects a minimal web UI (file drag-and-drop, structured results display). Not implemented — the current deliverable is API-only.

### Batch processing (ADR-007)
**ADR reference:** ADR-007

ADR-007 documents a batch endpoint for processing multiple labels in a single request (e.g. for pre-market screening of a product line). Not implemented.

### Schema version gate (ADR-011)
**ADR reference:** ADR-011 §Schema evolution

`ExtractionResult.from_dict` accepts any `schema_version` value without validation. A production implementation should reject or flag results with an unexpected schema version to catch model prompt / schema drift.

### Unicode normalization for GWS verbatim check
Comparison of extracted GWS text against the canonical body (27 CFR §16.21) uses whitespace normalization only. A production version should also normalize Unicode (e.g. smart quotes, em-dashes, non-breaking spaces) before comparison, since OCR output and model transcription can introduce these.

### ABV range check for `low`-confidence values
The ABV range check (R-DS-03, R-WN-03) only runs at `high` confidence. A `low`-confidence ABV that is clearly out of range (e.g. 150%) is not flagged.

---

## Not started (out of scope for this prototype)

- Certificate of Label Approval (COLA) integration — verifying that the label matches a TTB-approved COLA on file
- Net contents and metric equivalence verification (the model extracts text; the prototype does not parse or cross-check metric vs. US customary values)
- Country-of-origin rules (captured in schema; no rules implemented)
- Vintage year format validation
- Appellation verification against approved AVA/GI lists
- Multi-language label handling
- Production deployment hardening (rate limiting, request signing, structured logging, monitoring)
