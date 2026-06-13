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
Yes. A React + Vite + Tailwind UI is built (`frontend/`) and served from the FastAPI backend at `/`. It supports drag-and-drop and click-to-pick upload for front and back panels, and displays structured compliance results. See [ADR-005](adr/005-frontend-framework.md) and [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md).

**Which document should I trust if docs disagree?**
**Code → `IMPLEMENTATION_STATUS.md` → `README.md` → ADRs → `requirements-analysis.md`**. See [docs/README.md](README.md).

---

## 2. Compliance reviewers and label specialists

**What do the four verdicts mean?**

| Verdict | Meaning |
|---|---|
| `COMPLIANT` | All checked rules pass |
| `NONCOMPLIANT` | At least one definitive violation (error severity) |
| `UNVERIFIABLE` | No errors, but something could not be verified — displayed as **REVIEW** in the UI |
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

**What if my label has more than two panels — for example a cylindrical can where the Government Warning is on a dedicated face?**

The API accepts at most two images (`front` and `back`). For a three-panel container, two approaches work:

**Option A — stitch all three panels into `front` (simplest).** Combine all panels into a single image and submit as the `front` field. The model reads all visible text in one call. Drawbacks: each panel gets proportionally less resolution; the merge layer is bypassed.

**Option B — submit `front` + stitched `back` (recommended).** Submit the main front face as `front`, and stitch the remaining two panels side-by-side as `back`. The system runs both extractions in parallel and merges results field-by-field, taking the highest-confidence value per field. This preserves better per-panel resolution and uses the merge layer to resolve field conflicts. A utility script (`scripts/stitch-labels.py`) is included; for custom panel pairings, any image editor or Pillow one-liner works.

Both options are subject to the 10 MB per-file limit. The native fix — N-panel support where each panel is a separate named file — is documented in [ADR-012](adr/012-multi-panel-submission.md) and deferred.

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
Set `API_KEY`; send `X-API-Key` on `POST /v1/check`. Unset locally = no auth. `POST /v1/check` is also rate-limited per IP via `slowapi` (`RATE_LIMIT_PER_MIN`, default 60/minute); returns HTTP 429 on breach. `GET /healthz` and `GET /version` are unrestricted. These are prototype deployment artifacts, not production design recommendations — see Part II §5, *Which features are prototype submission artifacts and would be absent or different in production?*

**Tests without an API key?**
`uv run --with pytest pytest tests/ -v` — extraction is mocked throughout.

**Model configuration?**
`EXTRACTION_MODEL` (primary) and `EXTRACTION_FALLBACK_MODELS` (comma-separated, sequential on retryable errors). Benchmarks favor Gemini 2.5 Flash-Lite for speed; see [latency-benchmarks.md](latency-benchmarks.md).

**Batch endpoint or verify-without-model mode?**
Batch ([ADR-007](adr/007-batch-processing-design.md)) is not built. Mode A application-matching ([ADR-003](adr/003-dual-mode-input.md)) is partially implemented: optional `application` JSON on `POST /v1/check` (R-APP-01–R-APP-05), UI COLA stub toggle, and `GET /v1/applications` catalog — extraction still runs via the vision model; full COLA on-file integration is deferred. Tests mock extraction.

**What comes back besides the verdict?**
`request_id`, `duration_ms` (server-side extraction time in milliseconds), token usage, filenames, SHA-256 hashes, label references. Server-side JSONL audit logs in `audit_logs/` (gitignored, sensitive). See [ADR-010](adr/010-audit-logging.md).

**Why does R-APP-01 (brand name match) produce false positives on real and synthetic labels?**
R-APP-01 false positives are extraction errors — the vision model reads the wrong text element from the label — not a schema design problem. Two distinct failure modes are observed:

1. **Display headline ≠ declared brand**: The model reads the most prominent display headline on the label face instead of the brand name as declared in the COLA. Examples: "CANYON RIDGE" extracted when the declared brand is "Canyon Ridge Bourbon"; "MESA VERDE" or "MESA VERDE WINERY" extracted when the declared brand is "Mesa Verde Chardonnay". The display headline is a categorically different label element from the full declared brand string.

2. **Shortened brand form**: The model reads the shortened or prominent form of the brand rather than the full declared string. Example: "Tito's" extracted when the COLA-declared brand is "Tito's Handmade Vodka". The label displays "TITO'S" in large type and "Handmade Vodka" as a secondary descriptor — the model treats only the large text as the brand name.

