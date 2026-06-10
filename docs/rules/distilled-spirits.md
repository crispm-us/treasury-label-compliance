# TTB Rules: Distilled Spirits Labels

**Applies to:** Distilled spirits (whiskey, bourbon, scotch, vodka, gin, rum, tequila, brandy, liqueur, etc.)
**Authority:** Federal Alcohol Administration Act (FAA Act), 27 U.S.C. 205(e); 27 CFR Part 5
**eCFR URL:** https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5
**TTB Checklist URL:** https://www.ttb.gov/regulated-commodities/beverage-alcohol/distilled-spirits/ds-labeling-home/ds-checklist
**TTB Labeling Home:** https://www.ttb.gov/regulated-commodities/beverage-alcohol/distilled-spirits/labeling
**Beverage Alcohol Manual (BAM):** https://www.ttb.gov/regulated-commodities/beverage-alcohol/distilled-spirits/beverage-alcohol-manual-spirits

---

## R-DS-01: Brand name (mandatory)

A brand name must appear on the label. If the product is not marketed under a brand name, the name of the bottler or importer serves as the brand name.

**Compliance check:** Field must be present and non-empty.

*Source: 27 CFR §5.32(a)(1)*

---

## R-DS-02: Class and type designation (mandatory)

The class and type designation must be stated on the label. The designation must:
- Correctly identify the distilled spirit according to the TTB standards of identity (27 CFR Part 5, Subpart C)
- Appear in the same field of vision as the brand name and alcohol content (see R-DS-05)

Examples of valid designations: "Whisky", "Bourbon Whisky", "Kentucky Straight Bourbon Whiskey", "Vodka", "Gin", "Rum", "Tequila", "Brandy", "Blended Whisky", "Liqueur", "Cordial"

**Compliance check:** Field must be present and non-empty. The prototype checks for presence; full standards-of-identity validation (e.g., "bourbon" requires specific production criteria) is documented but deferred to a later version.

*Source: 27 CFR §5.32(a)(2), §5.62–5.131 (standards of identity)*

---

## R-DS-03: Alcohol content (mandatory)

Alcohol content must be stated as a percentage of alcohol by volume (% Alc/Vol or % Alc. by Vol.). 

- The statement may additionally include proof (1 proof = 0.5% ABV), but if stated, proof must equal exactly 2× the ABV percentage.
- The word "proof" may substitute for the ABV statement only if the product's actual alcohol content equals the stated proof divided by 2, within tolerance.
- Standard tolerance: ±0.15% Alc/Vol from stated value (see 27 CFR §5.36(c) for full tolerances by product class).

**Compliance check:**
1. Field must be present
2. Format must match: a numeric percentage followed by "%" and "alc" or "alc/vol" or "alc. by vol." (case-insensitive)
3. If proof is also stated, verify proof = ABV × 2 (within ±0.3 proof)
4. Value must be within plausible range for distilled spirits (typically 20%–95% ABV)

*Source: 27 CFR §5.32(a)(3), §5.35, §5.36*

---

## R-DS-04: Net contents (mandatory)

Net contents must be stated in metric units. Standard sizes:
50 mL, 100 mL, 200 mL, 375 mL, 500 mL, 750 mL, 1 L, 1.75 L (these are the standard sizes; non-standard sizes are permitted but unusual).

**Compliance check:**
1. Field must be present
2. Must be expressed in mL or L (e.g., "750 mL", "1 L", "1.75 L")
3. Non-metric units (e.g., "fifth", "quart", "pint") without metric equivalent are a violation post-metrication rules

*Source: 27 CFR §5.32(a)(4), §5.38*

---

## R-DS-05: Same field of vision (mandatory layout rule)

The brand name, alcohol content, and class/type designation must all appear in the **same field of vision** — defined as a single side of the container from which all three can be viewed simultaneously without rotating the container. For cylindrical containers, a "side" = 40% of the circumference.

**Compliance check (visual, model-assisted):** This is a layout/placement rule, not just a presence rule. The model should be asked to identify whether these three elements appear on the same face of the label. If the model cannot determine this from the image (e.g., only one side is photographed), record as "cannot verify — single-side image" rather than a pass or fail.

*Source: 27 CFR §5.32(c)*

---

## R-DS-06: Name and address of bottler or importer (mandatory)

For domestically produced spirits: name and address of the bottler (or distiller if bottled at the distillery).
For imported spirits: name and address of the US importer.

Format: City and state minimum; street address not required but common.

**Compliance check:**
1. Field must be present
2. Must include at minimum a name and a US location (city + state abbreviation)
3. For imports: "Imported by [name], [city, state]" or equivalent

*Source: 27 CFR §5.32(a)(5), §5.37*

---

## R-DS-07: Country of origin (mandatory for imports)

If the spirits are imported (produced outside the United States), the country of origin must be stated.

**Compliance check:**
1. If the model detects an importer statement or non-US place names suggesting foreign origin, check for country of origin
2. If the product appears to be domestic, this field is not required
3. The prototype applies this check when class/type or other label text indicates imported origin

*Source: 27 CFR §5.32(a)(6)*

---

## R-DS-08: Government Warning Statement (mandatory)

See `government-warning-statement.md` for full rules (R-GW-01 through R-GW-08). All rules apply to distilled spirits.

*Source: 27 CFR Part 16; 27 CFR §5.7 (cross-reference)*

---

## R-DS-09: Prohibited practices (non-exhaustive)

The following are prohibited on distilled spirits labels and are checked if detected by the model:

- False or misleading statements about age, origin, identity, or quality
- Use of "pure" as a standalone claim without qualification
- Use of a geographic name (e.g., "Scotch", "Cognac", "Tennessee Whiskey") for a product that does not meet the applicable standard of identity
- Any statement implying government endorsement beyond what is required

**Compliance check:** The prototype flags obviously prohibited terms (e.g., "bourbon" for a product with <51% corn mash or aged in used barrels) only when the model extracts sufficient information to make the determination. Most prohibited practice checks are deferred.

*Source: 27 CFR §5.42, §5.43*

---

## R-DS-10: Language

All mandatory label information must appear in English. Foreign language translations may also appear but must not contradict the English.

*Source: 27 CFR §5.34*

---

## Fields Summary for Compliance Checker

| Rule | Field | Type | Mandatory? |
|---|---|---|---|
| R-DS-01 | brand_name | presence | Always |
| R-DS-02 | class_type | presence | Always |
| R-DS-03 | alcohol_content | presence + format + value range | Always |
| R-DS-04 | net_contents | presence + metric format | Always |
| R-DS-05 | same_field_of_vision | layout (visual) | Always |
| R-DS-06 | bottler_name_address | presence | Always |
| R-DS-07 | country_of_origin | presence | If imported |
| R-GW-* | government_warning | presence + verbatim text + formatting | Always |
