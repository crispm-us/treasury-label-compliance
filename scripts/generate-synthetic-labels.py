#!/usr/bin/env python3
"""
Generate synthetic alcohol label images for the test corpus.

Produces two pairs per beverage class (one compliant + one noncompliant).
All labels are rendered as front + back panels, then stitched into a combined image.

Beer:
  COMPLIANT   — Prairie Creek Brewing Co., American Lager (27 CFR Part 7)
  NONCOMPLIANT (R-GW-01) — Sunset Brewing Company, Amber Ale — GWS absent

Spirits:
  COMPLIANT   — Blue Ridge Distilling Co., Straight Rye Whiskey (27 CFR Part 5)
  NONCOMPLIANT (R-GW-03) — Iron Ridge Distillery, Straight Bourbon Whiskey
                           GWS header in title case, not all-caps bold

Wine:
  COMPLIANT   — Silverleaf Vineyards, 2023 Chardonnay (27 CFR Part 4)
  NONCOMPLIANT (R-WN-09) — Copper Creek Winery, 2022 Merlot — sulfite declaration absent

Usage (from repo root):
    uv run --with pillow scripts/generate-synthetic-labels.py

Output:
    test-labels/beer/prairie-creek-lager-{front,back,combined}.jpg
    test-labels/beer/sunset-ale-R-GW-01-{front,back,combined}.jpg
    test-labels/spirits/blue-ridge-rye-{front,back,combined}.jpg
    test-labels/spirits/iron-ridge-bourbon-R-GW-03-{front,back,combined}.jpg
    test-labels/wine/silverleaf-chardonnay-{front,back,combined}.jpg
    test-labels/wine/copper-creek-merlot-R-WN-09-{front,back,combined}.jpg
"""

import io
import sys
import textwrap
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Missing dependency — run: uv run --with pillow scripts/generate-synthetic-labels.py")

REPO_ROOT  = Path(__file__).resolve().parent.parent
LABELS_DIR = REPO_ROOT / "test-labels"

# ── label canvas dimensions ──────────────────────────────────────────────────
# Sized to approximate a typical bottle label at 150 DPI:
#   front: ~3" wide × 4.5" tall  → 450 × 675 px  (scaled ×2 → 900 × 1350)
#   back:  ~3" wide × 3.5" tall  → 450 × 525 px  (scaled ×2 → 900 × 1050)
# We normalise both panels to the same height before stitching.
W      = 900
H      = 1200   # same height for both panels so stitch is flush
GAP    = 40
GAP_C  = (180, 180, 180)
BORDER = 18     # inner border margin
JPEG_Q = 92

# ── Government Warning Statement ─────────────────────────────────────────────
GWS_HEADER   = "GOVERNMENT WARNING:"       # must be ALL-CAPS, BOLD per R-GW-03/R-GW-04
GWS_BODY     = (
    "(1) According to the Surgeon General, women should not drink alcoholic "
    "beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a "
    "car or operate machinery, and may cause health problems."
)

# R-GW-03 DEFECT version — title case header (wrong)
GWS_HEADER_DEFECTIVE = "Government Warning:"   # ← DEFECT: should be all-caps
GWS_BODY_DEFECTIVE   = (
    "(1) According to the Surgeon General, women should not drink alcoholic "
    "beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a "
    "car or operate machinery, and may cause health problems."
)


# ── font loader ───────────────────────────────────────────────────────────────
_FONT_SEARCH = [
    # Linux (sandbox)
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    # macOS (Zulu) — Helvetica Neue / Arial
    "/Library/Fonts/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]

def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    bold_marker = "Bold" if bold else "Regular"
    for path in _FONT_SEARCH:
        if bold_marker.lower() in path.lower() and Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    # Try any available sans-serif
    for path in _FONT_SEARCH:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── drawing helpers ───────────────────────────────────────────────────────────

def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    fill: tuple,
    max_width: int,
    line_spacing: int = 4,
) -> int:
    """Draw a wrapped text block; return the y position after the last line."""
    lines = wrap_text(text, font, max_width)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = font.getbbox(line)
        y += (bbox[3] - bbox[1]) + line_spacing
    return y


