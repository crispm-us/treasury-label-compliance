#!/usr/bin/env python3
"""
Download example alcohol label images into test-labels/.

Run from the repo root on a machine with unrestricted internet access:

    pip install requests
    python scripts/download-test-labels.py

Sources:
  - Wikimedia Commons API (no key required, CC-licensed images)
  - Open Food Facts API   (no key required, ODbL-licensed product images)

The script is idempotent: already-downloaded files are skipped.
"""

import json
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Install requests first:  pip install requests")

REPO_ROOT = Path(__file__).resolve().parent.parent
LABELS_DIR = REPO_ROOT / "test-labels"
MIN_PER_CATEGORY = 3
REQUEST_DELAY = 0.5  # seconds between API calls — be polite

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
OFF_API = "https://world.openfoodfacts.org/api/v2/product"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "treasury-label-compliance-test/1.0 (https://github.com/crispm-us/treasury-label-compliance)"})

# ---------------------------------------------------------------------------
# Wikimedia Commons helpers
# ---------------------------------------------------------------------------

def wikimedia_category_files(category: str, limit: int = 20) -> list[str]:
    """Return filenames (without 'File:' prefix) in a Commons category."""
    resp = SESSION.get(COMMONS_API, params={
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmtype": "file",
        "cmlimit": limit,
        "format": "json",
    }, timeout=15)
    resp.raise_for_status()
    members = resp.json().get("query", {}).get("categorymembers", [])
    return [m["title"].removeprefix("File:") for m in members]


def wikimedia_file_url(filename: str) -> str | None:
    """Resolve a Commons filename to its direct download URL."""
    resp = SESSION.get(COMMONS_API, params={
        "action": "query",
        "titles": f"File:{filename}",
        "prop": "imageinfo",
        "iiprop": "url|size",
        "format": "json",
    }, timeout=15)
    resp.raise_for_status()
    for page in resp.json().get("query", {}).get("pages", {}).values():
        for info in page.get("imageinfo", []):
            return info.get("url")
    return None


# ---------------------------------------------------------------------------
# Open Food Facts helper
# ---------------------------------------------------------------------------

def off_front_image_url(barcode: str) -> str | None:
    """Return the front-label image URL for a product barcode, or None."""
    resp = SESSION.get(
        f"{OFF_API}/{barcode}",
        params={"fields": "product_name,image_front_url"},
        timeout=15,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json().get("product", {}).get("image_front_url")


# ---------------------------------------------------------------------------
# Download helper
# ---------------------------------------------------------------------------

def download(url: str, dest: Path) -> bool:
    """Download url to dest. Returns True on success."""
    if dest.exists():
        print(f"    skip (exists): {dest.name}")
        return True
    try:
        r = SESSION.get(url, stream=True, timeout=30)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(8192):
                fh.write(chunk)
        size_kb = dest.stat().st_size // 1024
        print(f"    ✓ {dest.name} ({size_kb} KB)")
        return True
    except Exception as exc:
        print(f"    ✗ {dest.name}: {exc}")
        if dest.exists():
            dest.unlink()
        return False


def is_image_filename(name: str) -> bool:
    return name.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))


# ---------------------------------------------------------------------------
# Per-category download logic
# ---------------------------------------------------------------------------

def download_from_commons_category(
    category: str, dest_dir: Path, already: int, target: int
) -> int:
    """Try to reach `target` images in dest_dir from a Wikimedia category."""
    count = already
    if count >= target:
        return count
    print(f"  Searching Commons category: {category}")
    try:
        filenames = wikimedia_category_files(category, limit=30)
    except Exception as exc:
        print(f"  ✗ Category lookup failed: {exc}")
        return count

    for filename in filenames:
        if count >= target:
            break
        if not is_image_filename(filename):
            continue
        time.sleep(REQUEST_DELAY)
        try:
            url = wikimedia_file_url(filename)
        except Exception as exc:
            print(f"    ✗ URL lookup for {filename}: {exc}")
            continue
        if not url:
            continue
        local_name = filename.replace(" ", "_")
        if download(url, dest_dir / local_name):
            count += 1
    return count


def download_from_off_barcodes(
    barcodes: list[tuple[str, str]], dest_dir: Path, already: int, target: int
) -> int:
    """Try to reach `target` images in dest_dir from Open Food Facts barcodes."""
    count = already
    for barcode, local_name in barcodes:
        if count >= target:
            break
        time.sleep(REQUEST_DELAY)
        try:
            url = off_front_image_url(barcode)
        except Exception as exc:
            print(f"    ✗ OFF lookup for {barcode}: {exc}")
            continue
        if not url:
            print(f"    ✗ No front image for barcode {barcode}")
            continue
        if download(url, dest_dir / local_name):
            count += 1
    return count


