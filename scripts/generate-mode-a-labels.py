#!/usr/bin/env python3
"""
Generate synthetic alcohol label images for Mode A (application-matching) testing.

Produces three pairs per beverage class: one compliant (label matches application),
and two noncompliant in different failure modes (label disagrees with the application).
All labels are CFR-compliant — GWS and mandatory fields are present — so the ONLY
violations are against the submitted application claims (R-APP-* rules).

Beer — Harbor Bay Brewing Co. / Harbor Bay Lager
  COMPLIANT         — label matches application exactly
  NONCOMPLIANT      — R-APP-01: brand name on label ≠ application
  NONCOMPLIANT      — R-APP-02: ABV on label outside ±0.5% tolerance vs application

Wine — Mesa Verde Winery / Mesa Verde Chardonnay
  COMPLIANT         — label matches application exactly
  NONCOMPLIANT      — R-APP-03: class/type designation ≠ application
  NONCOMPLIANT      — R-APP-05: appellation/origin ≠ application

Spirits — Canyon Ridge Distillery / Canyon Ridge Bourbon
  COMPLIANT         — label matches application exactly
  NONCOMPLIANT      — R-APP-04: net contents ≠ application
  NONCOMPLIANT      — R-APP-01 + R-APP-02: brand name AND ABV both differ

Usage (from repo root):
    uv run --with pillow scripts/generate-mode-a-labels.py

Output (18 front/back + 9 combined images):
    test-labels/beer/harbor-bay-lager-synth-mode-a-compliant-{front,back,combined}.jpg
    test-labels/beer/harbor-bay-lager-synth-mode-a-R-APP-01-{front,back,combined}.jpg
    test-labels/beer/harbor-bay-lager-synth-mode-a-R-APP-02-{front,back,combined}.jpg
    test-labels/wine/mesa-verde-chardonnay-synth-mode-a-compliant-{front,back,combined}.jpg
    test-labels/wine/mesa-verde-chardonnay-synth-mode-a-R-APP-03-{front,back,combined}.jpg
    test-labels/wine/mesa-verde-chardonnay-synth-mode-a-R-APP-05-{front,back,combined}.jpg
    test-labels/spirits/canyon-ridge-bourbon-synth-mode-a-compliant-{front,back,combined}.jpg
    test-labels/spirits/canyon-ridge-bourbon-synth-mode-a-R-APP-04-{front,back,combined}.jpg
    test-labels/spirits/canyon-ridge-bourbon-synth-mode-a-R-APP-01-02-{front,back,combined}.jpg
"""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Missing dependency — run: uv run --with pillow scripts/generate-mode-a-labels.py")

REPO_ROOT  = Path(__file__).resolve().parent.parent
LABELS_DIR = REPO_ROOT / "test-labels"

# ── canvas dimensions (match existing synthetic labels) ───────────────────────
W      = 900
H      = 1200
GAP    = 40
GAP_C  = (180, 180, 180)
BORDER = 18
JPEG_Q = 92

# ── Government Warning Statement (verbatim, 27 CFR 16.21) ────────────────────
GWS_HEADER = "GOVERNMENT WARNING:"
GWS_BODY = (
    "(1) According to the Surgeon General, women should not drink alcoholic "
    "beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a "
    "car or operate machinery, and may cause health problems."
)


# ── font loader (same as generate-synthetic-labels.py) ───────────────────────
_FONT_SEARCH = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
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
    for path in _FONT_SEARCH:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── drawing helpers ───────────────────────────────────────────────────────────

def wrap_text(text: str, font, max_width: int) -> list[str]:
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


def text_block(draw, text, x, y, font, fill, max_width, line_spacing=4):
    lines = wrap_text(text, font, max_width)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = font.getbbox(line)
        y += (bbox[3] - bbox[1]) + line_spacing
    return y


def centered(draw, text, y, font, fill, width):
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    x = (width - tw) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return y + (bbox[3] - bbox[1]) + 6


def hline(draw, y, color, width, margin=BORDER):
    draw.line([(margin, y), (width - margin, y)], fill=color, width=2)


