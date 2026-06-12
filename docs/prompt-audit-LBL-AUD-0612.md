# Extraction Prompt Audit — LBL-AUD-0612

**Date:** 2026-06-12
**Auditors:** ChatGPT (GPT-4o), Gemini (2 passes), Cris Pedregal Martin
**Scope:** `backend/app/prompts/extraction.py` — `SYSTEM` and `USER_TEMPLATE` constants
**Status:** Analysis complete; implementation pending

---

## Background

After observing systematic R-APP-05 false positives (model reading "USA" from bottler address instead of appellation text) and R-APP-01 false positives (model reading entity name instead of brand name), a structured two-auditor prompt review was conducted. ChatGPT produced a 16-item consolidated audit (session LBL-AUD-0612). Gemini reviewed the original prompt independently (Pass 1) and then critiqued the ChatGPT recommendations (Pass 2). This document records the merged findings, dispositions, and implementation plan.

---

## Consolidated Issue List

Issues are ordered by implementation priority. Source column: **C** = ChatGPT, **G** = Gemini.

### P0 — Schema-breaking or highest-frequency extraction failure

| # | Issue | Source | Disposition |
|---|---|---|---|
| A | `"high"` confidence conflates "clearly visible" with "certainly absent" — splits behavior unpredictably between `{"value": null, "confidence": "high"}` and `{"value": null, "confidence": "not_found"}` | C, G | **Accept.** Remove the "certainly absent" clause from `"high"`. Reserve `"not_found"` strictly for missing fields. |
| B | No explicit rule that boolean-valued fields must use the wrapper object. Models return bare `true`/`false`/`null` for `gws_present`, `gws_header_bold`, `gws_body_bold` — this is a confirmed hard schema violation observed in testing (8 violations on one label). | C, G | **Accept.** Add a dedicated schema rule after the JSON template. Add a self-check instruction: "Before returning the final JSON, verify every entry under `fields` is a `{value, confidence}` object." |

### P1 — High-frequency extraction error; direct R-APP-* impact

| # | Issue | Source | Disposition |
|---|---|---|---|
| C | `brand_name` is not distinguished from producer/entity/winery name. Observed: "MESA VERDE WINERY" not "Mesa Verde Chardonnay", "HARBOR BAY" not "Harbor Bay Lager". | C | **Accept.** Add: brand_name = consumer-facing product brand most prominently presented to purchasers; do NOT use winery/brewery/distillery/importer names unless they are also clearly functioning as the displayed brand. Add note: entity-type suffixes (Winery, Brewing Co., Distillery, Inc.) are not part of the brand name unless they appear on the label as such. |
| D | `country_of_origin` is read from bottler address ("USA" from address line) not from the origin/appellation statement on the label face. Root cause of R-APP-05 false positives on all synthetic labels. | C, G | **Accept.** Add: extract the geographic origin statement presented as part of the product identity or origin declaration on the label face. Do NOT derive from bottler, producer, importer, or address text unless the label explicitly presents that text as an origin statement. Preserve text at whatever specificity appears (e.g., "American", "California", "Lawrenceburg, Kentucky"). |
| E | `country_of_origin` normalization: "Product of France" → "France"; "Imported from Mexico" → "Mexico". Without this, R-APP-05 mismatch fires when origin_as_stated = "France" and model extracts "Product of France". | C | **Accept.** Add as a field-specific rule: when the origin claim includes introductory phrases ("Product of", "Imported from", "Made in"), extract only the geographic designation. |
| F | `country_of_origin` and `appellation` are not differentiated — model conflates them or double-populates. | C, G | **Accept.** Add: `appellation` = formal appellation or geographic designation as part of product classification (wine AVAs primarily); do not populate from bottler addresses. Both fields may be populated simultaneously when both concepts are explicitly present. |
| G | `class_type` is underspecified — model may extract varietal, marketing descriptor, or legal class/type. | C, G | **Accept.** Add: extract the class/type designation exactly as printed (e.g., "Straight Bourbon Whiskey", "Cabernet Sauvignon"). Preserve capitalization and wording. Do not include marketing adjectives unless they form the legal class/type designation. Note: ChatGPT's examples included "Hard Cider" and "India Pale Ale" — acceptable for general guidance but TTB-specific examples (Straight Bourbon Whiskey, Blended Scotch Whisky) should be preferred. |

