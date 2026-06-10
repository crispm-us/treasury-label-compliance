# TTB Rules: Malt Beverage and Beer Labels

**Applies to:** Malt beverages (beer, ale, porter, stout, lager, hard cider when malt-based, etc.)
**Authority:** Federal Alcohol Administration Act (FAA Act), 27 U.S.C. 205(e); 27 CFR Part 7
**eCFR URL:** https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-7
**TTB Malt Beverage Mandatory Label Info:** https://www.ttb.gov/beer/labeling/malt-beverage-mandatory-label-information
**TTB Malt Beverage Checklist:** https://www.ttb.gov/beer/labeling/malt-beverage-labeling-checklist
**Beverage Alcohol Manual (BAM) for Beer:** https://www.ttb.gov/regulated-commodities/beverage-alcohol/beer/beverage-alcohol-manual-beer

---

## Important Distinction: Beer vs. Other Beverage Types

Malt beverages have fewer mandatory fields than distilled spirits or wine. Most notably, **alcohol content is not universally mandatory** for malt beverages. This is a critical difference that the compliance checker must handle correctly.

---

## R-MB-01: Brand name (mandatory)

A brand name must appear on the label.

**Compliance check:** Field must be present and non-empty.

*Source: 27 CFR §7.64*

---

## R-MB-02: Class and type designation (mandatory)

The product must be identified by a class and type designation that accurately describes the malt beverage. TTB has a list of established designations (see 27 CFR §7.141).

Examples of valid designations: "Beer", "Ale", "Porter", "Stout", "Lager", "Pilsner", "Malt Beverage", "Hard Cider" (if malt-based), "Flavored Malt Beverage"

**Compliance check:** Field must be present and must be a recognizable malt beverage type term.

*Source: 27 CFR §7.64, §7.141*

---

## R-MB-03: Alcohol content (conditional — NOT always mandatory)

**Alcohol content is required ONLY in the following circumstances:**

1. The product contains alcohol derived from **flavors or other added non-beverage ingredients (other than hops extract)** that contain alcohol — 27 CFR §7.63(a)(3)
2. The product is a "flavored malt beverage" (FMB) — these virtually always require ABV disclosure
3. Many states additionally require ABV disclosure on the label (state law, not TTB); the prototype covers federal law only

**When required:**
- Format: X.X% Alc/Vol or X.X% Alcohol by Volume
- Value must be within plausible range (0.5%–15% ABV for most malt beverages)

**When not required:**
- Traditional beer/ale/lager/stout made from malt, hops, water, yeast with no added flavor-derived alcohol
- Many major commercial beers do not display ABV on the federal label (though they commonly do voluntarily or per state law)

**Compliance check:**
1. Determine if ABV is present
2. If product is an FMB or the label mentions flavors/natural flavors as a significant component, flag absence as a warning
3. If ABV is present, validate format and plausible range

*Source: 27 CFR §7.63(a)(3)*

---

## R-MB-04: Net contents (mandatory)

Net contents must be stated. Uniquely for malt beverages, the net contents statement **may be blown, embossed, or molded into the container** rather than printed on a paper label.

Standard sizes: 12 fl. oz. (355 mL), 16 fl. oz. (473 mL), 22 fl. oz. (650 mL), 32 fl. oz. (946 mL), 40 fl. oz. (1.18 L), 64 fl. oz. (1.89 L). Metric equivalents are acceptable.

**Compliance check:**
1. Field must be present (may be embossed on container — note if not visible in label image)
2. Metric or customary units acceptable for malt beverages (unlike spirits/wine which require metric)
3. Value must be plausible (typically 8–64 fl. oz. / 237 mL–1.89 L for single containers)

*Source: 27 CFR §7.70*

---

## R-MB-05: Name and address of brewer or importer (mandatory)

Name and address of the brewer (domestic) or importer (imported). Like net contents, this **may be blown, embossed, or molded into the container**.

**Compliance check:**
1. Field must be present
2. Must include a name and US location (city + state)

*Source: 27 CFR §7.66–7.68*

---

## R-MB-06: Country of origin (mandatory for imports)

If imported, the country of origin must be stated per US Customs and Border Protection (CBP) rules, as referenced in 27 CFR §7.69.

**Compliance check:** Apply when label indicates foreign origin.

*Source: 27 CFR §7.69; 19 CFR (CBP country of origin rules)*

---

## R-MB-07: Mandatory additive/allergen declarations (conditional)

The following must be declared if present in the product:

| Ingredient | Declaration required |
|---|---|
| FD&C Yellow No. 5 (tartrazine) | "Contains FD&C Yellow No. 5" |
| Cochineal extract | "Contains cochineal extract" |
| Carmine | "Contains carmine" |
| Sulfites (≥10 ppm) | "Contains sulfites" or "Contains [specific sulfite]" |
| Aspartame | "PHENYLKETONURICS: CONTAINS PHENYLALANINE" |

**Compliance check:** If any of these terms are detected by the model on the label, verify correct wording. If label indicates use of flavors or added ingredients but no declaration is present, flag as "additive declaration may be required — verify ingredients."

*Source: 27 CFR §7.63(b)*

---

## R-MB-08: Government Warning Statement (mandatory)

See `government-warning-statement.md` for full rules. All rules apply to malt beverages ≥0.5% ABV.

*Source: 27 CFR Part 16; 27 CFR §7.5 (cross-reference)*

---

## R-MB-09: Prohibited practices (non-exhaustive)

- Use of "draft" on a packaged product that has not been produced by draft process
- Use of geographic designations (e.g., "Champagne-style") in ways that imply foreign origin
- Statements implying medicinal properties
- False statements about ingredients, process, or origin

*Source: 27 CFR §7.54, §7.55*

---

## Note on Hard Cider

Hard cider made from apple or pear juice with ≤0.64 g/100 mL carbonation and 0.5%–8.5% ABV is regulated under 27 CFR Part 4 (wine), not Part 7, unless it is malt-based. Apple/pear-based hard cider at ≥8.5% ABV is regulated as wine. The prototype uses the presence of "cider" in the class/type designation combined with ABV to route to the appropriate rule set.

*Source: 27 CFR §4.21(e)(3); TTB Industry Circular 2015-1*

---

## Fields Summary for Compliance Checker

| Rule | Field | Type | Mandatory? |
|---|---|---|---|
| R-MB-01 | brand_name | presence | Always |
| R-MB-02 | class_type | presence + malt-beverage term | Always |
| R-MB-03 | alcohol_content | presence + format | Only if FMB or flavor-derived alcohol; warn if absent otherwise |
| R-MB-04 | net_contents | presence | Always (may be on container, not label) |
| R-MB-05 | brewer_name_address | presence | Always |
| R-MB-06 | country_of_origin | presence | If imported |
| R-MB-07 | additive_declarations | presence + wording | If applicable ingredients present |
| R-MB-08 | government_warning | verbatim + formatting | Always |
