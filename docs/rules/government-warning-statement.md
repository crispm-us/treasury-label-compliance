# TTB Rules: Government Health Warning Statement

**Applies to:** All alcohol beverages containing ≥0.5% alcohol by volume, sold or distributed in the United States.
**Authority:** Alcoholic Beverage Labeling Act of 1988 (ABLA), 27 U.S.C. 215–218; 27 CFR Part 16
**eCFR URL:** https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16
**TTB URL:** https://www.ttb.gov/regulated-commodities/beverage-alcohol/distilled-spirits/ds-labeling-home/ds-health-warning
**Effective:** November 18, 1989 (no exceptions for pre-existing labels after that date)

---

## R-GW-01: Statement is mandatory

The health warning statement MUST appear on every container of alcoholic beverages ≥0.5% ABV sold or distributed in the United States. There are no exemptions for domestic or imported products, regardless of beverage type.

**Exception:** Products bottled before November 18, 1989 (importer/bottler must provide proof on request).
**Exception:** Products produced/labeled exclusively for export outside the US (does not apply to Armed Forces shipments).

*Source: 27 CFR §16.20, §16.21*

---

## R-GW-02: Exact required text

The statement must read, verbatim:

> GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.

**Compliance check:** Compare extracted text against this exact string. Normalize whitespace only. Any deviation — including paraphrasing, reordering of clauses, or substitution of synonyms — is a violation.

*Source: 27 CFR §16.21*

---

## R-GW-03: "GOVERNMENT WARNING" must be all-caps and bold

The first two words, "GOVERNMENT WARNING", must appear in:
- ALL CAPITAL LETTERS
- **Bold type** (heavier weight than surrounding text)

The colon following "GOVERNMENT WARNING:" is part of the required text but not subject to the bold/caps rule independently — it follows naturally as part of the phrase.

**Compliance check:** The extracted text must begin with "GOVERNMENT WARNING:" in all caps. The visual presentation (bold) must also be detected — note that vision models can typically identify bold text from the visual weight of characters.

*Source: 27 CFR §16.22(a)(2)*

---

## R-GW-04: Remainder of statement must NOT be bold

The text following "GOVERNMENT WARNING:" — the two numbered clauses — must NOT appear in bold type. A label that bolds the entire statement (a common shortcut by producers) is non-compliant.

**Compliance check:** If the model detects that the body of the warning statement is also bold, flag as violation: "Warning statement body must not be bold; only 'GOVERNMENT WARNING' may be bold."

*Source: 27 CFR §16.22(a)(2) — "The remainder of the warning statement may not appear in bold type."*

---

## R-GW-05: Legibility on contrasting background

The statement must be readily legible under ordinary conditions and must appear on a contrasting background (e.g., black text on white background, or equivalent contrast).

**Compliance check (visual, model-assisted):** Flag if model reports the text is difficult to read due to low contrast, very small size, or compressed/crowded characters.

*Source: 27 CFR §16.22(a)(1)*

---

## R-GW-06: Minimum type size by container volume

| Container volume | Minimum type size |
|---|---|
| ≤237 mL (≤8 fl. oz.) | 1 millimeter |
| >237 mL and ≤3 liters (≤101 fl. oz.) | 2 millimeters |
| >3 liters (>101 fl. oz.) | 3 millimeters |

Maximum character density at each size: 40 chars/inch at 1mm; 25 chars/inch at 2mm; 12 chars/inch at 3mm.

**Compliance check:** This rule is difficult to verify precisely from a label photo without physical measurement. The checker should flag if the model reports the text appears unusually small or compressed. Physical size verification is out of scope for v1.

*Source: 27 CFR §16.22(b)*

---

## R-GW-07: Placement — separate from other information

The statement must appear "separate and apart from all other information" — it may be on the brand label, front label, back label, or side label, but must not be integrated into or visually merged with other label text.

**Compliance check:** Model should detect whether the warning statement appears as a distinct, visually separated block, or is embedded within other text.

*Source: 27 CFR §16.21*

---

## R-GW-08: Label must be permanently affixed

Labels bearing the warning statement must be affixed so they cannot be removed without water or solvent application (if the label is a separate affixed piece, not printed directly on the container).

**Note:** This requirement cannot be checked from a label image. Document as out-of-scope for image-based compliance checking.

*Source: 27 CFR §16.22(c)*

---

## Common Violations (from TTB enforcement and stakeholder interviews)

| Violation | Rule violated |
|---|---|
| "Government Warning:" (title case) | R-GW-03 |
| Full statement in bold | R-GW-04 |
| Entire statement in small italics, buried in other text | R-GW-05, R-GW-07 |
| Missing clause (1) or clause (2) | R-GW-02 |
| Paraphrased text (e.g., "may cause birth defects") | R-GW-02 |
| Statement on the bottom of the container | R-GW-07 (see note below) |

**Note on placement exclusions:** The following locations do NOT satisfy the label requirement even if the warning appears there: bottom surface of container; caps, corks, or closures (unless TTB-authorized); foil or heat shrink bottle capsules. *Source: Parallel to 27 CFR §7.61 construction; applies across beverage types.*
