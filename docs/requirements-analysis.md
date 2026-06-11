# Requirements Analysis

> **Historical document.** This is the original stakeholder spec written at project start. Many functional requirements here (Mode A verify-harness, React UI, batch upload, 5 s SLA, HEIC conversion, receipt object in API response) were deliberately deferred. For what is actually built, see [`IMPLEMENTATION_STATUS.md`](../IMPLEMENTATION_STATUS.md). When this doc conflicts with `IMPLEMENTATION_STATUS.md` or the code, those win.

**Project:** AI-Powered Alcohol Label Verification Prototype
**Date:** 2026-06-09
**Sources:** TTB.gov, 27 CFR Parts 4, 5, 7, 16 (eCFR), stakeholder interviews

---

## 1. Stakeholder-Derived Requirements

### Hard constraints (non-negotiable)

| # | Requirement | Source | Notes |
|---|---|---|---|
| H1 | End-to-end response time < 5 seconds, ≥95th percentile | Sarah Chen | Previous scanning vendor failed at 30–40s; agents abandoned it. Target is a statistical SLA, not a hard per-request timeout. |
| H2 | UI must be operable by non-technical users | Sarah Chen | Benchmark: 73-year-old who learned video calling recently; half the team is over 50 |
| H3 | Government Warning Statement checked verbatim | Jenny Park | Word-for-word; "GOVERNMENT WARNING:" must be all-caps bold; non-bold remainder |

### Soft requirements (important, design for them)

| # | Requirement | Source | Notes |
|---|---|---|---|
| S1 | Batch upload support | Sarah Chen / Janet (Seattle) | "Would be huge." 200–300 labels at once. API-first design handles it; UI v1 exposes single-label only |
| S2 | Handle imperfect label images | Jenny Park | Angles, glare, bad lighting. See image preprocessing (ADR-008) |
| S3 | Near-miss matching for non-critical fields | Dave Morrison | "STONE'S THROW" vs "Stone's Throw" — same thing. Case-insensitive matching for brand name and producer name; exact match only for warning statement |
| S4 | No integration with COLA system | Marcus Williams | Standalone proof-of-concept only |
| S5 | No persistent storage of sensitive data | Marcus Williams | Images and extracted data cleared after response; no database in v1 |

---

## 2. TTB Compliance Rules (authoritative — 27 CFR)

### 2.1 Distilled Spirits (27 CFR Part 5)

All of the following are mandatory. Brand name, alcohol content, and class/type designation must appear in the **same field of vision** — a single side of the container (≤40% of circumference for cylinders) where all three can be viewed simultaneously without rotating the container.

| Field | Regulation | Rule |
|---|---|---|
| Brand name | 27 CFR 5.32(a)(1) | Must be present; primary display panel |
| Class/type designation | 27 CFR 5.32(a)(2) | Must accurately identify the spirit (e.g., "Kentucky Straight Bourbon Whiskey") |
| Alcohol content | 27 CFR 5.32(a)(3) | % Alc/Vol required; proof optional but if stated must equal 2× ABV |
| Net contents | 27 CFR 5.32(a)(4) | In metric units (e.g., "750 mL") |
| Name and address of bottler/importer | 27 CFR 5.32(a)(5) | Full name and US address |
| Country of origin | 27 CFR 5.32(a)(6) | Required if imported |
| Government Warning Statement | 27 CFR Part 16 | See §2.4 below |

### 2.2 Wine (27 CFR Part 4)

Applies to wine ≥7% ABV. Key differences from spirits: vintage and appellation are optional but trigger additional rules when present; sulfite declaration required if applicable.

| Field | Regulation | Rule |
|---|---|---|
| Brand name | 27 CFR 4.32(a)(1) | Must be present; front label (PDP) |
| Class/type designation | 27 CFR 4.32(a)(2) | Must include "wine" or a wine-type word (e.g., "cider", "mead") |
| Alcohol content | 27 CFR 4.32(a)(3) | % Alc/Vol; tolerance ±1.5% for wines <14%, ±1.0% for wines ≥14% |
| Net contents | 27 CFR 4.32(a)(4) | Metric (e.g., "750 mL") |
| Name and address of bottler | 27 CFR 4.32(a)(5) | |
| Country of origin | 27 CFR 4.32(a)(6) | Required if imported |
| Appellation of origin | 27 CFR 4.32(a)(7) | Required if brand name includes a geographic name; triggers varietal/vintage rules |
| Vintage date | 27 CFR 4.32(a)(8) | Optional; if stated, ≥95% of grapes from that year |
| Sulfite declaration | 27 CFR 4.32(b) | Required if SO₂ ≥10 ppm: "Contains Sulfites" or "Contains [Specific Sulfite]" |
| Government Warning Statement | 27 CFR Part 16 | See §2.4 below |

### 2.3 Malt Beverages / Beer (27 CFR Part 7)

Note: Alcohol content is **not** universally mandatory for beer — it is only required when alcohol is derived from flavors or non-beverage ingredients.

