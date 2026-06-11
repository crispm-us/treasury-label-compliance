# Implementation Status

This document maps each Architecture Decision Record to its current build state, and lists what is deliberately deferred vs. not yet started. It exists so reviewers can assess scope honestly without having to diff ADRs against the code.

---

## Built and working

### Core two-layer pipeline (ADR-009)
The full request path is implemented end-to-end:
- `POST /v1/check` accepts one or two label images (JPEG, PNG, WebP)
- Layer 1 (`backend/app/services/extractor.py`) sends images to a configurable vision model via LiteLLM and returns a typed `ExtractionResult`
- Layer 2 (`backend/app/services/compliance_checker.py`) applies deterministic TTB rules and returns a `ComplianceResult` with verdict and rule-mapped issues
- The two layers are fully decoupled — Layer 2 has no AI imports and is independently unit-testable

### Extraction schema (ADR-011)
The 18-field extraction schema is implemented, including:
- `confidence` enum (`high | low | not_found`) with documented semantics
- `verdict` enum (`COMPLIANT | NONCOMPLIANT | UNVERIFIABLE | ERROR`)
- Two-panel merge: field-by-field highest-confidence wins; ties to non-null value; `readable` is True if either panel is readable
- `partial_verification` flag: True when `verdict=NONCOMPLIANT` and any issue has `not_found=True` (violation confirmed but some fields were not visible)
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
- **R-DS-03**: ABV required; range check (20%–95%) at `high` confidence (error) and `low` confidence (warning); proof consistency check (proof = 2 × ABV ± 0.3)
- **R-DS-04**: Net contents (metric) required
- **R-DS-06**: Distiller/bottler name and address required

Wine (27 CFR Part 4):
- **R-WN-01**: Brand name required
- **R-WN-02**: Class/type designation required
- **R-WN-03**: ABV required; range check (0.5%–24.0%) at `high` confidence (error) and `low` confidence (warning)
- **R-WN-04**: Net contents (metric) required
- **R-WN-05**: Winery/bottler name and address required
- **R-WN-08**: Appellation required when vintage is stated; `not_found=True` when appellation was not visible
- **R-WN-09**: Sulfite declaration warning (cannot verify SO₂ level from image)

### Multi-provider model routing (ADR-001, ADR-002)
LiteLLM is the provider abstraction layer (`extractor.py` uses `litellm.completion()`). Any LiteLLM-supported provider can be selected via the `EXTRACTION_MODEL` environment variable (format: `provider/model-name`, default: `anthropic/claude-haiku-4-5-20251001`). A sequential fallback list is configurable via `EXTRACTION_FALLBACK_MODELS` (comma-separated list of model strings). Non-retryable errors (401, 400) halt fallback immediately; all other errors (429, 500, network) try the next model in sequence. The `extraction_model` field in the API response reflects the model that actually produced the result, not the configured primary. Budget-capped API keys for Gemini Flash and GPT-4o are pending acquisition for end-to-end fallback testing.

### API and infrastructure (ADR-004, ADR-006, ADR-010)
- FastAPI with auto-generated OpenAPI docs (`/docs`)
- `GET /healthz` health check
- Optional `X-API-Key` authentication (enforced when `API_KEY` env var is set; bypassed for local dev)
- JSONL audit log with per-day rotation and thread-safe writes (`audit_logs/YYYY-MM-DD.jsonl`); includes token usage per request
- `AUDIT_ENABLED` flag for disabling writes in tests
- Model error capture and classification in audit log (status codes 401, 400, 429, 500/529)
- `uv`-managed dependencies with `uv.lock` for reproducible installs

### Upload validation (ADR-008)
- Upload size limit: 10 MB per image; returns 413 before reading the full payload (reads `MAX_IMAGE_BYTES + 1` bytes to detect overflow efficiently)
- Magic-byte MIME validation: returns 415 when file content does not match a recognized JPEG/PNG/WebP signature, regardless of the `Content-Type` header supplied by the client
- `Content-Type: image/jpg` accepted as an alias for `image/jpeg` (common client mislabeling)
- Sniffed MIME type used for the LiteLLM data URI, not the client-declared type — a client sending PNG bytes with `Content-Type: image/jpeg` is handled correctly
- Magic-byte check is a necessary but not sufficient guard against corrupt uploads: a file with a valid header but a truncated or corrupt body passes validation and will produce an `ERROR` verdict from Layer 1. For production, the recommended addition is a minimum file size threshold (e.g. 4 KB — no real label at any useful resolution is smaller) plus optionally `Pillow.Image.verify()` for full structural validation. `Pillow` is not a current dependency; adding it is the production upgrade path.

