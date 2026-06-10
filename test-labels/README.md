# Test Label Images

Example alcohol label images for exercising the prototype. Organised by beverage type so the compliance checker can be validated against each rule set.

## Directory layout

```
test-labels/
├── spirits/    — distilled spirits (27 CFR Part 5)
├── wine/       — wine and cider (27 CFR Part 4)
└── beer/       — malt beverages (27 CFR Part 7)
```

At least three products per category. Each product must have exactly **two source files** (`{name}-front.jpg` and `{name}-back.jpg`) **or** a single pre-stitched file (`{name}-combined.jpg`). For products with only a combined file, no separate front/back are required.

Run `scripts/stitch-labels.py` after adding any front+back pair to generate the combined image automatically.

The test corpus covers both compliant labels and intentionally defective labels (see Intentionally defective labels section below). Compliant examples are real bottle photographs; defective examples are synthesised.

## How to populate

All scripts must run on a machine with unrestricted internet access (Zulu, not in a sandboxed environment).

### Note on TTB COLA Online

**Label images are not publicly accessible.** The TTB COLA Public Registry exposes metadata only (brand name, class/type, status). The image viewer (`viewColaLabel.do`) requires a TTB industry account. Run `scripts/download-cola-labels.py --list-only` to search COLA metadata and find products worth photographing or looking up in the BAM.

### Option A — TTB Beverage Alcohol Manual (BAM) PDFs

The BAM PDFs contain real approved label examples with all mandatory TTB fields visible. Best free source of realistic compliant labels — extract label images manually:

- **Spirits**: https://www.ttb.gov/system/files/images/pdfs/spirits_bam/complete-distilled-spirit-beverage-alcohol-manual.pdf
- **Wine**: https://www.ttb.gov/wine/bam
- **Beer**: https://www.ttb.gov/beer/bam

### Option B — Open Food Facts / Wikimedia Commons

Automated download via API; good for wine and beer, weak for spirits:

```bash
uv run --with requests --with pillow scripts/download-test-labels.py
```

Sources:
- **Wikimedia Commons API** — for spirits, using category searches (CC / public domain)
- **Open Food Facts API** — for beer and wine (ODbL licence)

## Adding images manually

Drop any JPEG or PNG into the appropriate subdirectory. Preferred image properties:
- Label fills most of the frame (not a full-bottle environmental shot)
- Sufficient resolution to read fine print (~1 MP minimum)
- All mandatory TTB fields visible in at least one image of the set

Good manual sources:
- **TTB Beverage Alcohol Manual** (contains real approved label examples): https://www.ttb.gov/wine/bam and https://www.ttb.gov/beer/bam
- **TTB COLA Online metadata search** (find product names to photograph): https://www.ttbonline.gov/colasonline/publicSearchColasBasic.do — label images require TTB account login
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