| Field | Regulation | Rule |
|---|---|---|
| Brand name | 27 CFR 7.64 | Must be present |
| Class/type designation | 27 CFR 7.141 | Must accurately identify the malt beverage |
| Net contents | 27 CFR 7.70 | May be blown/embossed/molded into container |
| Name and address | 27 CFR 7.66–68 | May be blown/embossed/molded into container |
| Alcohol content | 27 CFR 7.63(a)(3) | Required only when alcohol is derived from flavors or added non-beverage ingredients |
| Allergen/additive disclosures | 27 CFR 7.63(b) | FD&C Yellow No. 5, cochineal extract, carmine, sulfites, aspartame — if present |
| Country of origin | 27 CFR 7.69 | Required if imported (per US CBP rules) |
| Government Warning Statement | 27 CFR Part 16 | See §2.4 below |

### 2.4 Government Health Warning Statement (27 CFR Part 16)

**Applies to all alcohol beverages ≥0.5% ABV sold or distributed in the United States.** Mandatory since November 18, 1989 under the Alcoholic Beverage Labeling Act of 1988.

**Exact required text (§16.21):**

> GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.

**Formatting requirements (§16.22):**
- "GOVERNMENT WARNING" — **ALL CAPS and BOLD** (exact, no exceptions)
- Remainder of statement — NOT bold (bold remainder is a violation)
- Must appear on a contrasting background
- Must be separate from all other label information
- Must not be compressed so as to impair legibility
- Minimum type size: 1mm for containers ≤237 mL; 2mm for 237 mL–3 L; 3mm for >3 L
- Maximum character density: 40 chars/inch at 1mm; 25 at 2mm; 12 at 3mm

**Civil penalty for violation: up to $10,000 per day per offense** (indexed to CPI; current amount at ttb.gov/laws-regulations-and-public-guidance/labeling-act-penalty).

