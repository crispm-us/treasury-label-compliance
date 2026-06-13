# Implementation Status

This document maps each Architecture Decision Record to its current build state, and lists what is deliberately deferred vs. not yet started. It exists so reviewers can assess scope honestly without having to diff ADRs against the code.

---

## Built and working

### Core two-layer pipeline (ADR-009)
The full request path is implemented end-to-end:
- `POST /v1/check` accepts one or two label images (JPEG, PNG, WebP)
- Layer 1 (`backend/app/services/extractor.py`) sends images to a configurable vision model via LiteLLM and returns a typed `ExtractionResult`. When both panels are submitted, the two `_extract_single` calls run concurrently via `ThreadPoolExecutor(max_workers=2)`; the FastAPI handler wraps the sync `extract()` call in `asyncio.to_thread()` so the event loop is not blocked. Two-panel wall-clock latency: ~5.1s sequential → ~2.2s parallel (Gemini Flash-Lite; 57% reduction).
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
LiteLLM is the provider abstraction layer (`extractor.py` uses `litellm.completion()`). Any LiteLLM-supported provider can be selected via the `EXTRACTION_MODEL` environment variable (format: `provider/model-name`, default: `gemini/gemini-2.5-flash-lite`). A sequential fallback list is configurable via `EXTRACTION_FALLBACK_MODELS` (comma-separated list of model strings). Non-retryable errors (401, 400) halt fallback immediately; all other errors (429, 500, network) try the next model in sequence. The `extraction_model` field in the API response reflects the model that actually produced the result, not the configured primary. Budget-capped API keys for Gemini Flash and GPT-4o are pending acquisition for end-to-end fallback testing.

### API and infrastructure (ADR-004, ADR-006, ADR-010)
- FastAPI with auto-generated OpenAPI docs (`/docs`)
- `GET /healthz` health check
- `GET /version` — returns `{commit, environment, branch}` from Railway-injected env vars (`RAILWAY_GIT_COMMIT_SHA[:7]`, `RAILWAY_ENVIRONMENT_NAME`, `RAILWAY_GIT_BRANCH`); falls back to `"dev"` in local dev
- Optional `X-API-Key` authentication (enforced when `API_KEY` env var is set; bypassed for local dev)
- Per-IP rate limiting on `POST /v1/check`: configurable via `RATE_LIMIT_PER_MIN` (default **60 requests/minute**) via `slowapi`. Returns HTTP 429 when exceeded. `GET /healthz` and `GET /version` are not rate-limited. Behind Railway's reverse proxy, `get_remote_address` reads `request.client.host` — if the real client IP is needed, a custom `key_func` reading `X-Forwarded-For` is the upgrade path (not required for current 1–2 user audience).
- `CheckResponse` includes `duration_ms: float | None` — server-side extraction wall time in milliseconds (also stored in audit log as `extraction_duration_ms`)
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

### Extraction schema (ADR-011) — receipt fields and schema violation tracking

Receipt fields added to API response and audit log (FR-07):
- `front_filename` / `back_filename`: original client-supplied filename
- `front_label_ref` / `back_label_ref`: `{stem}-{YYYYMMDDTHHmmss}Z` — human-readable unique reference correlating the submission to the audit log entry without a database
- `front_sha256` / `back_sha256`: SHA-256 hex of received image bytes (pre-EXIF-rotation), providing a content-addressable receipt the caller can verify

Schema violation tracking (see ADR-011 §Layer 1 Schema Violations):
- Non-dict field values from the model are recorded in `schema_violations` (list in audit log, count in API response)
- `EXTRACTION_SCHEMA_STRICT=true` env flag treats violations as ExtractionError (default: false — violations are logged but extraction proceeds)
- Single-panel path now has the same isinstance guard as the two-panel merge path via `_sanitize_fields()`

### ABV cross-validation (R-META-02)

New cross-field rule applied after all beverage-class checks: if `abv_pct` and `abv_text` are both present with usable confidence, the numeric value parsed from `abv_text` is compared with `abv_pct`. A discrepancy > 0.2% fires R-META-02 at warning severity. Motivated by Mike's Harder hallucination: `abv_pct=5.0` at high confidence while `abv_text="8% ALC. BY VOL."` correctly read 8%.

The hallucination was internally self-consistent: the model also returned `proof=10.0`, which correctly equals 2 × 5.0. The proof-consistency check therefore passed, and the ABV range check passed (5% is plausible for a flavored malt beverage). Only cross-referencing `abv_pct` against the independently-read `abv_text` ("8%") exposes the contradiction. This is why R-META-02 cross-checks two fields rather than validating either in isolation.

### Mode A application-matching (ADR-003) — partial
Regulation checks (Layer 2) plus application-match checks when optional `application` JSON is supplied on `POST /v1/check`. Full COLA integration (lookup against TTB on-file records) remains out of scope.