### P2 — Moderate inconsistency; no direct rule-engine crash today

| # | Issue | Source | Disposition |
|---|---|---|---|
| H | `gws_header` / `gws_body` delimiter undefined — some models include the colon in `gws_header`, others don't. | G | **Accept with caveat.** Add: `gws_header` = preamble header without trailing colon or separator punctuation; `gws_body` = warning text following the header, omit leading colon and whitespace separator. **Caveat:** existing normalization layer in `compliance_checker.py` (`_normalize_gws_header()`, normalization #3) handles the ` :` artifact. The prompt fix must be coordinated with the normalization layer — if the model no longer includes the colon, normalization #3 becomes a no-op but must not break canonical matching. Verify in re-test before committing. |
| I | `net_contents_metric` and `net_contents_us` have no normalization rule — model may return "750ml", "750 mL", "750 Milliliters". | G | **Accept with correction.** Normalize to TTB-standard notation with space and uppercase unit: "750 mL", "1.5 L", "12 fl oz". Gemini proposed lowercase "ml" — reject that; TTB uses "mL". |
| J | `gws_present: false` implies a compliance determination the model cannot support from a single image. | C, G | **Partial accept.** Add observational scoping: `true` = GWS text observed; `false` = all visible panel(s) inspected, no GWS text observed; `null` = image quality prevents determination. Do NOT rename to `gws_observed` — that is a schema change requiring API versioning. |
| K | `"not_found"` wording "It may be on another panel" is misleading when both panels are provided. | C | **Accept.** Replace with: "the field was not observed in the visible portions of the provided panel(s). If not all panels were submitted, the field may appear elsewhere on the container." |
| L | Verbatim contract (Issue 13) conflicts with stripping rule (Issue 16). | C, G | **Accept; resolve by explicit exception.** State the verbatim-preservation rule as the default, then list field-specific overrides: "Unless a field-specific rule below overrides this, string fields preserve exact wording, capitalization, punctuation, and spacing. Exceptions: country_of_origin strips introductory phrases (see rule); bottler_name strips role descriptors (see rule)." |
| M | `bottler_name` and `bottler_address` lack extraction boundaries — "Bottled by", "Brewed by" may end up inside the name; company name may bleed into address. | G | **Accept.** Add: bottler_name = legal entity name only, strip role descriptors ("Bottled by", "Produced by", "Imported by"); bottler_address = geographic location (street/city/state/zip), exclude company name and role descriptors. |

### P3 — Low frequency or already handled in code

| # | Issue | Source | Disposition |
|---|---|---|---|
| N | `abv_pct` and `abv_text` relationship implicit — should both be populated when ABV text is present. | C | **Accept.** One-line clarification. |
| O | GWS fields may be populated with unrelated text when model is uncertain what the GWS is. | C | **Accept.** Add: populate `gws_header` and `gws_body` only when the text is identified as belonging to the Government Warning Statement. |
| P | `readable` definition too subjective. | C | **Accept (low priority).** Replace "if you can interpret the image" with "if at least one field can be extracted with high or low confidence." |
| Q | `beverage_class` may be inferred from brand knowledge rather than label evidence. | C | **Accept.** Add: determine from explicit label evidence only; do not infer from brand recognition or packaging style. |
| R | `schema_version` could be mutated by model (e.g., incremented to "1.1"). | G | **Accept.** Add: schema_version must always be the literal string "1.0". |
| S | Bilingual GWS — schema has single `gws_header` field, cannot represent two-language headers. | G | **Partial accept (prompt only).** Prompt instruction: if multiple languages are present, extract the English Government Warning only. Schema fix (two-field) deferred. |
| T | JSON escape character vulnerabilities (labels with `"` characters). | G | **Defer.** `json.JSONDecodeError` is already caught and returns `ExtractionError`. Apostrophes don't need JSON escaping. True `"` characters on labels are extremely rare. No prompt change needed. |
| U | Floating-point truncation on `proof` and `abv_pct` (94 vs 94.0). | G | **Defer.** `float(fv.value)` conversion in the ABV checker handles this. Non-issue for current code. |
| V | Bold text criteria subjective across model families. | C, G | **Accept.** Replace with: "true only when text appears visually heavier than adjacent body text in the same section." |