def gws_block(draw, y, inner_w):
    """Draw a compliant Government Warning Statement block; return updated y."""
    gws_header_font = _font(17, bold=True)
    gws_body_font   = _font(17)
    draw.text((BORDER * 2, y), GWS_HEADER, font=gws_header_font, fill=(0, 0, 0))
    hdr_bbox = gws_header_font.getbbox(GWS_HEADER)
    y += (hdr_bbox[3] - hdr_bbox[1]) + 4
    y = text_block(draw, GWS_BODY, BORDER * 2, y, gws_body_font, (0, 0, 0), inner_w, line_spacing=3)
    return y


def save_label(front: Image.Image, back: Image.Image, dest_dir: Path, stem: str) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    front_path    = dest_dir / f"{stem}-front.jpg"
    back_path     = dest_dir / f"{stem}-back.jpg"
    combined_path = dest_dir / f"{stem}-combined.jpg"
    front.save(front_path,    "JPEG", quality=JPEG_Q)
    back.save(back_path,      "JPEG", quality=JPEG_Q)
    canvas = Image.new("RGB", (W + GAP + W, H), GAP_C)
    canvas.paste(front, (0, 0))
    canvas.paste(back,  (W + GAP, 0))
    canvas.save(combined_path, "JPEG", quality=JPEG_Q)
    print(f"  ✓ {front_path.name}")
    print(f"  ✓ {back_path.name}")
    print(f"  ✓ {combined_path.name}  ({W + GAP + W}×{H})")


# ─────────────────────────────────────────────────────────────────────────────
# BEER: Harbor Bay Brewing Co.  /  Harbor Bay Lager
# Application: brand="Harbor Bay Lager", class="American Lager",
#              abv=5.0%, net_contents="12 fl oz", origin="United States"
# ─────────────────────────────────────────────────────────────────────────────

def _beer_front(brand_line1: str, brand_line2: str, class_type: str,
                abv_text: str, contents_text: str) -> Image.Image:
    img  = Image.new("RGB", (W, H), (15, 50, 100))  # deep navy blue
    draw = ImageDraw.Draw(img)
    draw.rectangle([8, 8, W - 9, H - 9],    outline=(100, 160, 220), width=4)
    draw.rectangle([16, 16, W - 17, H - 17], outline=(70, 120, 180), width=1)

    y = 70
    y = centered(draw, brand_line1, y, _font(54, bold=True), (210, 235, 255), W)
    y = centered(draw, brand_line2, y + 4, _font(36, bold=True), (210, 235, 255), W)
    y += 28
    hline(draw, y, (100, 160, 220), W)
    y += 22
    y = centered(draw, class_type, y, _font(36, bold=True), (255, 255, 220), W)
    y += 20
    hline(draw, y, (100, 160, 220), W)
    y += 36
    y = centered(draw, "⚓  ⚓  ⚓", y, _font(26), (100, 150, 200), W)
    y += 20
    y = centered(draw, "San Francisco, California", y, _font(22), (160, 195, 230), W)
    y += 56
    draw.rectangle([BORDER * 2, y, W - BORDER * 2, y + 80], outline=(100, 160, 220), width=2)
    y += 16
    y = centered(draw, contents_text, y, _font(28, bold=True), (210, 235, 255), W)
    y += 30
    y = centered(draw, abv_text, y, _font(26, bold=True), (210, 235, 255), W)
    return img