def centered(draw: ImageDraw.ImageDraw, text: str, y: int, font, fill, width: int) -> int:
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    x  = (width - tw) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return y + (bbox[3] - bbox[1]) + 6


def hline(draw: ImageDraw.ImageDraw, y: int, color: tuple, width: int, margin: int = BORDER) -> None:
    draw.line([(margin, y), (width - margin, y)], fill=color, width=2)


def save_label(front: Image.Image, back: Image.Image, dest_dir: Path, stem: str) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)

    front_path    = dest_dir / f"{stem}-front.jpg"
    back_path     = dest_dir / f"{stem}-back.jpg"
    combined_path = dest_dir / f"{stem}-combined.jpg"

    front.save(front_path,    "JPEG", quality=JPEG_Q)
    back.save(back_path,     "JPEG", quality=JPEG_Q)

    # stitch side-by-side (same height assumed)
    canvas = Image.new("RGB", (W + GAP + W, H), GAP_C)
    canvas.paste(front, (0, 0))
    canvas.paste(back,  (W + GAP, 0))
    canvas.save(combined_path, "JPEG", quality=JPEG_Q)

    print(f"  ✓ {front_path.name}")
    print(f"  ✓ {back_path.name}")
    print(f"  ✓ {combined_path.name}  ({W + GAP + W}×{H})")


# ─────────────────────────────────────────────────────────────────────────────
# Label 1: Prairie Creek Brewing Co. — American Lager  (COMPLIANT)
# ─────────────────────────────────────────────────────────────────────────────

def make_beer_front() -> Image.Image:
    img  = Image.new("RGB", (W, H), (253, 248, 236))   # warm cream
    draw = ImageDraw.Draw(img)

    # outer decorative border
    draw.rectangle([8, 8, W - 9, H - 9], outline=(120, 80, 30), width=4)
    draw.rectangle([14, 14, W - 15, H - 15], outline=(180, 130, 60), width=2)

    y = 80
    # Brand
    f_brand = _font(58, bold=True)
    y = centered(draw, "PRAIRIE CREEK", y, f_brand, (40, 20, 5), W)
    y = centered(draw, "BREWING CO.", y + 4, _font(46, bold=True), (40, 20, 5), W)

    y += 30
    hline(draw, y, (160, 110, 40), W)
    y += 20

    # Product class/type — required, 27 CFR 7.26
    y = centered(draw, "AMERICAN LAGER", y, _font(38, bold=True), (80, 50, 10), W)
    y += 20
    hline(draw, y, (160, 110, 40), W)

    # decorative middle section
    y += 40
    y = centered(draw, "★  ★  ★", y, _font(28), (140, 90, 30), W)
    y += 20
    y = centered(draw, "Est. Austin, Texas", y, _font(22), (100, 70, 20), W)
    y += 60

    # Net contents — required, 27 CFR 7.72 (metric + US customary)
    draw.rectangle([BORDER * 2, y, W - BORDER * 2, y + 80],
                   outline=(120, 80, 30), width=2)
    y += 16
    y = centered(draw, "12 FL OZ  (355 mL)", y, _font(30, bold=True), (40, 20, 5), W)

    return img