---

## Rejected Recommendations

**Gemini critique of Recommendations 14/16 ("country_of_origin breaks international trade validation"):** Rejected. Gemini applied a customs/import-duty ontology. This system is TTB label text matching, not trade compliance. The `country_of_origin` field is compared against `origin_as_stated` in a COLA application stub, which may declare "California" or "Lawrenceburg, Kentucky". ChatGPT's source-attribution framing was correct.

**ChatGPT Recommendation 9 ("preserve role descriptor in bottler_name"):** Rejected per Gemini's critique. "Produce by XYZ" as the extracted `bottler_name` creates downstream matching variance. Strip all role descriptors.

**Rename `country_of_origin` → `origin_statement`:** Deferred, not rejected. Architecturally correct (documented in ADR-011 §Deferred rename). Breaking API change; no external consumers yet. Revisit before first production release.

**Rename `gws_present` → `gws_observed`:** Rejected for prompt implementation. Would require schema version bump and API change. Observational scoping added via wording only (Issue J above).

---

## Conflicts Resolved

**Verbatim vs. stripping:** Recommendation 13 (preserve exact wording) conflicts with Recommendation 16 (strip "Product of" prefix) and bottler role-descriptor stripping. Resolution: state verbatim preservation as the default rule, list explicit named exceptions inline.

**"MUST be null" misread:** Gemini flagged an apparent conflict between Issue 1 ("not_found value MUST be null") and Issue 2 ("never return bare null"). Not a real conflict — Issue 1 refers to the `value` key inside the wrapper object; Issue 2 refers to the field-level structure. The phrasing in the Cursor prompt should be written to make this unambiguous.

**gws_header colon:** Gemini Issue 3 proposes stripping the colon from `gws_header`. Existing normalization #3 in `compliance_checker.py` handles models that include a space before the colon. If the prompt is changed to always omit the colon, normalization #3 becomes a no-op but must not break canonical GWS header matching. Coordinate prompt change + normalization layer verification in re-test.

---

## Implementation Plan

### What changes

Prompt text only: `backend/app/prompts/extraction.py`. No changes to models, compliance checker, application checker, or fixtures at this stage.

### Scope for Cursor prompt

Implement P0 (A, B) and P1 (C–G) changes. Include P2 items H–M selectively — H (gws_header colon) is marked verify-in-retest; I (net_contents) is a clean addition; J–M are low-risk clarifications. P3 items N–S can be bundled in the same pass since they are one-liners.

### Review process

1. Write Cursor prompt (this session)
2. Cursor implements changes to `extraction.py` only
3. Cris PM reviews the diff directly — no external AI round-trip for the implementation review
4. Local re-test: run existing 105 tests (should be unaffected — no code change) + curls on Harbor Bay compliant and Mesa Verde R-APP-05 to check whether R-APP-05 false positive behavior improves
5. If re-test shows regression or new failures, roll back `extraction.py` to git HEAD
6. If re-test is clean, commit; optionally send revised prompt text (not code) to ChatGPT for a final spot-check on wording only
7. Label test case review is a separate work stream — proceed in parallel or after commit

### What is NOT in this change

- No changes to `compliance_checker.py`, `application_checker.py`, or `application.py`
- No fixture updates
- No schema version bump
- No field renames
- No new tests (existing 105 cover schema violation behavior; prompt-level changes are validated by re-test curls)
