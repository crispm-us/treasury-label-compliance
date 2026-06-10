#!/usr/bin/env python3
"""
Download example alcohol label images into test-labels/.

Usage (from repo root):
    uv run --with requests --with pillow scripts/download-test-labels.py

Behaviour:
  - Beer and wine are sourced from Open Food Facts via category search (no
    barcodes required). Products with both front and back images are preferred.
  - Spirits are sourced from Wikimedia Commons category search.
  - When Pillow is available and both front+back images exist, they are
    stitched side-by-side into a single *-combined.jpg. The separate
    *-front.jpg and *-back.jpg are also kept alongside.
  - Idempotent: skips files that already exist on disk.
  - Exits non-zero if any category is below MIN_PRODUCTS_PER_CATEGORY.

Sources:
  - Open Food Facts  https://world.openfoodfacts.org  (ODbL licence)
  - Wikimedia Commons  https://commons.wikimedia.org  (CC / public domain)
"""

import io
import sys
import time
import re
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit(
        "Missing dependency — run:\n"
        "  uv run --with requests --with pillow scripts/download-test-labels.py"
    )

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("Note: Pillow not available — front/back saved separately, not stitched.\n")

REPO_ROOT  = Path(__file__).resolve().parent.parent
LABELS_DIR = REPO_ROOT / "test-labels"

MIN_PRODUCTS_PER_CATEGORY = 3
BASE_DELAY   = 0.8   # seconds between requests
RETRY_DELAY  = 30    # seconds to wait on 429

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
OFF_SEARCH  = "https://world.openfoodfacts.org/api/v2/search"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "treasury-label-compliance-test/1.0 "
        "(https://github.com/crispm-us/treasury-label-compliance)"
    )
})


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def get_with_retry(url: str, params: dict | None = None, retries: int = 2) -> requests.Response | None:
    """GET url, retrying once on 429 and returning None on persistent failure."""
    for attempt in range(retries + 1):
        try:
            resp = SESSION.get(url, params=params, timeout=20)
            if resp.status_code == 429:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"    rate limited — waiting {wait}s before retry…")
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as exc:
            if attempt < retries:
                time.sleep(BASE_DELAY * 2)
            else:
                print(f"    request error: {exc}")
    return None


def download_bytes(url: str) -> bytes | None:
    resp = get_with_retry(url)
    return resp.content if resp else None


def save_file(data: bytes, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f"    ✓ {dest.name} ({len(data) // 1024} KB)")