A two-field schema approach (analogous to the `origin_as_stated` / `origin_iso2_country` design for R-APP-05) does not apply here. The origin split works because geography has a legitimate regulatory hierarchy — a label may correctly declare origin at any level (state, country). There is no analogous hierarchy for brand names: the COLA application has one `brand_name` field and the label must reproduce it exactly. The two cases are categorically different: origin is a multi-level representation problem; brand name is an extraction accuracy problem.

The production fixes are: (1) improve the extraction prompt to explicitly distinguish brand name from producer/entity name — the model should be told that `brand_name` is the registered product identifier, not the winery, distillery, or importer name; (2) optionally, a normalized substring heuristic as a stopgap — if the extracted brand is a case-normalized substring of the declared brand or vice versa, treat as tentative match — this would resolve the "Tito's" ≠ "Tito's Handmade Vodka" case but not the entity-name confusion. Neither fix is implemented in this prototype. R-APP-01 false-positive results should be treated as informational pending extraction prompt improvement.

**Why does R-APP-05 (origin match) flag labels that say "American" or show a state or city name?**
As of the current prototype, R-APP-05 compares the extracted origin text against the `origin_as_stated` field in the application stub. The geo-normalization service described below remains the production design for validating that `origin_as_stated` is consistent with `origin_iso2_country`. R-APP-05 does exact string comparison between the vision model's `country_of_origin` extraction and the declared stub value (typically `"United States"`). The model frequently extracts `"American"`, `"Kentucky"`, `"Lawrenceburg, KY"`, or a country abbreviation — all genuinely US origin — but none matches the declared string.

US origin determination is not a string-normalization problem solvable with a fixed enumeration. A correct resolver must handle 50 state names and abbreviations, Washington D.C., all US territories (Puerto Rico, Guam, U.S. Virgin Islands, Northern Mariana Islands, American Samoa), and variant spellings (`"USA"`, `"U.S.A."`, `"United States of America"`, unqualified `"American"`). It must also reject superficially similar strings such as `"South American"` or `"North American"` that are not US origin.

For wine, the declared `country_of_origin` in a COLA application may be a state, a county, or a federally recognized American Viticultural Area (AVA) — not just the country. An application may legitimately declare `"California"`, `"Napa Valley"`, or `"Paso Robles"` rather than `"United States"`. A production resolver must understand the TTB appellation hierarchy: AVA ⊂ county ⊂ state ⊂ US, and map any extracted text to the correct level for comparison. This is out of scope for a string-matching rule.

The production design should delegate to an external geo-normalization service rather than maintaining an in-house enumeration — the same argument that leads to delegating sales tax computation to a zipcode-aware service (Avalara, TaxJar, etc.) rather than encoding tax rules in application code. A single classification call at check time (extracted string → ISO 3166-1 country code) is the clean architecture; the R-APP-05 rule then compares codes, not strings.

Post-prompt LBL-AUD-0612 (2026-06-12): beer and spirits labels now extract origin from the class/type line on the label face rather than the bottler address; wine labels remain unfixed because class/type text lacks a reliable geographic anchor.

This is a documented prototype limitation. The current R-APP-05 false-positive rate on genuine US-origin labels is high; treat R-APP-05 `warning`-severity results as informational until normalization is addressed.

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
Yes for all tested configurations. Single-panel Flash-Lite ~2.5 s; two-panel parallel ~2.2 s (Flash-Lite), ~4.4 s (Haiku), ~4.8 s (GPT nano). The two-panel path runs both panel extractions concurrently via `ThreadPoolExecutor`. Full accounting: [latency-benchmarks.md](latency-benchmarks.md).

---

# Part II — Meta FAQs (evaluating this work)

*For interviewers, reviewers, and architects assessing the project as a deliverable. Assumes you have read Part I.*

---

## 5. Evaluating the project — scope, process, and architecture

**What was the original ask vs. what was delivered?**
[requirements-analysis.md](requirements-analysis.md) specified React UI, batch upload, Mode A verify harness, HEIC conversion, 5 s SLA, and image resize/backoff. Mode A application-matching is partially delivered (API + UI toggle; COLA on-file integration deferred). [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md) is the honest built-vs-deferred accounting. When they conflict, implementation status and code win.

**What is the core design insight worth explaining?**
Strict separation of AI extraction (Layer 1) from deterministic compliance checking (Layer 2). Compliance logic is auditable, version-controlled, and unit-testable independent of the model. Everything else — multi-provider fallback, audit logging, rule files as repo artifacts — supports that separation.

**Where is design thinking documented?**
[docs/adr/](adr/) — decisions with explicit trade-offs and alternatives rejected. Real-label testing findings, iteration notes, and smoke-test results are in [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md), [DEPLOYMENT_CHECKLIST.md §6](DEPLOYMENT_CHECKLIST.md), and Part II of this FAQ.

