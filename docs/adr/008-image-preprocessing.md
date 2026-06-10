# ADR-008: Image Preprocessing and Format Handling

Date: 2026-06-09
Status: Accepted

## Context

Label images arrive from a variety of sources (smartphone photos, document scanners, existing archives) in a variety of formats and resolutions. Sending oversized images to vision models wastes tokens and increases latency; sending over-compressed images risks making text unreadable. The system must handle the full range gracefully.

Key constraints:
- Claude API native resolution: 1568px max on long edge (Sonnet/Haiku); tokens ≈ width×height/750, capped at ~1568 tokens
- Claude API does not support HEIC/HEIF or TIFF natively
- HEIC is the default format on iPhones — a significant real-world input source
- Heavy JPEG compression introduces artifacts that impair text OCR (Anthropic docs: "heavy JPEG compression can make text difficult to read")
- Gemini Flash tile cost drops dramatically if images are ≤768px both dimensions (1 tile = 258 tokens vs. 4+ tiles for larger images)
- The SLA requires model responses within 4.5 seconds; reducing image payload reduces network time

## Decision

All images are processed through a preprocessing pipeline in the backend before being sent to any model. The pipeline runs in two phases: **format normalization** then **resolution targeting**.

### Phase 1: Format Normalization

Convert everything to JPEG (or PNG for images with transparency) before further processing:

| Input format | Action |
|---|---|
| JPEG | Pass through |
| PNG | Pass through (preserve if transparency present; else convert to JPEG) |
| WebP | Convert to JPEG |
| GIF | Extract first frame, convert to JPEG |
| HEIC / HEIF | Convert to JPEG (requires `pillow-heif` plugin) |
| TIFF | Convert to JPEG |
| PDF | Extract first page as image, convert to JPEG (requires `pdf2image` / `pypdfium2`) |

### Phase 2: Resolution Targeting

```
Target: 1200px max long edge, JPEG quality 85
Result: ~100–300KB for a typical bottle label photo, ~1000–1500 tokens
```

This fits within Claude's native resolution window (1568px cap) without triggering upsampling, and fits within 2×2 Gemini tiles (1032 tokens). Text on standard bottle labels is legible at this resolution.

### Backoff Strategy

If the model response indicates it cannot read the image — defined as: model explicitly states it cannot read text, OR confidence score on >50% of fields is "low" or "not_found" — the pipeline retries at a higher resolution:

```
Attempt 1:  1200px max long edge, JPEG 85  →  send to model
             ↓ (if unreadable)
Attempt 2:  2400px max long edge, JPEG 90  →  send to model
             ↓ (if still unreadable)
Attempt 3:  original resolution (up to 8000×8000 / 10MB limit), JPEG 92  →  send to model
             ↓ (if still unreadable)
Return error: "Label image is not readable at any resolution. Please submit a clearer photo."
```

Each retry uses the same model and fallback chain (ADR-001). The resolution is increased, not the model tier — the cost increase from a larger image is less than the cost of using a more expensive model. Retry attempts beyond Attempt 1 are logged for monitoring; a high backoff rate indicates a systematic image quality problem worth surfacing to operators.

### Implementation

```python
# backend/app/services/image_processor.py

from PIL import Image
import pillow_heif  # registers HEIC handler
import io

NORMAL_MAX_PX = 1200
NORMAL_QUALITY = 85

RETRY_STEPS = [
    (2400, 90),      # Attempt 2
    (None, 92),      # Attempt 3: original (None = no resize)
]

def normalize_and_resize(image_bytes: bytes, max_long_edge: int = NORMAL_MAX_PX, quality: int = NORMAL_QUALITY) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if max_long_edge is not None:
        img.thumbnail((max_long_edge, max_long_edge), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()
```

## Consequences

- `pillow-heif` and `pdf2image` (or `pypdfium2`) are added as backend dependencies — both are pure Python / lightweight
- Preprocessing adds ~50–200ms per image (CPU-bound, acceptable within the 5s SLA budget)
- The backoff adds latency on retries (rare in practice); the retry path is logged and counted
- Token costs are predictable: normal path ≈ 1000–1500 tokens per image regardless of original file size
- Gemini Flash optimization: a separate `resize_for_gemini()` variant targeting 768px max can be used when Gemini is the active model, reducing to 1 tile (258 tokens) — configurable, not the default

## Alternatives Considered

**No preprocessing — send original:** Maximizes image fidelity but: HEIC/TIFF fail; large files (10MB+) increase latency; cost is unpredictable. Rejected.

**Compress aggressively (quality 50–60%):** Reduces cost but risks making small-font text (e.g., the warning statement at 1–2mm) unreadable. Rejected.

**Resize to Gemini single-tile (768px) by default:** Cheapest option for Gemini. Risk: 768px may be marginal for reading 1–2mm warning statement text on a full-bottle label photo. Rejected as the default; available as a tunable option.

**Use a dedicated OCR service before the LLM:** Adds a separate dependency and latency. The vision models handle extraction and compliance reasoning in one call. Rejected.