### Test suite
- 56 tests, 0 failures on Python 3.10
- All extraction mocked — no API key required, no network calls
- Coverage: all verdict paths, all implemented rule IDs, extractor fallback logic (429 retry, 500 retry, 401 no-retry, 400 no-retry, all-fallbacks-exhausted), non-dict JSON guard in `_extract_single`, empty-choices and null-content crash guard in `_extract_single`, invalid confidence string rejection, `not_found`-with-non-null-value rejection, low-confidence ABV range check (R-DS-03, R-WN-03), R-GW-02 case-insensitive body check (all-caps real-label pass), upload size limit (413), magic-byte MIME validation (415), `image/jpg` alias, API key auth, token usage fields in response, partial verification flag, two-panel token summation, two-panel readable merge, empty-string and whitespace-only mandatory field bypass

---

## Deferred (design decisions documented, not yet built)

### R-GW-04 — GWS bold-type requirement
**ADR reference:** ADR-011 §Deferred rules

The GWS header must be bold and the body must not be bold (27 CFR §16.22(a)(2)). The `gws_header_bold` and `gws_body_bold` fields are extracted and stored in the schema but not evaluated. This is a **probabilistic visual classification problem**: the model must judge whether printed text appears bold — a property that varies with font weight, contrast, image quality, and camera angle. There is no post-processing step that corrects an incorrect visual observation; false positives would flag compliant labels. Activate only after evaluating accuracy against a labeled sample of real labels.

### R-MB-03 — Flavored malt beverage ABV rule
**ADR reference:** ADR-011

ABV is mandatory for flavored malt beverages and products where flavor contributes alcohol, but not for traditional beer/ale/lager/stout. The current implementation issues a warning for any beer label where ABV is not visible. The correct production behavior requires detecting whether the product is a flavored malt beverage, which is difficult from label text alone.

### Retry and backoff (ADR-008)
**ADR reference:** ADR-008 §Retry strategy

The extractor implements sequential provider-switching fallback: on a retryable error (429, 500, network) it tries each model in `EXTRACTION_FALLBACK_MODELS` in order before giving up. What is **not** implemented is per-provider exponential backoff with jitter — the extractor makes a single attempt per model and moves on. The audit log documents recommended per-status-code actions (exponential backoff for 429, do-not-retry for 401/400). A production implementation would add a retry loop with jitter around each model call.

### Image preprocessing pipeline (ADR-008)
**ADR reference:** ADR-008

Not implemented: orientation correction (EXIF), resolution normalization, contrast enhancement for low-quality scans. See the Upload validation section above for what is implemented and for the minimum-file-size / Pillow production upgrade path.

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
Comparison of extracted GWS text against the canonical body (27 CFR §16.21) uses whitespace normalization only. A production version should also normalize Unicode (e.g. smart quotes → straight quotes, em-dashes → hyphens, zero-width spaces, ligatures) before comparison, since model transcription can introduce these. This is a **deterministic text-processing problem**: `unicodedata.normalize("NFKC", text)` plus an explicit character map would be sufficient. It is deferred because real printed labels use standard ASCII in practice, making this a low-probability edge case for the prototype.

Note: Unicode normalization and R-GW-04 bold detection are superficially similar (both deferred text/visual analysis tasks) but differ fundamentally in nature. Unicode normalization is a known, solvable implementation task with no accuracy uncertainty. Bold detection is a probabilistic visual classification problem whose accuracy is empirically unknown; deploying it without calibration would introduce false positives. They are deferred for different reasons and require different production investment.

---

## Not started (out of scope for this prototype)

- Certificate of Label Approval (COLA) integration — verifying that the label matches a TTB-approved COLA on file
- Net contents and metric equivalence verification (the model extracts text; the prototype does not parse or cross-check metric vs. US customary values)
- Country-of-origin rules (captured in schema; no rules implemented)
- Vintage year format validation
- Appellation verification against approved AVA/GI lists
- Multi-language label handling
- Production deployment hardening (rate limiting, request signing, structured logging, monitoring)