**Common violations (from Jenny Park's interview and TTB enforcement):**
- "Government Warning:" in title case instead of all caps
- Bold applied to the full statement instead of only the first two words
- Insufficient contrast against background
- Font too small or text compressed
- Missing one of the two clauses
- Paraphrasing or rewording the required text

---

## 3. Functional Requirements

### FR-01: Image ingestion and preprocessing
- Accept on upload: JPEG, PNG, WebP, GIF, HEIC/HEIF, TIFF, PDF (first page)
- Auto-convert unsupported formats to JPEG on ingest (HEIC, TIFF, PDF)
- Resize to target (1200px max long edge, JPEG quality 85%) before sending to model
- **Backoff strategy:** if model returns a low-confidence or unreadable response, retry at a higher resolution (up to original, or 50% intermediate step); see ADR-008
- Do not persist images beyond the request lifecycle

### FR-02: Field extraction (Mode B — production)
- Call vision model with preprocessed label image
- Extract all mandatory TTB fields as structured JSON
- Include per-field confidence indicators (high / medium / low / not_found)
- Target latency: <4.5 seconds (model timeout); <5 seconds end-to-end

### FR-03: Compliance check
- Input: extracted fields (from FR-02) or claimed fields (Mode A)
- Check each field against the applicable TTB rules (by detected beverage type)
- Output: `compliant: true/false`, plus per-issue detail:
  - `field`: which field failed
  - `rule`: which regulation was violated (e.g., "27 CFR 16.22(a)(2)")
  - `found`: what was actually on the label
  - `expected`: what was required
  - `severity`: error | warning (errors = non-compliant, warnings = needs review)
- "Not just compliant/non-compliant": every failure must be actionable

### FR-04: Mode A — test/verify mode
- Accept form-submitted field values
- Skip vision model extraction
- Run same compliance check, return same response shape
- Clearly labeled "Developer / Test Mode" in UI

### FR-05: Batch endpoint
- API accepts array of label submissions
- Processes concurrently (up to `MAX_CONCURRENT_REQUESTS`, default 5)
- Single-label UI sends batch of one
- Batch UI deferred to v2

### FR-07: Evaluation receipt in API response

Every response from the label check endpoint (Modes A and B) must include a `receipt` object containing:
- `event_id` — UUID linking this response to the server-side audit log entry
- `image_id` — SHA-256 hex digest of the original image bytes as received by the server
- `received_at` — ISO 8601 UTC timestamp of when the request was received
- `model_used` — the model that actually produced the extraction result (may differ from the configured primary if fallback was triggered)
- `preprocessing_applied` — boolean; true if the image was resized or format-converted before being sent to the model
- `backoff_attempt` — integer; 0 for the normal path, 1+ if the image was retried at a higher resolution

This allows clients to retain a tamper-evident record of what was submitted and how it was processed, enabling investigation of disputed verdicts without requiring server log access.

**Web UI:** The receipt is included in the underlying response payload but displayed as a collapsed disclosure element below the compliance verdict ("Show evaluation receipt ▾"). It is not part of the primary compliance workflow but must not be hidden entirely.

**Cross-reference:** ADR-010 for audit log schema and the server-side record that `event_id` links to.

### FR-06: Result display
- Prominent pass/fail indicator (green/red, unambiguous)
- Extracted fields table with confidence indicators
- Per-issue list: field name, what was found, what was required
- Fields that passed shown alongside failures (not just failure list)
- Clear indication when a field was not found vs. found but incorrect

---

## 4. Non-Functional Requirements

| # | Requirement | Target |
|---|---|---|
| NFR-01 | End-to-end latency, single label Mode B | <5 seconds at 95th percentile |
| NFR-02 | Provider availability | App operational if any single provider is down (three-tier fallback, ADR-001) |
| NFR-03 | UI accessibility | Usable by non-technical users; clear labels, no jargon, unambiguous pass/fail |
| NFR-04 | Error handling | All error states shown with actionable message; no raw stack traces |
| NFR-05 | Cost control | Default model: Gemini Flash; max_tokens: 500; rate limit: 10 req/min/IP |
| NFR-06 | No persistent storage | Images and extracted data cleared after response |

---

## 5. Image Format Considerations

### Supported formats and token costs (per provider)

| Format | Claude API support | Notes |
|---|---|---|
| JPEG | ✅ | Most common for bottle photos; lossy — quality 85% is appropriate |
| PNG | ✅ | Lossless; good for flat/graphic labels; larger file size |
| WebP | ✅ | Modern, efficient; increasingly common |
| GIF | ✅ | 8-bit color; poor for photos; only first frame used |
| HEIC/HEIF | ❌ | iPhone default format; must convert to JPEG on ingest |
| TIFF | ❌ | Professional/scanning format; must convert to JPEG on ingest |
| PDF | ❌ (as image) | Some submissions may be PDF; extract first page as JPEG |

### Token cost reference (Claude Sonnet 4.6 — $3/M input tokens)

| Image dimensions | ~Tokens | ~Cost/image | ~Cost/1k images |
|---|---|---|---|
| 400×600 px (small label) | ~320 | ~$0.001 | ~$0.96 |
| 800×1200 px (target resize) | ~1280 | ~$0.004 | ~$3.84 |
| 1200×1600 px (max target) | ~1568 (capped) | ~$0.005 | ~$4.70 |
| Original photo (3000×4000) | ~1568 (capped at native res) | ~$0.005 | ~$4.70 |

Claude caps at ~1568 tokens regardless of image size above 1568px, so resizing to 1200px is sufficient.

### Gemini Flash tile cost (tile = 258 tokens, ~$0.004/M tokens)

| Image dimensions | Tiles | ~Tokens | ~Cost/image |
|---|---|---|---|
| ≤384×384 px | 1 (flat) | 258 | <$0.001 |
| 768×768 px | 1 tile | 258 | <$0.001 |
| 1200×800 px | 2×2 = 4 tiles | 1032 | ~$0.004 |

For Gemini, resizing to ≤768px max dimension fits in 1 tile at minimal cost.

### Target preprocessing (see ADR-008)

- **Normal path:** resize to 1200px max long edge, JPEG 85% → ~100–300KB, sufficient for all three providers
- **Backoff:** if model cannot read → retry at original dimensions (up to provider limits)

---

## 6. Out of Scope (v1)

> *As originally specified. Note: audit logging **was** built (see `IMPLEMENTATION_STATUS.md`); "Batch UI" and React UI were not. See `IMPLEMENTATION_STATUS.md` for the current scope.*

- Integration with TTB COLA system
- User authentication / agent accounts
- Audit logging or decision history
- Batch UI (API supports it; UI does not in v1)
- Label generation or correction suggestions
- Mobile-optimized layout (desktop-first; API is mobile-ready)
- State-level labeling requirements (prototype covers federal TTB only)
- Nutritional labeling (proposed TTB rulemaking, not yet mandatory)

---

## 7. Acceptance Criteria (MVP)

> *As originally specified. Criteria 1 (5 s SLA), 5 (Mode A), and 6 (HEIC conversion) were not met in the prototype — see `IMPLEMENTATION_STATUS.md`.*

The prototype is complete when:

1. A user can upload a label image and receive a compliant/non-compliant verdict in <5 seconds for ≥95% of requests
2. The Government Warning Statement is checked verbatim, including ALL CAPS and bold formatting of "GOVERNMENT WARNING"
3. All mandatory TTB fields are checked for the detected beverage type (spirits, wine, or beer)
4. Each compliance failure produces a specific, actionable issue description identifying the field, what was found, and what was required
5. Mode A (test harness) allows field values to be submitted without a model call and returns the same verdict format
6. HEIC, TIFF, and other non-native formats are automatically converted on ingest
7. The app is accessible at a public Railway URL
8. Image preprocessing backoff is implemented: if the model cannot read a resized image, it retries at higher resolution
9. The app handles errors gracefully — missing image, unreadable label, provider timeout — with a user-visible message