def slugify(text: str) -> str:
    """Convert a product name to a safe filename stem."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:60].strip("-")


def is_image_filename(name: str) -> bool:
    return name.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))


# ---------------------------------------------------------------------------
# Image stitch helper
# ---------------------------------------------------------------------------

def stitch_side_by_side(front_data: bytes, back_data: bytes, dest: Path) -> bool:
    if not PILLOW_AVAILABLE:
        return False
    try:
        front  = Image.open(io.BytesIO(front_data)).convert("RGB")
        back   = Image.open(io.BytesIO(back_data)).convert("RGB")
        target = min(max(front.height, back.height), 1600)

        def fit(img: Image.Image, h: int) -> Image.Image:
            return img.resize((int(img.width * h / img.height), h), Image.LANCZOS)

        front  = fit(front, target)
        back   = fit(back,  target)
        gap    = 24
        canvas = Image.new("RGB", (front.width + gap + back.width, target), (180, 180, 180))
        canvas.paste(front, (0, 0))
        canvas.paste(back,  (front.width + gap, 0))

        buf = io.BytesIO()
        canvas.save(buf, "JPEG", quality=85)
        save_file(buf.getvalue(), dest)
        return True
    except Exception as exc:
        print(f"    stitch error: {exc}")
        return False


# ---------------------------------------------------------------------------
# Open Food Facts — category search (no barcodes needed)
# ---------------------------------------------------------------------------

def off_search_category(
    category_tag: str,
    max_results: int = 40,
    country: str = "united-states",
) -> list[dict]:
    """
    Return OFF products in category_tag that have at least a front image,
    sorted by popularity (most-photographed first).
    Filters to the specified country to favour US products with English labels.
    """
    params = {
        "categories_tags_en": category_tag,
        "countries_tags_en":  country,
        "fields": "code,product_name,image_front_url,image_back_url",
        "page_size": max_results,
        "sort_by": "popularity_key",
        "json": "1",
    }
    time.sleep(BASE_DELAY)
    resp = get_with_retry(OFF_SEARCH, params=params)
    if not resp:
        # Retry without country filter
        params.pop("countries_tags_en")
        time.sleep(BASE_DELAY * 2)
        resp = get_with_retry(OFF_SEARCH, params=params)
    if not resp:
        return []
    products = resp.json().get("products", [])
    # Prefer products with both images, fall back to front-only
    both  = [p for p in products if p.get("image_front_url") and p.get("image_back_url")]
    front = [p for p in products if p.get("image_front_url") and not p.get("image_back_url")]
    return both + front


def download_off_product(product: dict, dest_dir: Path) -> bool:
    """
    Download front + back (if available) for one OFF product dict.
    Returns True if at least a front image was saved.
    """
    name = slugify(product.get("product_name") or product.get("code") or "unknown")
    if not name or name == "unknown":
        return False

    combined_path = dest_dir / f"{name}-combined.jpg"
    front_path    = dest_dir / f"{name}-front.jpg"

    if combined_path.exists() or front_path.exists():
        print(f"    skip (exists): {name}")
        return True

    front_url = product.get("image_front_url")
    back_url  = product.get("image_back_url")

    front_data = download_bytes(front_url) if front_url else None
    if not front_data:
        return False

    back_data = download_bytes(back_url) if back_url else None

    if front_data and back_data:
        if PILLOW_AVAILABLE:
            if stitch_side_by_side(front_data, back_data, combined_path):
                save_file(front_data, front_path)
                save_file(back_data,  dest_dir / f"{name}-back.jpg")
                return True
        # Pillow unavailable — save separately
        save_file(front_data, front_path)
        save_file(back_data,  dest_dir / f"{name}-back.jpg")
        return True
    else:
        if not back_data:
            print(f"    (no back image in OFF for '{name}')")
        save_file(front_data, front_path)
        return True


def download_from_off_category(
    off_category: str, dest_dir: Path, already: int, target: int
) -> int:
    count = already
    if count >= target:
        return count
    print(f"  Searching Open Food Facts category: {off_category}")
    products = off_search_category(off_category)
    if not products:
        print(f"  ✗ no results for OFF category '{off_category}'")
        return count
    for product in products:
        if count >= target:
            break
        time.sleep(BASE_DELAY)
        if download_off_product(product, dest_dir):
            count += 1
    return count


# ---------------------------------------------------------------------------
# Wikimedia Commons — category search
# ---------------------------------------------------------------------------

def wikimedia_category_files(category: str, limit: int = 40) -> list[str]:
    resp = get_with_retry(COMMONS_API, params={
        "action": "query", "list": "categorymembers",
        "cmtitle": f"Category:{category}", "cmtype": "file",
        "cmlimit": limit, "format": "json",
    })
    if not resp:
        return []
    members = resp.json().get("query", {}).get("categorymembers", [])
    return [m["title"].removeprefix("File:") for m in members]


def wikimedia_file_url(filename: str) -> str | None:
    resp = get_with_retry(COMMONS_API, params={
        "action": "query", "titles": f"File:{filename}",
        "prop": "imageinfo", "iiprop": "url", "format": "json",
    })
    if not resp:
        return None
    for page in resp.json().get("query", {}).get("pages", {}).values():
        for info in page.get("imageinfo", []):
            return info.get("url")
    return None


def download_from_commons_category(
    category: str, dest_dir: Path, already: int, target: int
) -> int:
    count = already
    if count >= target:
        return count
    print(f"  Searching Commons category: {category}")
    filenames = wikimedia_category_files(category)
    if not filenames:
        return count
    for filename in filenames:
        if count >= target:
            break
        if not is_image_filename(filename):
            continue
        local_name = filename.replace(" ", "_")
        if (dest_dir / local_name).exists():
            print(f"    skip (exists): {local_name}")
            count += 1
            continue
        time.sleep(BASE_DELAY)
        url = wikimedia_file_url(filename)
        if not url:
            continue
        data = download_bytes(url)
        if data:
            save_file(data, dest_dir / local_name)
            count += 1
    return count


# ---------------------------------------------------------------------------
# Product counting
# ---------------------------------------------------------------------------

def count_products(directory: Path) -> int:
    """
    Count distinct products. A combined, front, or back file all map to the
    same product stem and count as one.
    """
    if not directory.exists():
        return 0
    suffixes = (
        "-combined.jpg", "-combined.jpeg",
        "-front.jpg",    "-front.jpeg",    "-front.png",
        "-back.jpg",     "-back.jpeg",     "-back.png",
    )
    products: set[str] = set()
    for f in directory.iterdir():
        if not is_image_filename(f.name):
            continue
        stem = f.name
        for sfx in suffixes:
            if f.name.endswith(sfx):
                stem = f.name[: -len(sfx)]
                break
        products.add(stem)
    return len(products)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Test-labels directory: {LABELS_DIR}")
    print(
        f"Pillow: {'available (will stitch front+back)' if PILLOW_AVAILABLE else 'not available (will save separately)'}\n"
    )

    results: dict[str, int] = {}

    # ---- SPIRITS (Wikimedia — OFF has poor spirits coverage) ----
    print("=== SPIRITS (27 CFR Part 5) ===")
    spirits_dir = LABELS_DIR / "spirits"
    spirits_dir.mkdir(parents=True, exist_ok=True)
    count = count_products(spirits_dir)
    for cat in [
        "Bottles_of_whiskey",
        "Bourbon_whiskey_bottles",
        "Vodka_bottles",
        "Rum_bottles",
        "Gin_bottles",
        "Tequila_bottles",
        "Scotch_whisky_bottles",
    ]:
        if count >= MIN_PRODUCTS_PER_CATEGORY:
            break
        count = download_from_commons_category(cat, spirits_dir, count, MIN_PRODUCTS_PER_CATEGORY)
    results["spirits"] = count
    print(f"  → {count} product(s) in test-labels/spirits/\n")

    # ---- BEER (OFF category search, Wikimedia fallback) ----
    print("=== BEER (27 CFR Part 7) ===")
    beer_dir = LABELS_DIR / "beer"
    beer_dir.mkdir(parents=True, exist_ok=True)
    count = count_products(beer_dir)
    for off_cat in ["beers", "lagers", "ales", "craft-beers"]:
        if count >= MIN_PRODUCTS_PER_CATEGORY:
            break
        count = download_from_off_category(off_cat, beer_dir, count, MIN_PRODUCTS_PER_CATEGORY)
    for wm_cat in ["Beer_bottle_labels", "Beer_bottles", "Lager_bottles", "Ale_bottles"]:
        if count >= MIN_PRODUCTS_PER_CATEGORY:
            break
        count = download_from_commons_category(wm_cat, beer_dir, count, MIN_PRODUCTS_PER_CATEGORY)
    results["beer"] = count
    print(f"  → {count} product(s) in test-labels/beer/\n")

    # ---- WINE (OFF category search, Wikimedia fallback) ----
    print("=== WINE (27 CFR Part 4) ===")
    wine_dir = LABELS_DIR / "wine"
    wine_dir.mkdir(parents=True, exist_ok=True)
    count = count_products(wine_dir)
    for off_cat in ["wines", "red-wines", "white-wines", "rose-wines"]:
        if count >= MIN_PRODUCTS_PER_CATEGORY:
            break
        count = download_from_off_category(off_cat, wine_dir, count, MIN_PRODUCTS_PER_CATEGORY)
    for wm_cat in ["Wine_bottle_labels", "Wine_bottles", "Red_wine_bottles", "White_wine_bottles"]:
        if count >= MIN_PRODUCTS_PER_CATEGORY:
            break
        count = download_from_commons_category(wm_cat, wine_dir, count, MIN_PRODUCTS_PER_CATEGORY)
    results["wine"] = count
    print(f"  → {count} product(s) in test-labels/wine/\n")

    # ---- Summary ----
    print("=== SUMMARY ===")
    all_ok = True
    for cat, n in results.items():
        status = "✓" if n >= MIN_PRODUCTS_PER_CATEGORY else "✗ NEEDS MORE"
        print(f"  {status}  {cat}: {n}/{MIN_PRODUCTS_PER_CATEGORY}")
        if n < MIN_PRODUCTS_PER_CATEGORY:
            all_ok = False

    if not all_ok:
        print(
            "\nSome categories are short. Add images manually — "
            "see test-labels/README.md for sources including the TTB COLA registry."
        )
        sys.exit(1)
    else:
        print("\nAll categories meet the minimum. Commit test-labels/ to the repo.")


if __name__ == "__main__":
    main()
