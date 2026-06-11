#!/usr/bin/env python3
"""
Stitch front+back label image pairs into side-by-side combined images.

For every *-front.jpg (or .jpeg/.png) in test-labels/**, finds the
corresponding *-back.jpg and produces *-combined.jpg alongside them.

Usage (from repo root):
    uv run --with pillow scripts/stitch-labels.py

Safe to re-run: skips pairs whose combined file already exists.
"""

import io
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Missing dependency — run:  uv run --with pillow scripts/stitch-labels.py")

REPO_ROOT  = Path(__file__).resolve().parent.parent
LABELS_DIR = REPO_ROOT / "test-labels"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
FRONT_SUFFIXES   = ("-front.jpg", "-front.jpeg", "-front.png", "-front.webp")
BACK_SUFFIXES    = ("-back.jpg",  "-back.jpeg",  "-back.png",  "-back.webp")

MAX_HEIGHT  = 1800   # cap combined image height; width scales proportionally
JPEG_QUALITY = 85
GAP_PX       = 32    # gray gap between front and back panels
GAP_COLOR    = (160, 160, 160)


def fit_to_height(img: Image.Image, target_h: int) -> Image.Image:
    if img.height == target_h:
        return img
    w = int(img.width * target_h / img.height)
    return img.resize((w, target_h), Image.LANCZOS)


def stitch(front_path: Path, back_path: Path, combined_path: Path) -> bool:
    try:
        front = Image.open(front_path).convert("RGB")
        back  = Image.open(back_path).convert("RGB")
    except Exception as exc:
        print(f"  ✗ could not open images: {exc}")
        return False

    target_h = min(max(front.height, back.height), MAX_HEIGHT)
    front    = fit_to_height(front, target_h)
    back     = fit_to_height(back,  target_h)

    canvas = Image.new("RGB",
                       (front.width + GAP_PX + back.width, target_h),
                       GAP_COLOR)
    canvas.paste(front, (0, 0))
    canvas.paste(back,  (front.width + GAP_PX, 0))

    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=JPEG_QUALITY)
    combined_path.write_bytes(buf.getvalue())
    size_kb = len(buf.getvalue()) // 1024
    print(f"  ✓ {combined_path.name} ({front.width + GAP_PX + back.width}×{target_h}, {size_kb} KB)")
    return True


def find_pairs(directory: Path) -> list[tuple[Path, Path, Path]]:
    """
    Return (front_path, back_path, combined_path) tuples for every
    front file that has a matching back file in the same directory.
    """
    pairs = []
    for front_path in sorted(directory.rglob("*")):
        if not front_path.is_file():
            continue
        stem = None
        for sfx in FRONT_SUFFIXES:
            if front_path.name.lower().endswith(sfx):
                stem = front_path.name[: -len(sfx)]
                break
        if stem is None:
            continue

        # Find matching back file
        back_path = None
        for sfx in BACK_SUFFIXES:
            candidate = front_path.parent / (stem + sfx)
            if candidate.exists():
                back_path = candidate
                break
        if back_path is None:
            print(f"  ! no back image found for {front_path.name} — skipping")
            continue

        combined_path = front_path.parent / (stem + "-combined.jpg")
        pairs.append((front_path, back_path, combined_path))

    return pairs


def main() -> None:
    if not LABELS_DIR.exists():
        sys.exit(f"test-labels directory not found: {LABELS_DIR}")

    pairs = find_pairs(LABELS_DIR)
    if not pairs:
        print("No front+back pairs found. Name your files *-front.jpg and *-back.jpg.")
        sys.exit(0)

    stitched = 0
    skipped  = 0

    for front_path, back_path, combined_path in pairs:
        rel = combined_path.relative_to(REPO_ROOT)
        if combined_path.exists():
            print(f"  skip (exists): {rel}")
            skipped += 1
            continue
        print(f"  stitching {front_path.name} + {back_path.name}")
        if stitch(front_path, back_path, combined_path):
            stitched += 1

    print(f"\nDone: {stitched} stitched, {skipped} skipped.")


if __name__ == "__main__":
    main()
