#!/usr/bin/env python3
"""
Search the TTB Public COLA Registry and download label images.

IMPORTANT — what is and isn't public:
  - The TTB Public COLA Registry search page and COLA detail pages are public.
    No account is required to search or view COLA metadata.
  - Label IMAGE download via viewColaLabel.do requires a TTB industry account
    (OAuth2 login). The public search returns metadata only, no image URLs.

What this script does instead:
  - Searches the COLA registry by product name wildcard to find recent
    APPROVED COLAs for a beverage category.
  - Prints the matching TTB IDs and brand names — useful for knowing what
    to photograph or look up in the TTB Beverage Alcohol Manual (BAM).
  - Optionally: for wine and beer, falls back to Open Food Facts which does
    provide publicly downloadable label images.

Better sources for actual label images:
  1. TTB Beverage Alcohol Manual (BAM) PDFs — contain real approved label
     examples, publicly accessible at ttb.gov.
       Spirits: https://www.ttb.gov/system/files/images/pdfs/spirits_bam/complete-distilled-spirit-beverage-alcohol-manual.pdf
       Wine:    https://www.ttb.gov/wine/bam
       Beer:    https://www.ttb.gov/beer/bam
  2. Photograph real bottles you have on hand (preferred for the prototype).
  3. Open Food Facts API — use scripts/download-test-labels.py.

Usage (from repo root):
    uv run --with requests --with beautifulsoup4 scripts/download-cola-labels.py
    uv run --with requests --with beautifulsoup4 scripts/download-cola-labels.py --wine-only
    uv run --with requests --with beautifulsoup4 scripts/download-cola-labels.py --list-only
"""

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit(
        "Missing dependencies — run:\n"
        "  uv run --with requests --with beautifulsoup4 scripts/download-cola-labels.py"
    )

# Form URLs confirmed by inspecting the live TTB COLA site (2026-06-10):
#   - Search form: GET  https://www.ttbonline.gov/colasonline/publicSearchColasBasic.do
#   - Form action: POST https://ttbonline.gov/colasonline/publicSearchColasBasicProcess.do?action=search
# Field names confirmed from DOM inspection:
#   searchCriteria.dateCompletedFrom      MM/DD/YYYY
#   searchCriteria.dateCompletedTo        MM/DD/YYYY
#   searchCriteria.productOrFancifulName  text, % wildcard allowed
#   searchCriteria.productNameSearchType  B=Brand, F=Fanciful, E=Either (default E)
#   searchCriteria.classTypeFrom          numeric code range start (leave blank for all)
#   searchCriteria.classTypeTo            numeric code range end   (leave blank for all)
#   searchCriteria.originCode             text (leave blank for all)
# Results page URL (for reference only — POST response, can't bookmark):
#   https://ttbonline.gov/colasonline/publicSearchColasBasicProcess.do?action=search
# Detail page URL pattern:
#   https://ttbonline.gov/colasonline/viewColaDetails.do?action=publicDisplaySearchBasic&ttbid={TTBID}
# Label image URL (requires TTB industry account login — NOT publicly accessible):
#   https://ttbonline.gov/colasonline/viewColaLabel.do?action=publicDisplaySearchBasic&ttbid={TTBID}

SEARCH_PAGE_URL = "https://www.ttbonline.gov/colasonline/publicSearchColasBasic.do"
SEARCH_POST_URL = "https://ttbonline.gov/colasonline/publicSearchColasBasicProcess.do"
DETAIL_URL_TMPL = "https://ttbonline.gov/colasonline/viewColaDetails.do?action=publicDisplaySearchBasic&ttbid={ttbid}"
BASE_URL        = "https://ttbonline.gov"

REPO_ROOT  = Path(__file__).resolve().parent.parent
LABELS_DIR = REPO_ROOT / "test-labels"

REQUEST_DELAY = 1.0

# Product name wildcards by beverage category.
# % is supported in the product name field.
SEARCHES: list[dict] = [
    {"category": "spirits", "name_patterns": ["%BOURBON%", "%WHISKEY%", "%WHISKY%", "%VODKA%", "%TEQUILA%"]},
    {"category": "wine",    "name_patterns": ["%CHARDONNAY%", "%CABERNET%", "%MERLOT%", "%PINOT%", "%SAUVIGNON%"]},
    {"category": "beer",    "name_patterns": ["%LAGER%", "%ALE%", "%STOUT%", "%IPA%", "%PORTER%"]},
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})


# -----------------------------------------------------------------------
# HTTP helpers
# -----------------------------------------------------------------------

def get_html(url: str) -> str | None:
    time.sleep(REQUEST_DELAY)
    try:
        resp = SESSION.get(url, timeout=20)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.RequestException as exc:
        print(f"    GET error: {exc}")
        return None


def post_html(url: str, data: dict) -> str | None:
    time.sleep(REQUEST_DELAY)
    try:
        resp = SESSION.post(url, data=data, params={"action": "search"}, timeout=20)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.RequestException as exc:
        print(f"    POST error: {exc}")
        return None