def make_beer_back() -> Image.Image:
    img  = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([8, 8, W - 9, H - 9], outline=(120, 80, 30), width=3)

    y = 40
    y = centered(draw, "PRAIRIE CREEK AMERICAN LAGER", y, _font(22, bold=True), (40, 20, 5), W)
    y += 6
    hline(draw, y, (160, 110, 40), W)
    y += 18

    # Brewer — required, 27 CFR 7.65
    body_font = _font(19)
    label_font = _font(19, bold=True)
    inner_w = W - BORDER * 4

    draw.text((BORDER * 2, y), "BREWED AND PACKAGED BY:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(draw, "Prairie Creek Brewing Co.", BORDER * 2, y, body_font, (40, 40, 40), inner_w)
    y = text_block(draw, "1234 Colorado River Blvd, Austin, TX 78701, USA", BORDER * 2, y, body_font, (40, 40, 40), inner_w)

    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    # Ingredients (optional but good practice)
    draw.text((BORDER * 2, y), "INGREDIENTS:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(draw, "Water, malted barley, hops, yeast.", BORDER * 2, y, body_font, (40, 40, 40), inner_w)

    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    # ── Government Warning Statement ─────────────────────────────────────────
    # R-GW-01: present  ✓
    # R-GW-02: verbatim text ✓
    # R-GW-03: "GOVERNMENT WARNING:" all-caps bold ✓
    # R-GW-04: header bold, body regular ✓
    # R-GW-05: contrasting background ✓

    gws_header_font = _font(17, bold=True)    # bold — R-GW-03 requires bold header
    gws_body_font   = _font(17)               # regular — R-GW-04 body not bold

    draw.text((BORDER * 2, y), GWS_HEADER, font=gws_header_font, fill=(0, 0, 0))
    hdr_bbox = gws_header_font.getbbox(GWS_HEADER)
    y += (hdr_bbox[3] - hdr_bbox[1]) + 4

    y = text_block(draw, GWS_BODY, BORDER * 2, y, gws_body_font, (0, 0, 0), inner_w, line_spacing=3)

    y += 16
    hline(draw, y, (200, 200, 200), W)
    y += 10

    # Synthetic label notice
    note_font = _font(14)
    y = text_block(
        draw,
        "[SYNTHETIC TEST LABEL — compliant — all mandatory fields present]",
        BORDER * 2, y, note_font, (150, 150, 150), inner_w,
    )

    return img


# ─────────────────────────────────────────────────────────────────────────────
# Label 2: Iron Ridge Distillery — Straight Bourbon Whiskey  (NONCOMPLIANT)
# Defect: R-GW-03 — GWS header rendered in title case, not all-caps bold
# ─────────────────────────────────────────────────────────────────────────────

def make_spirits_front() -> Image.Image:
    img  = Image.new("RGB", (W, H), (28, 22, 14))       # dark brown/black
    draw = ImageDraw.Draw(img)

    # gold border
    draw.rectangle([8, 8, W - 9, H - 9], outline=(180, 145, 60), width=4)
    draw.rectangle([16, 16, W - 17, H - 17], outline=(140, 110, 40), width=1)

    y = 70
    y = centered(draw, "IRON RIDGE", y, _font(64, bold=True), (210, 175, 80), W)
    y = centered(draw, "DISTILLERY", y + 4, _font(42, bold=True), (210, 175, 80), W)

    y += 30
    hline(draw, y, (160, 125, 50), W)
    y += 24

    # Class/type — required, 27 CFR 5.63
    y = centered(draw, "STRAIGHT BOURBON WHISKEY", y, _font(30, bold=True), (230, 210, 150), W)

    y += 20
    hline(draw, y, (160, 125, 50), W)
    y += 40

    y = centered(draw, "◆   ◆   ◆", y, _font(24), (160, 130, 60), W)
    y += 24
    y = centered(draw, "Bardstown, Kentucky", y, _font(22), (180, 155, 90), W)
    y += 50

    # ABV — required, 27 CFR 5.65
    y = centered(draw, "45% Alc/Vol  (90 Proof)", y, _font(28, bold=True), (230, 210, 150), W)
    y += 20
    # Net contents — required, 27 CFR 5.68
    y = centered(draw, "750 mL", y, _font(26, bold=True), (230, 210, 150), W)

    return img


def make_spirits_back() -> Image.Image:
    img  = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([8, 8, W - 9, H - 9], outline=(28, 22, 14), width=3)

    y = 40
    y = centered(draw, "IRON RIDGE STRAIGHT BOURBON WHISKEY", y, _font(20, bold=True), (28, 22, 14), W)
    y += 6
    hline(draw, y, (80, 60, 20), W)
    y += 18

    body_font  = _font(19)
    label_font = _font(19, bold=True)
    inner_w    = W - BORDER * 4

    # Bottler — required, 27 CFR 5.67
    draw.text((BORDER * 2, y), "DISTILLED AND BOTTLED BY:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(draw, "Iron Ridge Distillery, LLC", BORDER * 2, y, body_font, (40, 40, 40), inner_w)
    y = text_block(draw, "450 Whiskey Row, Bardstown, KY 40004, USA", BORDER * 2, y, body_font, (40, 40, 40), inner_w)

    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    # Tasting notes (optional)
    draw.text((BORDER * 2, y), "TASTING NOTES:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(
        draw,
        "Rich notes of vanilla, caramel oak and dried fruit. "
        "Aged a minimum of 4 years in new charred American oak barrels.",
        BORDER * 2, y, body_font, (40, 40, 40), inner_w,
    )

    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    # ── Government Warning Statement — DEFECTIVE (R-GW-03) ───────────────────
    # DEFECT: "Government Warning:" in title case — must be "GOVERNMENT WARNING:" (all-caps, bold)
    # R-GW-03 violation: header is not in all-capital letters
    # The body text is also in mixed case (compounding the defect, but R-GW-03 is primary)

    gws_header_defect = _font(17, bold=False)   # also not bold — second part of R-GW-03 violation
    gws_body_font     = _font(17)

    # Draw defective header in non-bold, title case
    draw.text((BORDER * 2, y), GWS_HEADER_DEFECTIVE, font=gws_header_defect, fill=(0, 0, 0))
    hdr_bbox = gws_header_defect.getbbox(GWS_HEADER_DEFECTIVE)
    y += (hdr_bbox[3] - hdr_bbox[1]) + 4

    y = text_block(draw, GWS_BODY_DEFECTIVE, BORDER * 2, y, gws_body_font, (0, 0, 0), inner_w, line_spacing=3)

    y += 16
    hline(draw, y, (200, 200, 200), W)
    y += 10

    note_font = _font(14)
    y = text_block(
        draw,
        "[SYNTHETIC TEST LABEL — NONCOMPLIANT — R-GW-03: GWS header in title case, not all-caps bold]",
        BORDER * 2, y, note_font, (180, 30, 30), inner_w,
    )

    return img


# ─────────────────────────────────────────────────────────────────────────────
# Label 3: Blue Ridge Distilling Co. — Straight Rye Whiskey  (COMPLIANT)
# ─────────────────────────────────────────────────────────────────────────────

def make_spirits_compliant_front() -> Image.Image:
    img  = Image.new("RGB", (W, H), (18, 42, 26))       # dark forest green
    draw = ImageDraw.Draw(img)

    # silver/grey border
    draw.rectangle([8, 8, W - 9, H - 9],   outline=(190, 200, 195), width=4)
    draw.rectangle([16, 16, W - 17, H - 17], outline=(140, 155, 148), width=1)

    y = 70
    y = centered(draw, "BLUE RIDGE", y, _font(64, bold=True), (210, 230, 210), W)
    y = centered(draw, "DISTILLING CO.", y + 4, _font(40, bold=True), (210, 230, 210), W)

    y += 30
    hline(draw, y, (160, 180, 165), W)
    y += 24

    # Class/type — required, 27 CFR 5.63
    y = centered(draw, "STRAIGHT RYE WHISKEY", y, _font(30, bold=True), (240, 245, 235), W)

    y += 20
    hline(draw, y, (160, 180, 165), W)
    y += 40

    y = centered(draw, "❧   ❧   ❧", y, _font(22), (160, 185, 165), W)
    y += 24
    y = centered(draw, "Lynchburg, Virginia", y, _font(22), (180, 205, 185), W)
    y += 50

    # ABV — required, 27 CFR 5.65
    y = centered(draw, "47% Alc/Vol  (94 Proof)", y, _font(28, bold=True), (240, 245, 235), W)
    y += 20
    # Net contents — required, 27 CFR 5.68
    y = centered(draw, "750 mL", y, _font(26, bold=True), (240, 245, 235), W)

    return img


def make_spirits_compliant_back() -> Image.Image:
    img  = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([8, 8, W - 9, H - 9], outline=(18, 42, 26), width=3)

    y = 40
    y = centered(draw, "BLUE RIDGE STRAIGHT RYE WHISKEY", y, _font(20, bold=True), (18, 42, 26), W)
    y += 6
    hline(draw, y, (60, 90, 70), W)
    y += 18

    body_font  = _font(19)
    label_font = _font(19, bold=True)
    inner_w    = W - BORDER * 4

    # Bottler — required, 27 CFR 5.67
    draw.text((BORDER * 2, y), "DISTILLED AND BOTTLED BY:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(draw, "Blue Ridge Distilling Co., LLC", BORDER * 2, y, body_font, (40, 40, 40), inner_w)
    y = text_block(draw, "88 Still House Road, Lynchburg, VA 24504, USA", BORDER * 2, y, body_font, (40, 40, 40), inner_w)

    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    draw.text((BORDER * 2, y), "TASTING NOTES:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(
        draw,
        "Bold rye spice with fresh cracked pepper, dried herbs, and a long, dry finish. "
        "Aged 3 years in new charred American oak barrels.",
        BORDER * 2, y, body_font, (40, 40, 40), inner_w,
    )

    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    # ── Government Warning Statement (COMPLIANT) ──────────────────────────────
    # R-GW-01: present  ✓
    # R-GW-02: verbatim text ✓
    # R-GW-03: "GOVERNMENT WARNING:" all-caps bold ✓
    # R-GW-04: header bold, body regular ✓

    gws_header_font = _font(17, bold=True)
    gws_body_font   = _font(17)

    draw.text((BORDER * 2, y), GWS_HEADER, font=gws_header_font, fill=(0, 0, 0))
    hdr_bbox = gws_header_font.getbbox(GWS_HEADER)
    y += (hdr_bbox[3] - hdr_bbox[1]) + 4

    y = text_block(draw, GWS_BODY, BORDER * 2, y, gws_body_font, (0, 0, 0), inner_w, line_spacing=3)

    y += 16
    hline(draw, y, (200, 200, 200), W)
    y += 10

    note_font = _font(14)
    y = text_block(
        draw,
        "[SYNTHETIC TEST LABEL — compliant — all mandatory fields present (27 CFR Part 5)]",
        BORDER * 2, y, note_font, (150, 150, 150), inner_w,
    )

    return img


# ─────────────────────────────────────────────────────────────────────────────
# Label 4: Sunset Brewing Company — Amber Ale  (NONCOMPLIANT)
# Defect: R-GW-01 — Government Warning Statement absent entirely
# ─────────────────────────────────────────────────────────────────────────────

def make_beer_noncompliant_front() -> Image.Image:
    img  = Image.new("RGB", (W, H), (200, 100, 20))     # deep amber/orange
    draw = ImageDraw.Draw(img)

    draw.rectangle([8, 8, W - 9, H - 9],    outline=(255, 200, 80), width=4)
    draw.rectangle([16, 16, W - 17, H - 17], outline=(220, 160, 40), width=1)

    y = 80
    y = centered(draw, "SUNSET", y, _font(72, bold=True), (255, 245, 200), W)
    y = centered(draw, "BREWING COMPANY", y + 4, _font(36, bold=True), (255, 245, 200), W)

    y += 30
    hline(draw, y, (255, 200, 80), W)
    y += 22

    # Class/type — required, 27 CFR 7.26
    y = centered(draw, "AMBER ALE", y, _font(42, bold=True), (255, 255, 220), W)

    y += 20
    hline(draw, y, (255, 200, 80), W)
    y += 40

    y = centered(draw, "☀  ☀  ☀", y, _font(26), (255, 220, 100), W)
    y += 20
    y = centered(draw, "Portland, Oregon", y, _font(22), (255, 230, 150), W)
    y += 60

    # Net contents — required, 27 CFR 7.72
    draw.rectangle([BORDER * 2, y, W - BORDER * 2, y + 80],
                   outline=(255, 200, 80), width=2)
    y += 16
    y = centered(draw, "12 FL OZ  (355 mL)", y, _font(30, bold=True), (255, 255, 220), W)

    return img


def make_beer_noncompliant_back() -> Image.Image:
    img  = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([8, 8, W - 9, H - 9], outline=(200, 100, 20), width=3)

    y = 40
    y = centered(draw, "SUNSET AMBER ALE", y, _font(22, bold=True), (180, 80, 10), W)
    y += 6
    hline(draw, y, (220, 130, 40), W)
    y += 18

    body_font  = _font(19)
    label_font = _font(19, bold=True)
    inner_w    = W - BORDER * 4

    # Brewer — required, 27 CFR 7.65
    draw.text((BORDER * 2, y), "BREWED AND PACKAGED BY:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(draw, "Sunset Brewing Company, Inc.", BORDER * 2, y, body_font, (40, 40, 40), inner_w)
    y = text_block(draw, "2200 NW Industrial St., Portland, OR 97201, USA", BORDER * 2, y, body_font, (40, 40, 40), inner_w)

    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    draw.text((BORDER * 2, y), "INGREDIENTS:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(draw, "Water, malted barley, crystal malt, hops, yeast.", BORDER * 2, y, body_font, (40, 40, 40), inner_w)

    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    draw.text((BORDER * 2, y), "TASTING NOTES:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(
        draw,
        "Rich toffee and caramel malt character with a clean, crisp finish. "
        "Medium body, earthy hop aroma.",
        BORDER * 2, y, body_font, (40, 40, 40), inner_w,
    )

    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    # ── Government Warning Statement — ABSENT (R-GW-01 DEFECT) ──────────────
    # DEFECT: No Government Warning Statement present on this label at all.
    # 27 CFR 16.21 requires the GWS on all alcoholic beverage labels ≥ 0.5% ABV.
    # (Space intentionally left empty where the GWS would appear.)

    draw.text((BORDER * 2, y), "BEST BEFORE: See bottom of can.", font=body_font, fill=(80, 80, 80))
    y += 28

    y += 20
    hline(draw, y, (200, 200, 200), W)
    y += 10

    note_font = _font(14)
    y = text_block(
        draw,
        "[SYNTHETIC TEST LABEL — NONCOMPLIANT — R-GW-01: Government Warning Statement absent]",
        BORDER * 2, y, note_font, (180, 30, 30), inner_w,
    )

    return img


# ─────────────────────────────────────────────────────────────────────────────
# Label 5: Silverleaf Vineyards — 2023 Chardonnay  (COMPLIANT)
# ─────────────────────────────────────────────────────────────────────────────

def make_wine_compliant_front() -> Image.Image:
    img  = Image.new("RGB", (W, H), (252, 250, 240))    # warm cream/ivory
    draw = ImageDraw.Draw(img)

    # elegant double border
    draw.rectangle([8, 8, W - 9, H - 9],    outline=(140, 120, 60), width=3)
    draw.rectangle([16, 16, W - 17, H - 17], outline=(190, 170, 90), width=1)
    draw.rectangle([22, 22, W - 23, H - 23], outline=(140, 120, 60), width=1)

    y = 70
    y = centered(draw, "SILVERLEAF", y, _font(56, bold=True), (60, 50, 20), W)
    y = centered(draw, "VINEYARDS", y + 4, _font(44, bold=True), (60, 50, 20), W)

    y += 28
    hline(draw, y, (160, 135, 55), W)
    y += 22

    y = centered(draw, "2023", y, _font(34), (100, 80, 30), W)
    y += 10
    # Class/type designation — required, 27 CFR 4.34
    y = centered(draw, "CHARDONNAY", y, _font(44, bold=True), (80, 60, 20), W)

    y += 16
    hline(draw, y, (160, 135, 55), W)
    y += 30

    # Appellation of origin — 27 CFR 4.25 (if used, adds mandatory disclosure)
    y = centered(draw, "CALIFORNIA", y, _font(26), (120, 100, 40), W)
    y += 14
    y = centered(draw, "~~~~", y, _font(20), (180, 155, 80), W)
    y += 30

    # ABV — required, 27 CFR 4.36
    y = centered(draw, "Alcohol 13.5% by Volume", y, _font(22, bold=True), (60, 50, 20), W)
    y += 14
    # Net contents — required, 27 CFR 4.37
    y = centered(draw, "750 mL", y, _font(22, bold=True), (60, 50, 20), W)

    return img


def make_wine_compliant_back() -> Image.Image:
    img  = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([8, 8, W - 9, H - 9], outline=(140, 120, 60), width=3)

    y = 40
    y = centered(draw, "SILVERLEAF VINEYARDS  2023 CHARDONNAY", y, _font(18, bold=True), (60, 50, 20), W)
    y += 6
    hline(draw, y, (160, 135, 55), W)
    y += 18

    body_font  = _font(19)
    label_font = _font(19, bold=True)
    inner_w    = W - BORDER * 4

    # Name and address — required, 27 CFR 4.35
    draw.text((BORDER * 2, y), "BOTTLED BY:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(draw, "Silverleaf Vineyards, LLC", BORDER * 2, y, body_font, (40, 40, 40), inner_w)
    y = text_block(draw, "789 Valley Road, Napa, CA 94558, USA", BORDER * 2, y, body_font, (40, 40, 40), inner_w)

    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    draw.text((BORDER * 2, y), "WINEMAKER'S NOTES:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(
        draw,
        "Barrel-fermented in French oak for 9 months. Aromas of crisp apple, "
        "ripe pear and toasted oak. Creamy, full-bodied with a long mineral finish.",
        BORDER * 2, y, body_font, (40, 40, 40), inner_w,
    )

    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    # Sulfite declaration — required when SO₂ ≥ 10 ppm, 27 CFR 16.20 / R-WN-09
    draw.text((BORDER * 2, y), "CONTAINS SULFITES", font=_font(19, bold=True), fill=(40, 40, 40))
    y += 28

    y += 6
    hline(draw, y, (200, 200, 200), W)
    y += 14

    # ── Government Warning Statement (COMPLIANT) ──────────────────────────────
    gws_header_font = _font(17, bold=True)
    gws_body_font   = _font(17)

    draw.text((BORDER * 2, y), GWS_HEADER, font=gws_header_font, fill=(0, 0, 0))
    hdr_bbox = gws_header_font.getbbox(GWS_HEADER)
    y += (hdr_bbox[3] - hdr_bbox[1]) + 4

    y = text_block(draw, GWS_BODY, BORDER * 2, y, gws_body_font, (0, 0, 0), inner_w, line_spacing=3)

    y += 16
    hline(draw, y, (200, 200, 200), W)
    y += 10

    note_font = _font(14)
    y = text_block(
        draw,
        "[SYNTHETIC TEST LABEL — compliant — all mandatory fields present (27 CFR Part 4)]",
        BORDER * 2, y, note_font, (150, 150, 150), inner_w,
    )

    return img


# ─────────────────────────────────────────────────────────────────────────────
# Label 6: Copper Creek Winery — 2022 Merlot  (NONCOMPLIANT)
# Defect: R-WN-09 — sulfite declaration absent
# ─────────────────────────────────────────────────────────────────────────────

def make_wine_noncompliant_front() -> Image.Image:
    img  = Image.new("RGB", (W, H), (80, 15, 30))       # deep burgundy
    draw = ImageDraw.Draw(img)

    draw.rectangle([8, 8, W - 9, H - 9],    outline=(180, 100, 110), width=4)
    draw.rectangle([16, 16, W - 17, H - 17], outline=(130, 60, 70), width=1)

    y = 70
    y = centered(draw, "COPPER CREEK", y, _font(56, bold=True), (235, 200, 200), W)
    y = centered(draw, "WINERY", y + 4, _font(44, bold=True), (235, 200, 200), W)

    y += 28
    hline(draw, y, (160, 80, 90), W)
    y += 22

    y = centered(draw, "2022", y, _font(34), (210, 170, 170), W)
    y += 10
    # Class/type — required, 27 CFR 4.34
    y = centered(draw, "MERLOT", y, _font(52, bold=True), (245, 215, 215), W)

    y += 16
    hline(draw, y, (160, 80, 90), W)
    y += 30

    y = centered(draw, "CALIFORNIA", y, _font(26), (205, 165, 165), W)
    y += 14
    y = centered(draw, "~  ~  ~", y, _font(22), (170, 110, 115), W)
    y += 30

    # ABV — required, 27 CFR 4.36
    y = centered(draw, "Alcohol 14.2% by Volume", y, _font(22, bold=True), (240, 215, 215), W)
    y += 14
    # Net contents — required, 27 CFR 4.37
    y = centered(draw, "750 mL", y, _font(22, bold=True), (240, 215, 215), W)

    return img


def make_wine_noncompliant_back() -> Image.Image:
    img  = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([8, 8, W - 9, H - 9], outline=(80, 15, 30), width=3)

    y = 40
    y = centered(draw, "COPPER CREEK WINERY  2022 MERLOT", y, _font(18, bold=True), (80, 15, 30), W)
    y += 6
    hline(draw, y, (130, 60, 70), W)
    y += 18

    body_font  = _font(19)
    label_font = _font(19, bold=True)
    inner_w    = W - BORDER * 4

    # Name and address — required, 27 CFR 4.35
    draw.text((BORDER * 2, y), "BOTTLED BY:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(draw, "Copper Creek Winery, LLC", BORDER * 2, y, body_font, (40, 40, 40), inner_w)
    y = text_block(draw, "456 Vineyard Lane, Sonoma, CA 95476, USA", BORDER * 2, y, body_font, (40, 40, 40), inner_w)

    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    draw.text((BORDER * 2, y), "WINEMAKER'S NOTES:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(
        draw,
        "Plush dark cherry, blackberry and mocha on the palate. Velvety tannins with "
        "a warm, spice-laden finish. Aged 16 months in French and American oak.",
        BORDER * 2, y, body_font, (40, 40, 40), inner_w,
    )

    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    # ── Sulfite declaration — ABSENT (R-WN-09 DEFECT) ────────────────────────
    # DEFECT: "CONTAINS SULFITES" declaration is missing.
    # 27 CFR 16.20 / R-WN-09 requires this statement when SO₂ ≥ 10 ppm.
    # (Wines treated with SO₂ as a preservative must disclose; space intentionally blank.)

    # ── Government Warning Statement (COMPLIANT — GWS correct; only sulfites defective) ─
    gws_header_font = _font(17, bold=True)
    gws_body_font   = _font(17)

    draw.text((BORDER * 2, y), GWS_HEADER, font=gws_header_font, fill=(0, 0, 0))
    hdr_bbox = gws_header_font.getbbox(GWS_HEADER)
    y += (hdr_bbox[3] - hdr_bbox[1]) + 4

    y = text_block(draw, GWS_BODY, BORDER * 2, y, gws_body_font, (0, 0, 0), inner_w, line_spacing=3)

    y += 16
    hline(draw, y, (200, 200, 200), W)
    y += 10

    note_font = _font(14)
    y = text_block(
        draw,
        "[SYNTHETIC TEST LABEL — NONCOMPLIANT — R-WN-09: CONTAINS SULFITES declaration absent]",
        BORDER * 2, y, note_font, (180, 30, 30), inner_w,
    )

    return img


# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Generating synthetic test labels…\n")

    print("Beer — Prairie Creek American Lager (compliant):")
    save_label(
        make_beer_front(),
        make_beer_back(),
        LABELS_DIR / "beer",
        "prairie-creek-lager",
    )

    print("\nBeer — Sunset Amber Ale (noncompliant R-GW-01 — GWS absent):")
    save_label(
        make_beer_noncompliant_front(),
        make_beer_noncompliant_back(),
        LABELS_DIR / "beer",
        "sunset-ale-R-GW-01",
    )

    print("\nSpirits — Blue Ridge Rye Whiskey (compliant):")
    save_label(
        make_spirits_compliant_front(),
        make_spirits_compliant_back(),
        LABELS_DIR / "spirits",
        "blue-ridge-rye",
    )

    print("\nSpirits — Iron Ridge Bourbon (noncompliant R-GW-03):")
    save_label(
        make_spirits_front(),
        make_spirits_back(),
        LABELS_DIR / "spirits",
        "iron-ridge-bourbon-R-GW-03",
    )

    print("\nWine — Silverleaf Chardonnay (compliant):")
    save_label(
        make_wine_compliant_front(),
        make_wine_compliant_back(),
        LABELS_DIR / "wine",
        "silverleaf-chardonnay",
    )

    print("\nWine — Copper Creek Merlot (noncompliant R-WN-09 — sulfite declaration absent):")
    save_label(
        make_wine_noncompliant_front(),
        make_wine_noncompliant_back(),
        LABELS_DIR / "wine",
        "copper-creek-merlot-R-WN-09",
    )

    print("\nDone. Review images before committing to the repo.")
    print("Run: uv run --with pillow scripts/stitch-labels.py  (already stitched above)")


if __name__ == "__main__":
    main()