def count_images(directory: Path) -> int:
    if not directory.exists():
        return 0
    return sum(1 for f in directory.iterdir() if is_image_filename(f.name))


# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

# (barcode, local_filename) pairs — Open Food Facts
BEER_BARCODES: list[tuple[str, str]] = [
    ("8714800310006", "heineken-lager.jpg"),
    ("018200001021",  "budweiser.jpg"),
    ("088321100018",  "sierra-nevada-pale-ale.jpg"),
    ("048992600031",  "samuel-adams-boston-lager.jpg"),
    ("0049800041937", "corona-extra.jpg"),
]

WINE_BARCODES: list[tuple[str, str]] = [
    ("9300696007247", "yellow-tail-shiraz.jpg"),
    ("0085000001008", "barefoot-cabernet.jpg"),
    ("3500610068094", "la-vieille-ferme-rose.jpg"),
    ("9414024020017", "cloudy-bay-sauvignon-blanc.jpg"),
    ("0085156700014", "josh-cellars-chardonnay.jpg"),
]

# Wikimedia Commons categories (no keys required; search order is fallback order)
SPIRITS_CATEGORIES = [
    "Bottles_of_whiskey",
    "Bourbon_whiskey_bottles",
    "Vodka_bottles",
    "Rum_bottles",
]

BEER_COMMONS_CATEGORIES = [
    "Beer_bottle_labels",
    "Beer_bottles",
    "Lager_bottles",
]

WINE_COMMONS_CATEGORIES = [
    "Wine_bottle_labels",
    "Wine_bottles",
    "Red_wine_bottles",
    "White_wine_bottles",
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Test-labels directory: {LABELS_DIR}\n")

    results: dict[str, int] = {}

    # --- SPIRITS (Wikimedia only — Open Food Facts has poor spirits coverage) ---
    print("=== SPIRITS (27 CFR Part 5) ===")
    spirits_dir = LABELS_DIR / "spirits"
    spirits_dir.mkdir(parents=True, exist_ok=True)
    count = count_images(spirits_dir)
    for cat in SPIRITS_CATEGORIES:
        if count >= MIN_PER_CATEGORY:
            break
        count = download_from_commons_category(cat, spirits_dir, count, MIN_PER_CATEGORY)
    results["spirits"] = count
    print(f"  → {count} image(s) in test-labels/spirits/\n")

    # --- BEER (Open Food Facts first, Wikimedia supplement) ---
    print("=== BEER (27 CFR Part 7) ===")
    beer_dir = LABELS_DIR / "beer"
    beer_dir.mkdir(parents=True, exist_ok=True)
    count = count_images(beer_dir)
    if count < MIN_PER_CATEGORY:
        count = download_from_off_barcodes(BEER_BARCODES, beer_dir, count, MIN_PER_CATEGORY)
    for cat in BEER_COMMONS_CATEGORIES:
        if count >= MIN_PER_CATEGORY:
            break
        count = download_from_commons_category(cat, beer_dir, count, MIN_PER_CATEGORY)
    results["beer"] = count
    print(f"  → {count} image(s) in test-labels/beer/\n")

    # --- WINE (Open Food Facts first, Wikimedia supplement) ---
    print("=== WINE (27 CFR Part 4) ===")
    wine_dir = LABELS_DIR / "wine"
    wine_dir.mkdir(parents=True, exist_ok=True)
    count = count_images(wine_dir)
    if count < MIN_PER_CATEGORY:
        count = download_from_off_barcodes(WINE_BARCODES, wine_dir, count, MIN_PER_CATEGORY)
    for cat in WINE_COMMONS_CATEGORIES:
        if count >= MIN_PER_CATEGORY:
            break
        count = download_from_commons_category(cat, wine_dir, count, MIN_PER_CATEGORY)
    results["wine"] = count
    print(f"  → {count} image(s) in test-labels/wine/\n")

    # --- Summary ---
    print("=== SUMMARY ===")
    all_ok = True
    for category, n in results.items():
        status = "✓" if n >= MIN_PER_CATEGORY else "✗ NEEDS MORE"
        print(f"  {status}  {category}: {n}/{MIN_PER_CATEGORY}")
        if n < MIN_PER_CATEGORY:
            all_ok = False

    if not all_ok:
        print(
            "\nSome categories have fewer than the minimum. Add images manually — "
            "see test-labels/README.md for sources including the TTB COLA registry."
        )
        sys.exit(1)
    else:
        print("\nAll categories meet the minimum. Commit test-labels/ to the repo.")


if __name__ == "__main__":
    main()