def _beer_back(brand_full: str, note_text: str, note_color: tuple) -> Image.Image:
    img  = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([8, 8, W - 9, H - 9], outline=(15, 50, 100), width=3)

    y = 40
    y = centered(draw, brand_full, y, _font(20, bold=True), (15, 50, 100), W)
    y += 6
    hline(draw, y, (70, 120, 180), W)
    y += 18

    body_font  = _font(19)
    label_font = _font(19, bold=True)
    inner_w    = W - BORDER * 4

    draw.text((BORDER * 2, y), "BREWED AND PACKAGED BY:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(draw, "Harbor Bay Brewing Co.", BORDER * 2, y, body_font, (40, 40, 40), inner_w)
    y = text_block(draw, "550 Embarcadero St., San Francisco, CA 94105, USA", BORDER * 2, y, body_font, (40, 40, 40), inner_w)
    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    draw.text((BORDER * 2, y), "INGREDIENTS:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(draw, "Water, malted barley, hops, yeast.", BORDER * 2, y, body_font, (40, 40, 40), inner_w)
    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    y = gws_block(draw, y, inner_w)

    y += 16
    hline(draw, y, (200, 200, 200), W)
    y += 10
    y = text_block(draw, note_text, BORDER * 2, y, _font(14), note_color, inner_w)
    return img


def make_beer_compliant() -> tuple[Image.Image, Image.Image]:
    front = _beer_front("HARBOR BAY", "BREWING CO.",
                        "AMERICAN LAGER",
                        "5.0% Alc/Vol",
                        "12 FL OZ  (355 mL)")
    back  = _beer_back("HARBOR BAY AMERICAN LAGER",
                       "[SYNTHETIC — Mode A compliant: label matches application exactly]",
                       (150, 150, 150))
    return front, back


def make_beer_R_APP_01() -> tuple[Image.Image, Image.Image]:
    # Brand name on label: "HARBOR POINT LAGER" ≠ application "Harbor Bay Lager"
    front = _beer_front("HARBOR POINT", "BREWING CO.",
                        "AMERICAN LAGER",
                        "5.0% Alc/Vol",
                        "12 FL OZ  (355 mL)")
    back  = _beer_back("HARBOR POINT AMERICAN LAGER",
                       "[SYNTHETIC — Mode A NONCOMPLIANT — R-APP-01: brand 'Harbor Point Lager' ≠ application 'Harbor Bay Lager']",
                       (180, 30, 30))
    return front, back


def make_beer_R_APP_02() -> tuple[Image.Image, Image.Image]:
    # ABV on label: 5.8% ≠ application 5.0% (delta 0.8%, outside ±0.5% tolerance)
    front = _beer_front("HARBOR BAY", "BREWING CO.",
                        "AMERICAN LAGER",
                        "5.8% Alc/Vol",
                        "12 FL OZ  (355 mL)")
    back  = _beer_back("HARBOR BAY AMERICAN LAGER",
                       "[SYNTHETIC — Mode A NONCOMPLIANT — R-APP-02: ABV 5.8% on label vs 5.0% in application (delta 0.8%, outside ±0.5% tolerance)]",
                       (180, 30, 30))
    return front, back


# ─────────────────────────────────────────────────────────────────────────────
# WINE: Mesa Verde Winery  /  Mesa Verde Chardonnay
# Application: brand="Mesa Verde Chardonnay", class="Chardonnay",
#              abv=13.5%, net_contents="750 mL", origin="California"
# ─────────────────────────────────────────────────────────────────────────────

def _wine_front(brand_line1: str, brand_line2: str, vintage: str, class_type: str,
                appellation: str, abv_text: str) -> Image.Image:
    img  = Image.new("RGB", (W, H), (245, 242, 225))  # pale sage/cream
    draw = ImageDraw.Draw(img)
    draw.rectangle([8, 8, W - 9, H - 9],    outline=(90, 120, 70), width=3)
    draw.rectangle([16, 16, W - 17, H - 17], outline=(130, 160, 105), width=1)
    draw.rectangle([22, 22, W - 23, H - 23], outline=(90, 120, 70), width=1)

    y = 65
    y = centered(draw, brand_line1, y, _font(52, bold=True), (35, 60, 25), W)
    y = centered(draw, brand_line2, y + 4, _font(38, bold=True), (35, 60, 25), W)
    y += 26
    hline(draw, y, (100, 135, 75), W)
    y += 20
    y = centered(draw, vintage, y, _font(32), (70, 100, 50), W)
    y += 8
    y = centered(draw, class_type, y, _font(42, bold=True), (40, 70, 30), W)
    y += 16
    hline(draw, y, (100, 135, 75), W)
    y += 26
    y = centered(draw, appellation, y, _font(26), (90, 115, 65), W)
    y += 12
    y = centered(draw, "~  ~  ~", y, _font(20), (150, 175, 125), W)
    y += 28
    y = centered(draw, abv_text, y, _font(22, bold=True), (35, 60, 25), W)
    y += 12
    y = centered(draw, "750 mL", y, _font(22, bold=True), (35, 60, 25), W)
    return img


def _wine_back(brand_full: str, note_text: str, note_color: tuple) -> Image.Image:
    img  = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([8, 8, W - 9, H - 9], outline=(90, 120, 70), width=3)

    y = 40
    y = centered(draw, brand_full, y, _font(18, bold=True), (35, 60, 25), W)
    y += 6
    hline(draw, y, (100, 135, 75), W)
    y += 18

    body_font  = _font(19)
    label_font = _font(19, bold=True)
    inner_w    = W - BORDER * 4

    draw.text((BORDER * 2, y), "BOTTLED BY:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(draw, "Mesa Verde Winery, Inc.", BORDER * 2, y, body_font, (40, 40, 40), inner_w)
    y = text_block(draw, "1200 Vineyard Drive, Santa Barbara, CA 93103, USA", BORDER * 2, y, body_font, (40, 40, 40), inner_w)
    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    draw.text((BORDER * 2, y), "WINEMAKER'S NOTES:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(draw,
        "Crisp apple and fresh citrus aromas with hints of toasted oak and vanilla. "
        "Bright acidity and a clean, lingering mineral finish.",
        BORDER * 2, y, body_font, (40, 40, 40), inner_w)
    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    draw.text((BORDER * 2, y), "CONTAINS SULFITES", font=_font(19, bold=True), fill=(40, 40, 40))
    y += 28
    y += 6
    hline(draw, y, (200, 200, 200), W)
    y += 14

    y = gws_block(draw, y, inner_w)

    y += 16
    hline(draw, y, (200, 200, 200), W)
    y += 10
    y = text_block(draw, note_text, BORDER * 2, y, _font(14), note_color, inner_w)
    return img


def make_wine_compliant() -> tuple[Image.Image, Image.Image]:
    front = _wine_front("MESA VERDE", "WINERY",
                        "2023", "CHARDONNAY", "CALIFORNIA",
                        "Alcohol 13.5% by Volume")
    back  = _wine_back("MESA VERDE WINERY  2023 CHARDONNAY",
                       "[SYNTHETIC — Mode A compliant: label matches application exactly]",
                       (150, 150, 150))
    return front, back


def make_wine_R_APP_03() -> tuple[Image.Image, Image.Image]:
    # Class/type on label: "WHITE WINE" ≠ application "Chardonnay"
    front = _wine_front("MESA VERDE", "WINERY",
                        "2023", "WHITE WINE", "CALIFORNIA",
                        "Alcohol 13.5% by Volume")
    back  = _wine_back("MESA VERDE WINERY  2023 WHITE WINE",
                       "[SYNTHETIC — Mode A NONCOMPLIANT — R-APP-03: class 'White Wine' on label ≠ 'Chardonnay' in application]",
                       (180, 30, 30))
    return front, back


def make_wine_R_APP_05() -> tuple[Image.Image, Image.Image]:
    # Origin/appellation on label: "Sonoma County" ≠ application "California"
    front = _wine_front("MESA VERDE", "WINERY",
                        "2023", "CHARDONNAY", "SONOMA COUNTY",
                        "Alcohol 13.5% by Volume")
    back  = _wine_back("MESA VERDE WINERY  2023 CHARDONNAY",
                       "[SYNTHETIC — Mode A NONCOMPLIANT — R-APP-05: origin 'Sonoma County' on label ≠ 'California' in application]",
                       (180, 30, 30))
    return front, back


# ─────────────────────────────────────────────────────────────────────────────
# SPIRITS: Canyon Ridge Distillery  /  Canyon Ridge Bourbon
# Application: brand="Canyon Ridge Bourbon", class="Straight Bourbon Whiskey",
#              abv=45.0%, net_contents="750 mL", origin="United States"
# ─────────────────────────────────────────────────────────────────────────────

def _spirits_front(brand_line1: str, brand_line2: str, class_type: str,
                   abv_text: str, contents_text: str) -> Image.Image:
    img  = Image.new("RGB", (W, H), (45, 25, 10))   # dark walnut
    draw = ImageDraw.Draw(img)
    draw.rectangle([8, 8, W - 9, H - 9],    outline=(195, 155, 80), width=4)
    draw.rectangle([16, 16, W - 17, H - 17], outline=(145, 110, 50), width=1)

    y = 70
    y = centered(draw, brand_line1, y, _font(60, bold=True), (225, 195, 120), W)
    y = centered(draw, brand_line2, y + 4, _font(38, bold=True), (225, 195, 120), W)
    y += 28
    hline(draw, y, (175, 135, 60), W)
    y += 22
    y = centered(draw, class_type, y, _font(28, bold=True), (240, 220, 165), W)
    y += 20
    hline(draw, y, (175, 135, 60), W)
    y += 38
    y = centered(draw, "✦  ✦  ✦", y, _font(24), (170, 135, 65), W)
    y += 22
    y = centered(draw, "Lawrenceburg, Kentucky", y, _font(22), (195, 165, 100), W)
    y += 52
    y = centered(draw, abv_text, y, _font(28, bold=True), (240, 220, 165), W)
    y += 18
    y = centered(draw, contents_text, y, _font(26, bold=True), (240, 220, 165), W)
    return img


def _spirits_back(brand_full: str, note_text: str, note_color: tuple) -> Image.Image:
    img  = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([8, 8, W - 9, H - 9], outline=(45, 25, 10), width=3)

    y = 40
    y = centered(draw, brand_full, y, _font(20, bold=True), (45, 25, 10), W)
    y += 6
    hline(draw, y, (90, 60, 20), W)
    y += 18

    body_font  = _font(19)
    label_font = _font(19, bold=True)
    inner_w    = W - BORDER * 4

    draw.text((BORDER * 2, y), "DISTILLED AND BOTTLED BY:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(draw, "Canyon Ridge Distillery, LLC", BORDER * 2, y, body_font, (40, 40, 40), inner_w)
    y = text_block(draw, "300 Barrel House Rd., Lawrenceburg, KY 40342, USA", BORDER * 2, y, body_font, (40, 40, 40), inner_w)
    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    draw.text((BORDER * 2, y), "TASTING NOTES:", font=label_font, fill=(40, 40, 40))
    y += 26
    y = text_block(draw,
        "Notes of vanilla cream, toasted oak, brown sugar and dried cherry. "
        "Aged a minimum of 5 years in new charred American white oak.",
        BORDER * 2, y, body_font, (40, 40, 40), inner_w)
    y += 14
    hline(draw, y, (200, 200, 200), W)
    y += 14

    y = gws_block(draw, y, inner_w)

    y += 16
    hline(draw, y, (200, 200, 200), W)
    y += 10
    y = text_block(draw, note_text, BORDER * 2, y, _font(14), note_color, inner_w)
    return img


def make_spirits_compliant() -> tuple[Image.Image, Image.Image]:
    front = _spirits_front("CANYON RIDGE", "DISTILLERY",
                           "STRAIGHT BOURBON WHISKEY",
                           "45.0% Alc/Vol  (90 Proof)", "750 mL")
    back  = _spirits_back("CANYON RIDGE STRAIGHT BOURBON WHISKEY",
                          "[SYNTHETIC — Mode A compliant: label matches application exactly]",
                          (150, 150, 150))
    return front, back


def make_spirits_R_APP_04() -> tuple[Image.Image, Image.Image]:
    # Net contents on label: "1.0 L" ≠ application "750 mL"
    front = _spirits_front("CANYON RIDGE", "DISTILLERY",
                           "STRAIGHT BOURBON WHISKEY",
                           "45.0% Alc/Vol  (90 Proof)", "1.0 L")
    back  = _spirits_back("CANYON RIDGE STRAIGHT BOURBON WHISKEY",
                          "[SYNTHETIC — Mode A NONCOMPLIANT — R-APP-04: net contents '1.0 L' on label ≠ '750 mL' in application]",
                          (180, 30, 30))
    return front, back


def make_spirits_R_APP_01_02() -> tuple[Image.Image, Image.Image]:
    # Brand: "CANYON RIDGE RESERVE BOURBON" ≠ application "Canyon Ridge Bourbon"
    # ABV:   48.0% ≠ application 45.0% (delta 3.0%, well outside ±0.5% tolerance)
    front = _spirits_front("CANYON RIDGE", "RESERVE",
                           "STRAIGHT BOURBON WHISKEY",
                           "48.0% Alc/Vol  (96 Proof)", "750 mL")
    back  = _spirits_back("CANYON RIDGE RESERVE STRAIGHT BOURBON WHISKEY",
                          "[SYNTHETIC — Mode A NONCOMPLIANT — R-APP-01: brand 'Canyon Ridge Reserve Bourbon' ≠ application 'Canyon Ridge Bourbon'; R-APP-02: ABV 48.0% ≠ 45.0% in application]",
                          (180, 30, 30))
    return front, back


# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Generating Mode A synthetic test labels...\n")

    print("Beer — Harbor Bay Lager (Mode A compliant):")
    save_label(*make_beer_compliant(), LABELS_DIR / "beer",
               "harbor-bay-lager-synth-mode-a-compliant")

    print("\nBeer — Harbor Bay Lager (Mode A noncompliant — R-APP-01 brand mismatch):")
    save_label(*make_beer_R_APP_01(), LABELS_DIR / "beer",
               "harbor-bay-lager-synth-mode-a-R-APP-01")

    print("\nBeer — Harbor Bay Lager (Mode A noncompliant — R-APP-02 ABV mismatch):")
    save_label(*make_beer_R_APP_02(), LABELS_DIR / "beer",
               "harbor-bay-lager-synth-mode-a-R-APP-02")

    print("\nWine — Mesa Verde Chardonnay (Mode A compliant):")
    save_label(*make_wine_compliant(), LABELS_DIR / "wine",
               "mesa-verde-chardonnay-synth-mode-a-compliant")

    print("\nWine — Mesa Verde Chardonnay (Mode A noncompliant — R-APP-03 class mismatch):")
    save_label(*make_wine_R_APP_03(), LABELS_DIR / "wine",
               "mesa-verde-chardonnay-synth-mode-a-R-APP-03")

    print("\nWine — Mesa Verde Chardonnay (Mode A noncompliant — R-APP-05 origin mismatch):")
    save_label(*make_wine_R_APP_05(), LABELS_DIR / "wine",
               "mesa-verde-chardonnay-synth-mode-a-R-APP-05")

    print("\nSpirits — Canyon Ridge Bourbon (Mode A compliant):")
    save_label(*make_spirits_compliant(), LABELS_DIR / "spirits",
               "canyon-ridge-bourbon-synth-mode-a-compliant")

    print("\nSpirits — Canyon Ridge Bourbon (Mode A noncompliant — R-APP-04 net contents):")
    save_label(*make_spirits_R_APP_04(), LABELS_DIR / "spirits",
               "canyon-ridge-bourbon-synth-mode-a-R-APP-04")

    print("\nSpirits — Canyon Ridge Bourbon (Mode A noncompliant — R-APP-01+02 brand+ABV):")
    save_label(*make_spirits_R_APP_01_02(), LABELS_DIR / "spirits",
               "canyon-ridge-bourbon-synth-mode-a-R-APP-01-02")

    print("\nDone. 9 label pairs generated (27 files).")
    print("Application JSON files are in test-labels/applications/")
    print("Extraction fixtures are in tests/fixtures/extraction/")


if __name__ == "__main__":
    main()