**How do I quickly assess architectural completeness?**
Read [docs/adr/README.md](adr/README.md) status table alongside [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md). Built: two-layer pipeline (009), extraction schema (011), FastAPI (004), Railway target (006), partial audit (010), partial preprocessing (008), partial UI — React+Vite+Tailwind (005), partial Mode A application-matching (003). Not built: batch (007). Mode A full COLA on-file integration remains deferred.

**Why keep `requirements-analysis.md` if much is deferred?**
Historical context for scope decisions and stakeholder constraints (no COLA integration, no persistent storage, verbatim GWS requirement). Not current behavior.

**What would production need beyond this prototype?**
Human review queue for NONCOMPLIANT/UNVERIFIABLE; schema version gate; Unicode normalization for GWS; calibrated R-GW-04 bold check; full image preprocessing; COLA integration; net-contents parsing; appellation verification; geo-normalization service for R-APP-05 origin matching (see Part I §4); deployment hardening. Listed in [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md).

**How was quality validated beyond unit tests?**
Synthetic labels with embedded defect markers; real bottle/can photographs; `scripts/smoke-test.sh`; `scripts/benchmark-latency.sh`. Real labels exposed rotation, multi-panel, and hallucination edge cases documented in [DEPLOYMENT_CHECKLIST.md §6](DEPLOYMENT_CHECKLIST.md).