- `backend/app/models/application.py` — `ApplicationFields` schema
- `backend/app/services/application_checker.py` — R-APP-01 through R-APP-05
- `test-labels/applications/` — 12 application JSON stubs (9 synthetic Mode A fixtures + 3 real-label stubs: Tito's Handmade Vodka, Sierra Nevada Pale Ale, Angry Orchard Iceman)
- `GET /v1/applications` — read-only catalog endpoint returning the 6-entry curated picker list (real labels + compliant synthetics; R-APP-* violation fixtures excluded)

Application JSON is assumed authoritative: null means the field was not declared for this product; non-null values are ground truth for comparison. The checker never validates application field values.

**Known R-APP false positive patterns (observed in Railway smoke tests, 2026-06-12):**

- **R-APP-01 (brand name)** — high false-positive rate. Two failure modes: (1) model extracts the most prominent display headline instead of the COLA-declared brand name — e.g. "CANYON RIDGE" vs "Canyon Ridge Bourbon", "MESA VERDE" or "MESA VERDE WINERY" vs "Mesa Verde Chardonnay"; (2) model extracts a shortened form — e.g. "Tito's" vs "Tito's Handmade Vodka". Root cause is extraction accuracy, not schema design. Production fix: improve the extraction prompt to distinguish brand name from producer entity name. A normalized substring heuristic (if extracted brand is a substring of declared brand or vice versa, treat as tentative match) would address case (2) but not case (1). See FAQ §4 for the full analysis of why a two-field schema approach does not apply here.

- **R-APP-05 (origin)** — high false-positive rate. Root cause: exact string comparison against a single declared origin value, while the vision model extracts origin at varying specificity levels (state name, city+state, "American", etc.). Fixed in the `origin_as_stated` / `origin_iso2_country` redesign — see `application.py` and FAQ §4. Post-prompt LBL-AUD-0612 (2026-06-12): extraction improvement for beer and spirits — model now reads origin from the class/type line on the label face ("AMERICAN LAGER" → "American"; "Kentucky Straight Bourbon Whiskey" → "Kentucky") rather than the bottler address. Wine labels lack a geographic anchor in the class/type text; R-APP-05 false-positive rate remains high for wine.

- **R-APP-04 (net contents)** — correctly detected post-prompt LBL-AUD-0612: label "1.0 L" vs stub "750 mL" fires as expected (Canyon Ridge R-APP-04 batch run, 2026-06-12). Previously a miss when the model returned `not_found` for `net_contents`. Unit-parsing (liters ↔ milliliters) is not implemented; the checker does normalized string comparison only.

Without `application`, Mode B behavior is unchanged (`mode: "regulation_only"`).

### Test suite
- 105 tests, 0 failures on Python 3.14 (uv run --with pytest pytest)
- All extraction mocked — no API key required, no network calls
- `client` fixture clears `API_KEY` via `monkeypatch.setattr("backend.app.main.API_KEY", "")` to isolate tests from host environment
- `client` fixture calls `limiter._storage.reset()` before each test — see **slowapi test interference** below
- Coverage: all verdict paths, all implemented rule IDs, extractor fallback logic (429 retry, 500 retry, 401 no-retry, 400 no-retry, all-fallbacks-exhausted), non-dict JSON guard in `_extract_single`, empty-choices and null-content crash guard in `_extract_single`, invalid confidence string rejection, `not_found`-with-non-null-value rejection, low-confidence ABV range check (R-DS-03, R-WN-03), R-GW-02 case-insensitive body check (all-caps real-label pass), R-GW-02 at high confidence (→ NONCOMPLIANT error), proof mismatch at low confidence (→ R-DS-03 warning, not error), R-WN-08 empty-string appellation bypass (same guard as mandatory field bypass), R-META-01 null beverage class (→ UNVERIFIABLE), `gws_present=true` with no extractable text (→ single R-GW-01 not_found warning; R-GW-02/03 suppressed), upload size limit (413), magic-byte MIME validation (415), `image/jpg` alias, API key auth, token usage fields in response, partial verification flag, two-panel token summation, two-panel readable merge, empty-string and whitespace-only mandatory field bypass, receipt fields (label_ref format, sha256 value, back=None), schema_violations count, R-META-02 ABV cross-validation (mismatch, match, tolerance, not_found skip, unparseable text), `duration_ms` present and non-null in response, `GET /version` returns 200 with commit/environment/branch fields, Mode A application checker (`tests/test_application_checker.py`, R-APP-01–R-APP-05), Mode A API integration (`test_mode_a_brand_mismatch`, `test_mode_b_no_application_regression`), `test_get_applications_returns_catalog`

### slowapi test interference

`slowapi` uses an in-memory `MemoryStorage` instance that is a **module-level singleton** — the same object lives for the entire pytest process. This causes silent cross-test contamination: each call to `POST /v1/check` increments the counter for the `"testclient"` key (the fixed remote address Starlette's `TestClient` presents). Once the configured per-minute limit is exceeded within the rolling window, every subsequent test that hits the endpoint gets HTTP 429 instead of the expected response — producing `KeyError` or status assertion failures with no obvious connection to rate limiting.

**Fix in place**: the `client` fixture calls `limiter._storage.reset()` before each test, clearing all counters. This is sufficient because `TestClient` calls are synchronous and instantaneous (no real time passes between tests).

**What else can trigger this:**

- **Adding new tests that call `/v1/check`**: each new test adds to the count within the minute window. As long as `client` is used as a fixture (not constructed inline), the reset runs automatically and each test starts clean.
- **Tests that construct `TestClient(app)` directly** (bypassing the `client` fixture): the storage is not reset. If such a test calls `/v1/check` more times than `RATE_LIMIT_PER_MIN` allows without resetting, subsequent tests will see 429. Always use the `client` fixture.
- **`pytest-xdist` parallel execution**: workers share the same Python process memory — if ever adopted, the storage would need to be worker-local or the limiter disabled in tests via `RATELIMIT_ENABLED=0` env var (checked at import time, so must be set before `backend.app.main` is imported).
- **`limiter._storage` is a private attribute**: if slowapi changes its internal API, the reset call will break with an `AttributeError`. The public alternative is to set `RATELIMIT_ENABLED=0` as an environment variable before importing the app — this disables the limiter entirely for the test process, which is safe since rate limiting is an infrastructure concern, not business logic.

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

Implemented: EXIF rotation correction via `ImageOps.exif_transpose()` — critical for phone photos where orientation is stored in metadata rather than pixel data (root cause of failures on Glenfiddich, Ron Ron, Mike's Harder).

Not implemented: resolution normalization, contrast enhancement for low-quality scans. See the Upload validation section above for the minimum-file-size / Pillow production upgrade path.

### Frontend (ADR-005) — ⚠ Partial
**ADR reference:** ADR-005

A React + Vite + Tailwind v4 UI is built (`frontend/`) and served from the FastAPI backend via `StaticFiles` at `/`. Drag-and-drop and click-to-pick upload are implemented for front and back panels. Structured compliance results (verdict, issues table, receipt metadata) are displayed. Additional UI features: `duration_ms` shown in metadata grid (extraction latency in seconds), version commit and environment displayed in header (fetched from `GET /version` on mount), "New check" button clears panels and result without clearing the API key — UploadZone components re-mount via `uploadKey` React state increment; Mode A COLA stub toggle: collapsible "Compare against COLA application stub" section with dropdown; catalog fetched from `GET /v1/applications` on mount; selected stub submitted as `application=` on `POST /v1/check`; R-APP-* issues highlighted blue in result table; `application match` mode badge shown in verdict header when Mode A is active; toggle and stub selection preserved across "New check".

Not built: the base64 JSON endpoint specified in ADR-005 — the UI uses multipart `POST /v1/check` directly. The mobile-optimized layout is also deferred (desktop-first).

### Batch processing (ADR-007 / ADR-013)
**ADR reference:** ADR-007 (production design, not built), ADR-013 (UI PoC, accepted but not yet built)

ADR-007 documents a server-side batch endpoint (`POST /v1/labels/check` with a `labels` array, async fan-out). Not implemented. ADR-013 supersedes it for the prototype scope: a batch UI tab (not yet built) that will submit up to 10 products sequentially via the existing `POST /v1/check` endpoint, with filename-based auto-pairing, live results table, and CSV export. No backend changes required.

### Schema version gate (ADR-011)
**ADR reference:** ADR-011 §Schema evolution

`ExtractionResult.from_dict` accepts any `schema_version` value without validation. A production implementation should reject or flag results with an unexpected schema version to catch model prompt / schema drift.

### Human review queue for NONCOMPLIANT and UNVERIFIABLE verdicts

A production deployment should route NONCOMPLIANT and UNVERIFIABLE verdicts to a human review queue rather than treating them as final. Two known failure modes make this mandatory:

- **R-GW-03 false positives from OCR**: The colon at the end of `GOVERNMENT WARNING:` is occasionally misread or missed by the model. The normalization in `_normalize_gws_header()` corrects a space-before-colon artifact, but other OCR errors on the colon (missing entirely, replaced with period, etc.) would produce a NONCOMPLIANT verdict on a physically compliant label. Physical inspection is the only resolution path.
- **Model hallucination on rotated images**: On a 90°-rotated GWS, the model may hallucinate plausible-sounding but incorrect body text (observed on Glenlivet: `"Must be 21+ to purchase"`). This produces NONCOMPLIANT or UNVERIFIABLE depending on confidence.

The `schema_violations` count in the API response provides an additional triage signal: any verdict with `schema_violations > 0` is lower confidence than one with zero violations.

### GWS normalization complexity risk

The `_normalize_gws_body()` function applies seven normalizations (see ADR-011 §GWS Normalization Policy). Each is justified by a specific observed OCR artifact, and each is applied symmetrically to both extracted and canonical text. The risk: if enough normalizations accumulate, a substantively non-compliant body could be accepted because multiple independent normalizations collectively bridge the gap. Monitor: each new normalization added to the function must include a proof (and test) that the canonical text is unchanged by it.

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
- Production deployment hardening (request signing, structured logging, monitoring, `X-Forwarded-For` IP extraction for rate limiting behind proxy)