# -----------------------------------------------------------------------
# COLA search
# -----------------------------------------------------------------------

def search_cola(name_pattern: str, from_date: str, to_date: str) -> list[dict]:
    """
    POST to the COLA search form and return a list of result dicts.
    Each dict has: ttbid, brand_name, fanciful_name, class_type, origin, status (if visible).
    """
    payload = {
        "searchCriteria.dateCompletedFrom":     from_date,
        "searchCriteria.dateCompletedTo":       to_date,
        "searchCriteria.productOrFancifulName": name_pattern,
        "searchCriteria.productNameSearchType": "E",   # Either brand or fanciful
        "searchCriteria.classTypeFrom":         "",
        "searchCriteria.classTypeTo":           "",
        "searchCriteria.originCode":            "",
    }

    html = post_html(SEARCH_POST_URL, payload)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    # Count total results reported
    total_text = soup.get_text()
    total_match = re.search(r"Total Matching Records:\s*([\d,]+)", total_text)
    total = int(total_match.group(1).replace(",", "")) if total_match else 0

    # Parse the results table
    records: list[dict] = []
    table = soup.find("table", summary=re.compile(r"search result", re.I)) or \
            soup.find("table", attrs={"border": True})

    if not table:
        # Page might be an error or "no results"
        if "no records" in total_text.lower() or total == 0:
            return []
        print(f"    ! Could not parse results table (found text: {total_text[:200]!r})")
        return []

    rows = table.find_all("tr")
    for row in rows[1:]:   # skip header row
        cells = row.find_all("td")
        if len(cells) < 5:
            continue
        # Columns: TTB ID | Permit No. | Serial # | Completed Date | Fanciful Name | Brand Name | Origin | Origin Desc | Class/Type | Class/Type Desc
        a = cells[0].find("a")
        if not a:
            continue
        ttbid = a.get_text(strip=True)
        href  = a.get("href", "")
        if href and not href.startswith("http"):
            href = urljoin(BASE_URL, href)

        records.append({
            "ttbid":          ttbid,
            "detail_url":     href or DETAIL_URL_TMPL.format(ttbid=ttbid),
            "fanciful_name":  cells[4].get_text(strip=True) if len(cells) > 4 else "",
            "brand_name":     cells[5].get_text(strip=True) if len(cells) > 5 else "",
            "origin_desc":    cells[7].get_text(strip=True) if len(cells) > 7 else "",
            "class_type_desc":cells[9].get_text(strip=True) if len(cells) > 9 else "",
        })

    return records


# -----------------------------------------------------------------------
# Open Food Facts fallback (for wine and beer)
# -----------------------------------------------------------------------

OFF_SEARCH = "https://world.openfoodfacts.org/api/v2/search"

OFF_CATEGORIES: dict[str, list[str]] = {
    "wine":  ["wines", "red-wines", "white-wines", "rose-wines"],
    "beer":  ["beers", "lagers", "ales", "craft-beers"],
    # spirits not well-covered in OFF
}


def off_image_search(category: str, dest_dir: Path, needed: int) -> int:
    """Download label images from Open Food Facts. Returns number of images saved."""
    try:
        from PIL import Image
        import io
        pillow = True
    except ImportError:
        pillow = False

    saved = 0
    off_cats = OFF_CATEGORIES.get(category, [])

    for off_cat in off_cats:
        if saved >= needed:
            break
        time.sleep(REQUEST_DELAY)
        params = {
            "categories_tags_en": off_cat,
            "fields": "code,product_name,image_front_url,image_back_url",
            "page_size": 20,
            "sort_by": "popularity_key",
            "json": "1",
        }
        try:
            resp = SESSION.get(OFF_SEARCH, params=params, timeout=20)
            resp.raise_for_status()
            products = resp.json().get("products", [])
        except Exception as exc:
            print(f"    OFF error for {off_cat}: {exc}")
            continue

        for p in products:
            if saved >= needed:
                break
            name = (p.get("product_name") or p.get("code") or "").strip()
            name = re.sub(r"[^\w\s-]", "", name.lower())
            name = re.sub(r"[\s_-]+", "-", name)[:50].strip("-")
            if not name:
                continue

            front_url = p.get("image_front_url")
            back_url  = p.get("image_back_url")
            if not front_url:
                continue

            front_path = dest_dir / f"{name}-front.jpg"
            if front_path.exists():
                saved += 1
                continue

            try:
                time.sleep(REQUEST_DELAY)
                front_data = SESSION.get(front_url, timeout=20).content
                back_data  = SESSION.get(back_url,  timeout=20).content if back_url else None

                front_path.write_bytes(front_data)
                print(f"    ✓ {front_path.name} ({len(front_data)//1024} KB)")

                if back_data:
                    back_path = dest_dir / f"{name}-back.jpg"
                    back_path.write_bytes(back_data)
                    print(f"    ✓ {back_path.name} ({len(back_data)//1024} KB)")

                saved += 1
            except Exception as exc:
                print(f"    ✗ download error for {name}: {exc}")

    return saved