**What known failure modes should an evaluator probe?**
GWS OCR false positives on punctuation (R-GW-03); hallucinated GWS body on rotated images (Glenlivet); ABV numeric hallucination vs correct text (Mike's Harder); three-face cans missing net contents when only two panels submitted (Henninger). These motivate human review, not algorithmic fixes alone.

**What artifacts demonstrate honest scoping?**
[IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md) (built/deferred/not started); ADR status icons in [docs/adr/README.md](adr/README.md); prototype notice in [README.md](../README.md); deferred rules (R-GW-04, R-MB-03) explained with *why*, not just *what*.

**Which features are prototype submission artifacts and would be absent or different in production?**

Three features exist because this is a public prototype deployment under evaluation, not production software. For the broader production gap list, see *What would production need beyond this prototype?* above.

**API key field in the UI.** The Railway endpoint is publicly reachable — anyone with the URL can call it. `API_KEY` / `X-API-Key` limits access to authorized users without requiring evaluators to use curl. The UI key-entry field is a usability accommodation for that handoff. In production, authentication is at the network or service layer (OAuth, mTLS, a reverse proxy's auth middleware) and never appears as a form field in the application UI.

**Per-IP rate limiting (slowapi, configurable via `RATE_LIMIT_PER_MIN`, default 60 req/min).** Each extraction call has real provider cost on a publicly reachable deployment. The rate limiter prevents accidental or intentional cost overruns from an unprotected public URL. In production, rate limiting is an API gateway or load-balancer concern, governed by authenticated client identity and service-level agreements — not an in-process per-IP counter.

**`AUDIT_ENABLED=false` on Railway.** Railway's filesystem is ephemeral: a redeploy wipes it. Leaving audit logging enabled against a local JSONL file would produce logs that silently disappear. The flag is set to `false` to avoid false confidence that a record is being retained. Production deployment ships logs to a structured sink (Cloud Logging, Datadog, etc.) rather than a local file — see [ADR-010](adr/010-audit-logging.md).

**What real-world engineering problems were encountered and fixed?**
Three specific incidents: (1) `API_KEY` shell environment bleed-through — setting `API_KEY` in `~/.zshrc` for local deployment convenience caused 25 test failures (all 401), because `TestClient` creates the app in-process and `API_KEY` was read from the live shell environment; fixed by monkeypatching `API_KEY` to `""` in the `client` fixture so tests are isolated from host environment regardless of what is set in the shell. (2) `slowapi` in-memory test contamination — adding rate limiting caused 7 test failures after the 20th `/v1/check` call in a pytest run; fixed by resetting `limiter._storage` between tests. (3) Railway deploy sequence — environment variables must be set in the service Variables tab (not Project Settings → Shared Variables) and applied before the first deployment. These are documented in [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md).

**What did real-label testing reveal that synthetic labels could not?**
Two findings that synthetics cannot expose. First, EXIF rotation: phone photos embed orientation in metadata rather than pixels; the model reads a sideways image as garbled text. Synthetic labels (generated by Pillow) are always upright. Discovered on Glenfiddich 12-year; fixed with Pillow `exif_transpose` applied server-side before model ingestion. Second, model hallucination on rotated images: on a poorly-oriented Glenlivet image the model produced plausible but fabricated GWS body text, yielding a false COMPLIANT verdict. This failure mode cannot be caught deterministically and is the primary reason human review is mandatory in production.

**Has the tool caught a genuine violation on a real commercial product?**

> **Real-label finding — a genuine violation, not a tool error.** Delirium Tremens (a commercially distributed Belgian import) returns NONCOMPLIANT on R-GW-02 because its Government Warning body reads "…OR TO OPERATE MACHINERY" where 27 CFR §16.21 mandates "…OR OPERATE MACHINERY." Physical inspection of the product confirmed the extra "TO" is printed on the label — the model read it correctly and the verbatim check flagged it correctly. This is a real federal labeling defect surfaced by the deterministic Layer 2, not an extraction artifact.

**What motivated the ABV cross-validation rule (R-META-02)?**
Mike's Harder Lemonade produced `abv_pct=5.0` at high confidence while correctly reading `abv_text` as `"8% ALC. BY VOL."` — a numeric hallucination the single-field confidence level would not catch. R-META-02 fires a warning when `abv_pct` and `abv_text` disagree by more than 0.2%. This illustrates the value of deterministic cross-checking in Layer 2: the model can be wrong at high confidence, and rules can catch it. The hallucination was internally self-consistent — the model also returned `proof=10.0`, which correctly equals 2 × 5.0, so the proof-consistency and ABV-range checks both passed; only cross-referencing `abv_pct` against the independently-read `abv_text` exposes the contradiction.

---

## 6. Test labels and evaluation (assessing the test strategy)

*Same corpus as Part I §3, but framed for evaluators judging coverage and rigor.*

**Does the test corpus demonstrate the architecture or production readiness?**
It demonstrates the architecture and rule coverage honestly. Synthetics prove deterministic checker paths; reals reveal model limitations. It is not a statistically validated production test suite.

**What defect coverage exists vs. gaps?**
Covered: R-GW-01, R-GW-03, R-WN-09 (synthetics). Not yet generated: R-GW-04 (full body bold), R-DS-03 ABV/proof defects, R-WN-03 tolerance band, R-MB-03 flavored-malt ABV. Matrix in [test-labels/README.md](../test-labels/README.md).

**How complete is rule coverage in the synthetic label corpus?**
The most important gap is that no synthetic label exercises R-GW-04 (GWS bold-type requirement) or the ABV range edge cases (R-DS-03, R-WN-03) at exactly the boundary. Real labels provide more realistic hallucination and confidence-variance data than synthetics for these rules.

**What did real-label testing reveal that synthetics did not?**
EXIF/rotation handling (Glenfiddich, Glenlivet); mixed-case GWS headers on otherwise compliant labels (Ron Ron); vertical GWS layout; flavored malt ABV cross-field mismatch (Mike's Harder); EU-market label behavior (Jack Daniel's EU). Documented with expected verdicts in [DEPLOYMENT_CHECKLIST.md §6](DEPLOYMENT_CHECKLIST.md).

**How complete is the real-label smoke matrix?**
All rows in [DEPLOYMENT_CHECKLIST.md §6](DEPLOYMENT_CHECKLIST.md) were confirmed against Gemini Flash Lite (2026-06-12) via `scripts/smoke-test.sh`, the web UI, or `test-labels/mode-a-smoke-batch.sh`. Domestic Jack Daniel's Old No. 7 remains in `smoke-test.sh` for no-GWS regression only — photos lack a visible GWS and are excluded from the §6 verdict matrix until a clean GWS shot is available.

**Why include TTB COLA research if images aren't public?**
Shows domain research: TTB submits one image per panel (aligns with two-panel API design); COLA images require industry login (explains why corpus uses BAM, Open Food Facts, and own photos). Documented in [ADR-012](adr/012-multi-panel-submission.md) and [test-labels/README.md](../test-labels/README.md).

**What scripts should an evaluator run?**
`uv run --with pytest pytest tests/ -v` (no keys); `bash scripts/smoke-test.sh` (needs running server + key); `./scripts/benchmark-latency.sh` (optional, needs keys).

---

## Structure summary

| Part | Sections | Audience |
|---|---|---|
| **I — Product** | 1 Everyone → 2 Compliance → 3 Test labels (usage) → 4 Technical (dev + architect) | Users of the prototype / eventual production |
| **II — Meta** | 5 Evaluating the project → 6 Test labels (assessment) | Interviewers and technical evaluators |

Overlap is intentional: test labels appear in I §3 (how to use) and II §6 (what they prove). Architecture appears in I §4 (how it works) and II §5 (why it matters for assessment). Evaluators read both; product readers can stop after Part I.
