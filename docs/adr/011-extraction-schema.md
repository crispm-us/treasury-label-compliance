# ADR-011: Extraction JSON Schema

**Status:** Accepted
**Date:** 2026-06-09
**Deciders:** Cris Sfnert

---

## Context

ADR-009 sketched an extraction schema for Layer 1 (the AI vision model). After writing the Layer 2 compliance checker and all fixture JSON files, the schema is now concrete enough to formalise. This ADR is the normative definition; compliance_checker.py and all fixtures conform to it.

---

## Schema Version

`schema_version: "1.0"`

The `schema_version` field is required in every extraction result. The checker rejects documents whose version it does not recognise. Breaking changes (new mandatory fields, changed confidence semantics) require a version bump.

---

## Top-Level Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | yes | Must be `"1.0"` |
| `readable` | boolean | yes | `false` if the model could not interpret the image at all (too blurry, corrupt, fully obscured). When `false`, all other fields are undefined and the checker returns `ERROR` immediately. |
| `beverage_class` | string \| null | yes | One of `"beer"`, `"spirits"`, `"wine"`, or `null` if unrecognisable. Null triggers an `R-META-01` warning in the checker. |
| `panels_provided` | array[string] | yes | Which physical panels were submitted. Valid elements: `"front"`, `"back"`. Used for audit logging only — the checker does not change behaviour based on this value. |
| `extraction_model` | string | yes | Model identifier that produced this result (e.g., `"claude-haiku-4-5-20251001"`). Use `"fixture"` for test data. Stored in the audit log. |
| `fields` | object | yes | 18 field objects described below. |

---

## The `fields` Object

Every field is a `{"value": <typed_value_or_null>, "confidence": <enum>}` object. No field may be omitted; use `{"value": null, "confidence": "not_found"}` when the field is absent from the submitted image(s).

### Confidence Enum

Three values only:

| Value | Meaning |
|---|---|
| `"high"` | Model is certain about the extracted value (or certain the field is absent when `value` is null). |
| `"low"` | Model found something but is uncertain — text may be partially obscured, font is unusual, or the reading is ambiguous. |
| `"not_found"` | Field was not present in the submitted image. It may exist on a panel that was not submitted. `value` must be `null` when confidence is `"not_found"`. |

**`"not_found"` is not a quality judgement** — it means "not visible here, may be elsewhere." The checker treats `not_found` as a warning (field may exist on another panel), never as a confirmed violation.

### Field Reference

All 18 fields:

| Field | Value type | Notes |
|---|---|---|
| `brand_name` | string | |
| `class_type` | string | E.g., `"PALE ALE"`, `"BOURBON WHISKEY"`, `"CHARDONNAY"`. |
| `abv_pct` | number | Numeric ABV as a percentage, e.g., `5.2` for 5.2%. Do not include the `%` sign. |
| `abv_text` | string | Full text as printed, e.g., `"5.2% Alc/Vol"`. |
| `proof` | number | Numeric proof as printed, e.g., `94.0`. Null if not present (beer and wine typically omit this). |
| `net_contents_metric` | string | E.g., `"355 mL"`, `"750 mL"`. |
| `net_contents_us` | string | E.g., `"12 FL OZ"`. Null if not printed. |
| `bottler_name` | string | Legal name of the bottler/packer/importer. |
| `bottler_address` | string | Full address as printed. |
| `country_of_origin` | string | Required for imported products. |
| `gws_present` | boolean | `true` if any government warning statement is visible. |
| `gws_header` | string | Verbatim header text, e.g., `"GOVERNMENT WARNING:"`. |
| `gws_body` | string | Verbatim body text. |
| `gws_header_bold` | boolean | Whether the header appears bold. **See note on R-GW-04 below.** |
| `gws_body_bold` | boolean | Whether the body appears bold. **See note on R-GW-04 below.** |
| `sulfite_declaration` | string | The sulfite declaration text if present (wine). Null if absent. |
| `vintage` | string | Year printed on wine label. Null if absent or non-wine. |
| `appellation` | string | Appellation of origin if stated. Null if absent. |