# -----------------------------------------------------------------------
# Per-category processing
# -----------------------------------------------------------------------

def process_category(
    category: str,
    name_patterns: list[str],
    from_date: str,
    to_date: str,
    max_results: int,
    list_only: bool,
    use_off_fallback: bool,
    dry_run: bool,
) -> int:
    dest_dir = LABELS_DIR / category
    dest_dir.mkdir(parents=True, exist_ok=True)

    existing = sum(1 for f in dest_dir.iterdir()
                   if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"})

    print(f"\n  Existing images: {existing}")

    # ---- COLA metadata search ----
    all_records: list[dict] = []
    for pattern in name_patterns:
        if len(all_records) >= max_results * 3:
            break
        print(f"  COLA search: name={pattern!r}")
        records = search_cola(pattern, from_date, to_date)
        print(f"    → {len(records)} result(s) on first page")
        all_records.extend(records)

    # Deduplicate by TTB ID
    seen: set[str] = set()
    unique = []
    for r in all_records:
        if r["ttbid"] not in seen:
            seen.add(r["ttbid"])
            unique.append(r)

    print(f"\n  COLA records found (metadata only — images require TTB login):")
    for r in unique[:max_results]:
        brand = r["brand_name"] or r["fanciful_name"] or "(unnamed)"
        print(f"    TTB ID {r['ttbid']}  |  {brand}  |  {r['class_type_desc']}  |  {r['origin_desc']}")
        print(f"    Detail: {r['detail_url']}")

    if list_only:
        return existing

    # ---- Image acquisition ----
    needed = max(0, 3 - existing)
    if needed == 0:
        print(f"\n  Already has {existing} image(s) — nothing to download")
        return existing

    print(f"\n  Need {needed} more image(s).")

    if use_off_fallback and category in OFF_CATEGORIES:
        print(f"  Falling back to Open Food Facts for images…")
        if not dry_run:
            new = off_image_search(category, dest_dir, needed)
            existing += new
            print(f"  → Downloaded {new} from Open Food Facts. Total: {existing}")
        else:
            print(f"  [dry-run] would attempt Open Food Facts for {needed} images")
    else:
        print(
            f"  ⚠️  No automatic image source available for {category}.\n"
            f"     Recommended sources (see test-labels/README.md):\n"
            f"     • TTB BAM PDF (extract label examples manually)\n"
            f"     • Photograph real bottles\n"
            f"     • Run scripts/download-test-labels.py (Wikimedia Commons)"
        )

    return existing


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--spirits-only", action="store_true")
    g.add_argument("--wine-only",    action="store_true")
    g.add_argument("--beer-only",    action="store_true")
    p.add_argument("--max",        type=int, default=10, metavar="N",
                   help="max COLA records to show per category (default: 10)")
    p.add_argument("--from-date",  default="01/01/2024",
                   help="search start MM/DD/YYYY (default: 01/01/2024)")
    p.add_argument("--to-date",    default="06/10/2026",
                   help="search end   MM/DD/YYYY (default: 06/10/2026)")
    p.add_argument("--list-only",  action="store_true",
                   help="only list COLA metadata, do not attempt to download images")
    p.add_argument("--no-off",     action="store_true",
                   help="skip Open Food Facts fallback for wine/beer images")
    p.add_argument("--dry-run",    action="store_true",
                   help="show what would be downloaded without saving")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    only_flags = [args.spirits_only, args.wine_only, args.beer_only]
    if any(only_flags):
        searches = [s for s, flag in zip(SEARCHES, only_flags) if flag]
    else:
        searches = SEARCHES

    print("TTB COLA Registry search — label IMAGES require TTB login, metadata is public.\n")
    if args.dry_run:
        print("DRY RUN — no files will be written.\n")

    results: dict[str, int] = {}
    for cfg in searches:
        print(f"=== {cfg['category'].upper()} ===")
        n = process_category(
            category       = cfg["category"],
            name_patterns  = cfg["name_patterns"],
            from_date      = args.from_date,
            to_date        = args.to_date,
            max_results    = args.max,
            list_only      = args.list_only,
            use_off_fallback = not args.no_off,
            dry_run        = args.dry_run,
        )
        results[cfg["category"]] = n

    print("\n=== SUMMARY ===")
    for cat, n in results.items():
        status = "✓" if n >= 3 else "✗ NEEDS MORE"
        print(f"  {status}  {cat}: {n} image(s)")

    if not all(n >= 3 for n in results.values()):
        print(
            "\nFor label images see test-labels/README.md — "
            "best sources are real bottle photos and the TTB BAM PDFs."
        )


if __name__ == "__main__":
    main()
