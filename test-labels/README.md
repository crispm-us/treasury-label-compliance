# Test Label Images

Example alcohol label images for exercising the prototype. Organised by beverage type so the compliance checker can be validated against each rule set.

## Directory layout

```
test-labels/
├── spirits/    — distilled spirits (27 CFR Part 5)
├── wine/       — wine and cider (27 CFR Part 4)
└── beer/       — malt beverages (27 CFR Part 7)
```

At least three images per category, covering both compliant labels and labels with known defects once the system is further along.

## How to populate

Run the download script from the repo root on a machine with unrestricted internet access (i.e. Zulu, not inside a sandboxed environment):

```bash
pip install requests pillow
python scripts/download-test-labels.py
```

The script queries:
- **Wikimedia Commons API** — for spirits, using category searches
- **Open Food Facts API** — for beer and wine (free product database with front-label photos)

Both sources are publicly accessible with no API key required. Images downloaded from Wikimedia Commons are licensed under Creative Commons or are in the public domain. Open Food Facts images are under the Open Database License (ODbL).

## Adding images manually

Drop any JPEG or PNG into the appropriate subdirectory. Preferred image properties:
- Label fills most of the frame (not a full-bottle environmental shot)
- Sufficient resolution to read fine print (~1 MP minimum)
- All mandatory TTB fields visible in at least one image of the set

Good manual sources:
- **TTB COLA Online** (real approved labels, public record): https://www.ttbonline.gov/colasonline/publicSearchColasBasic.do
- **TTB Beverage Alcohol Manual — Distilled Spirits** (contains sample label images): https://www.ttb.gov/system/files/images/pdfs/spirits_bam/complete-distilled-spirit-beverage-alcohol-manual.pdf
- **Wikimedia Commons** — search for specific brand names or "label" within alcohol-related categories

## What makes a useful test image

For the prototype to exercise the full compliance path, each image should include:
- Brand name (clearly legible)
- Class/type designation
- Alcohol content (% Alc/Vol)
- Net contents (metric)
- Bottler name and US address
- Government Warning Statement (the critical verbatim check)

An image lacking the Government Warning Statement is also useful for testing the failure path.

## Intentionally defective labels

Once the happy-path tests are passing, add at least one defective label per type to test failure detection:

| Defect | Expected failure | Rule |
|--------|-----------------|------|
| Missing Government Warning | error | R-GW-01 |
| "Government Warning:" in title case (not all caps) | error | R-GW-03 |
| Full warning in bold (should be first two words only) | error | R-GW-04 |
| ABV missing from spirits label | error | R-DS-03 |
| Proof stated but not equal to 2× ABV | error | R-DS-08 |
| Wine ABV outside tolerance band | error | R-WN-03 |
| Sulfite declaration missing (wine with SO₂ ≥10 ppm) | error | R-WN-09 |
| ABV present on traditional beer label | warning | R-MB-03 |
