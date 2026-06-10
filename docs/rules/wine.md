# TTB Rules: Wine Labels

**Applies to:** Wine containing ≥7% alcohol by volume (wines <7% ABV are regulated differently under the Internal Revenue Code)
**Authority:** Federal Alcohol Administration Act (FAA Act), 27 U.S.C. 205(e); 27 CFR Part 4
**eCFR URL:** https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-4
**TTB Wine Labeling Overview:** https://www.ttb.gov/regulated-commodities/beverage-alcohol/wine/7percentormore
**TTB Wine Labeling Checklist:** https://www.ttb.gov/regulated-commodities/beverage-alcohol/wine/labeling-wine/wine-labeling-checklist-of-mandatory-label-information
**Beverage Alcohol Manual (BAM) for Wine:** https://www.ttb.gov/regulated-commodities/beverage-alcohol/wine/beverage-alcohol-manual-wine

---

## R-WN-01: Brand name (mandatory)

A brand name must appear on the front label (Principal Display Panel). If no brand name is used, the bottler's name serves as the brand name.

**Compliance check:** Field must be present and non-empty on the front/principal label.

*Source: 27 CFR §4.32(a)(1)*

---

## R-WN-02: Class and type designation (mandatory)

The wine must be identified by a class/type designation that includes the word "wine" or a term that clearly indicates the product is wine (e.g., "cider", "perry", "mead", "sake" are acceptable). The designation must accurately describe the wine.

Examples of valid designations: "Table Wine", "Red Wine", "White Wine", "Rosé Wine", "Sparkling Wine", "Champagne" (only if from Champagne, France, or grandfathered US use), "Port" (only if from Portugal, or with geographic qualifier), "Sherry", "Riesling", "Chardonnay" (varietal, requires ≥75% of that grape), "Cabernet Sauvignon"

**Compliance check:** Field must be present. Must contain a recognizable wine-type term. Varietal label requirements (≥75% of named grape, appellation rules) are documented but deferred to a later version.

*Source: 27 CFR §4.32(a)(2), §4.21–4.23 (standards of identity)*

---

## R-WN-03: Alcohol content (mandatory with tolerances)

Alcohol content must be stated as a percentage of alcohol by volume.

**Tolerances (actual vs. stated ABV):**
- Wines <14% ABV: ±1.5 percentage points (e.g., a wine labeled "12% Alc/Vol" may actually be 10.5%–13.5%)
- Wines ≥14% ABV: ±1.0 percentage point
- Tax class boundaries (7%, 14%, 21%, 24%) may not be crossed by the tolerance — a wine labeled 14% must actually be ≥13% (cannot be <14% for a higher tax class label)

**Format requirements:** "X% Alc. by Vol.", "X% Alcohol by Volume", or equivalent. Numerical value required.

**Special cases:** Wine labeled as "table wine" or "light wine" may omit the ABV if it falls within defined ranges (7%–14%), but only in specific circumstances (see 27 CFR §4.36(b)). The prototype checks for presence; if absent, flag as "alcohol content not found — verify if exemption applies."

**Compliance check:**
1. Field must be present (with noted exemption caveat)
2. Numeric format required
3. Value must be within plausible wine range (0.5%–24% ABV)
4. If value can be compared to known/declared value (Mode A), apply tolerance check

*Source: 27 CFR §4.32(a)(3), §4.36*

---

## R-WN-04: Net contents (mandatory)

Must be stated in metric units. Standard sizes: 187 mL, 375 mL, 750 mL, 1 L, 1.5 L, 3 L, 6 L.

**Compliance check:**
1. Field must be present
2. Must use metric units (mL or L)

*Source: 27 CFR §4.32(a)(4), §4.37*

---

## R-WN-05: Name and address of bottler (mandatory)

Name and address of the bottler (or winery/importer for imports).

**Compliance check:**
1. Field must be present
2. Must include a name and US location (city + state)
3. For imports: name and address of US importer

*Source: 27 CFR §4.32(a)(5), §4.35*

---

## R-WN-06: Country of origin (mandatory for imports)

If the wine is imported, the country of origin must be stated on the label.

**Compliance check:** Apply when label indicates foreign origin (non-US producer address, foreign place names, foreign language on label, appellation outside the US).

*Source: 27 CFR §4.32(a)(6)*

---

## R-WN-07: Appellation of origin (conditional — mandatory if claimed)

If the label bears a geographic appellation (country, state, county, American Viticultural Area), it must comply with the relevant rules:
- At least 75% of the wine's volume must be derived from grapes grown in the appellation (85% for an AVA; 100% for a single vineyard)
- If an appellation is used, the vintage date rules are triggered (see R-WN-08)

**Compliance check:** Check for presence of geographic name on the label. If present, flag as "appellation claim detected — verify percentage requirements." Full percentage verification is out of scope for image-based checking (requires production records).

*Source: 27 CFR §4.25, §4.26*

---

## R-WN-08: Vintage date (conditional — mandatory if stated)

If a vintage year appears on the label:
- At least 95% of the wine's volume must be derived from grapes harvested in that year
- An appellation of origin must also appear on the label

**Compliance check:** If a four-digit year is detected on the label in the context of vintage, flag as "vintage claim detected." Verify that an appellation is also present. Year must be plausible (not in the future; not before ~1950 for commercial wine).

*Source: 27 CFR §4.27*

---

## R-WN-09: Sulfite declaration (conditional — mandatory if applicable)

If the wine contains sulfur dioxide (SO₂) or other sulfites at 10 parts per million or more, the label must state: "Contains Sulfites" or "Contains [specific sulfite name]."

This is extremely common — virtually all conventionally produced wine contains measurable sulfites from fermentation. Intentionally sulfite-free wines may state "No Added Sulfites" only if no sulfites were added during production.

**Compliance check:** If the model detects a "Contains Sulfites" statement, verify it is present and correctly worded. If not detected, flag as "sulfite declaration not found — verify SO₂ level." The prototype cannot determine actual SO₂ level from the label; flag the absence as a warning requiring manual verification, not a hard failure.

*Source: 27 CFR §4.32(b)(3); TTB Industry Circular 86-3*

---

## R-WN-10: Government Warning Statement (mandatory)

See `government-warning-statement.md` for full rules. All rules apply to wine ≥0.5% ABV.

*Source: 27 CFR Part 16; 27 CFR §4.7 (cross-reference)*

---

## R-WN-11: FD&C Yellow No. 5 / cochineal / carmine declaration (conditional)

If the wine contains FD&C Yellow No. 5 (tartrazine), cochineal extract, or carmine as a color additive, it must be declared on the label.

*Source: 27 CFR §4.32(b)(1)–(b)(2)*

---

## Fields Summary for Compliance Checker

| Rule | Field | Type | Mandatory? |
|---|---|---|---|
| R-WN-01 | brand_name | presence | Always |
| R-WN-02 | class_type | presence + wine-type term | Always |
| R-WN-03 | alcohol_content | presence + format + tolerance | Always (with exemption caveat) |
| R-WN-04 | net_contents | presence + metric format | Always |
| R-WN-05 | bottler_name_address | presence | Always |
| R-WN-06 | country_of_origin | presence | If imported |
| R-WN-07 | appellation | format check | If geographic name present |
| R-WN-08 | vintage_date | presence of appellation | If year present |
| R-WN-09 | sulfite_declaration | presence | If SO₂ ≥10 ppm (flag absence as warning) |
| R-WN-10 | government_warning | verbatim + formatting | Always |
| R-WN-11 | color_additive_declaration | presence | If applicable additive used |