---

## Verdict Enum

The checker (`check_compliance()`) returns one of four verdicts:

| Verdict | Condition |
|---|---|
| `ERROR` | `readable` is `false`. No rules evaluated. |
| `NONCOMPLIANT` | At least one issue has `severity == "error"`. |
| `UNVERIFIABLE` | No error-severity issues, but at least one warning. |
| `COMPLIANT` | Zero issues of any kind. |

Verdict precedence: `ERROR > NONCOMPLIANT > UNVERIFIABLE > COMPLIANT`.

---

## Issue Schema

Each item in the `issues` list has:

| Field | Type | Description |
|---|---|---|
| `rule_id` | string | E.g., `"R-GW-01"`, `"R-DS-03"`. Maps to a rule in `docs/rules/*.md`. |
| `severity` | `"error"` \| `"warning"` | Error drives NONCOMPLIANT; warning drives UNVERIFIABLE (unless an error is also present). |
| `field` | string | The extraction field that triggered the issue. |
| `found` | any | The value that was found (or null). |
| `expected` | string | Human-readable description of what was required. |

---

## Two-Panel Handling

When a label is submitted as two images (front and back), each is processed independently with the same extraction prompt. The results are merged field-by-field before being passed to the checker:

- For each field, take the value with the higher confidence (`"high"` > `"low"` > `"not_found"`).
- When both panels return the same confidence level for a field, prefer the non-null value.
- The `panel_hint` passed to the extraction call (e.g., `"front"` or `"back"`) is recorded in the audit log for traceability only. It does not affect extraction logic.

This strategy tolerates flipped images naturally: if the front and back labels are submitted in the wrong order, fields that happen to appear on the "wrong" panel are still extracted and merged correctly.

---

## Checker Behaviour for Deferred / Always-Warning Rules

Three rules have special handling in v1:

**R-GW-04 — GWS bold text requirement.** `gws_header_bold` and `gws_body_bold` are captured in the schema for forward compatibility. In v1 the checker ignores them. Vision-model bold detection is unreliable without a calibrated baseline. These fields will be activated once a reference set of known-bold and known-non-bold labels is assembled. See ADR-008.

**R-MB-03 — ABV on malt beverages.** ABV is not universally mandatory for malt beverages (required only above 0.5% in some jurisdictions). A missing `abv_pct` on a beer label fires an R-MB-03 warning, never an error. Upgrading to error-severity is deferred pending rules clarification.

**R-WN-09 — Sulfite declaration.** The TTB requires a sulfite declaration only when the product contains ≥10 ppm SO₂. Whether a product exceeds that threshold cannot be determined from the label image alone. A missing `sulfite_declaration` therefore always fires as an R-WN-09 warning (UNVERIFIABLE), never an error.

---

## Partial Extraction with High-Confidence Violation

When some fields have `confidence == "not_found"` (generating warnings) and at least one field has a definitive error-severity violation, the checker returns `NONCOMPLIANT` and includes both the error and the warnings in the `issues` list.

**This is a known limitation.** The NONCOMPLIANT verdict is technically correct — the violation exists. However, a submitter who fixes only the reported violation may not realise the label could not be fully verified, because mandatory fields on an unsubmitted panel are flagged only as warnings.

**Production design note (deferred):** the API response should include a top-level `partial_verification: true` flag whenever NONCOMPLIANT co-exists with one or more `not_found` warnings, so the UI can display: "Violation found AND some fields could not be verified — submit a complete label image to confirm all mandatory fields."

The documented fixture for this case is `tests/fixtures/extraction/spirits_partial_noncompliant.json`.

---

## Relationship to Other ADRs

- **ADR-009** — defines the two-layer architecture; this ADR formalises the contract between Layer 1 and Layer 2.
- **ADR-008** — covers image preprocessing and the retry/escalation strategy that feeds into Layer 1.
- **ADR-010** (if written) — covers the API contract; `partial_verification` flag design belongs there.

This ADR supersedes the sketch in ADR-009 §"Layer 1: Extraction schema."
