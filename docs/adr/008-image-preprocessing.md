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

All images are processed through a preprocessing pipeline in the backend before being sent to any model. The pipeline runs in three phases: **pre-submission validation**, **format normalization**, then **resolution targeting**.

### Phase 0: Pre-submission Validation

Before any processing, inspect the raw image file's metadata to catch inputs that cannot possibly yield a readable result. This runs on the original uploaded bytes, not on a resized copy, so the check reflects what the user actually submitted.

| Check | Threshold | Action |
|---|---|---|
| File size — minimum | < 5 KB | Reject: "Image file is too small to contain label content." |
| File size — maximum | > 20 MB | Reject: "Image file exceeds the 20 MB limit. Please resize before uploading." |
| Dimension — minimum short side | < 400 px | Reject: "Image resolution is too low ({W}×{H}). Minimum short side is 400 px." |
| Dimension — warning short side | 400–799 px | Warn in response: "Image resolution may be too low to read fine print. Results may be incomplete." Continue processing. |
| Dimension — maximum long side | > 8000 px | Pass through — backoff schedule handles downscaling. |
| Aspect ratio — extreme | > 10:1 or < 1:10 | Warn: "Unusual aspect ratio. Confirm this is a label image." Continue processing. |

**Rationale for the 400 px floor:** TTB-mandated text (Government Warning, net contents, ABV) must appear at a minimum type size of approximately 1–2 mm on the physical label. A label photo at 400 px short side represents roughly 40 DPI; 1 mm of text ≈ 1–2 px — technically below reliable OCR. In practice any submission below 400 px is either a thumbnail, a corrupt file, or a non-label image. The 800 px soft-warning threshold corresponds to ~80 DPI, which is marginal for vision-model text extraction.

**TTB COLA system image requirements (for reference):** TTB's own COLAs Online system accepts JPEG, TIFF, PNG, and GIF label images. As of mid-2026 the system does not publish minimum pixel dimensions; the practical limit is file legibility. Industry guidance notes that images should be high enough quality to print legibly at actual label size (typically 300 DPI for offset-printed labels, 150–200 DPI for inkjet proofs).

#### Implementation

```python
# backend/app/services/image_processor.py

def validate_image_metadata(image_bytes: bytes) -> tuple[bool, str | None]:
    """
    Validate image size and dimensions before any processing.
    Returns (ok, error_message). If ok is False, reject the upload.
    """
    file_size = len(image_bytes)
    if file_size < 5_000:
        return False, f"Image file is too small ({file_size} bytes). Minimum 5 KB."
    if file_size > 20 * 1024 * 1024:
        return False, f"Image file exceeds 20 MB limit ({file_size // (1024*1024)} MB)."

    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
    except Exception as exc:
        return False, f"Cannot read image file: {exc}"

    short = min(w, h)
    long  = max(w, h)

    if short < 400:
        return False, (
            f"Image resolution too low ({w}×{h} px). "
            "Minimum short side is 400 px. Please submit a higher-resolution photo."
        )

    warnings: list[str] = []
    if short < 800:
        warnings.append(
            f"Image resolution ({w}×{h} px) may be too low to read fine print reliably."
        )
    if long / short > 10:
        warnings.append(f"Unusual aspect ratio ({w}×{h}). Confirm this is a label image.")

    # Warnings are attached to the compliance result, not used to block processing.
    return True, ("\n".join(warnings) if warnings else None)
```

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

# Each tuple: (max_long_edge_px, jpeg_quality, model_override)
# model_override=None means "use whatever the ADR-001 chain selected" — current behavior.
# To activate model escalation later, add a step with a non-None model_override string.
RETRY_STEPS: list[tuple[int | None, int, str | None]] = [
    (2400, 90, None),   # Attempt 2: higher resolution, same model
    (None, 92, None),   # Attempt 3: original resolution, same model
    # Uncomment after real-label data reveals model-capability failures:
    # (1200, 85, "claude-sonnet-4-6"),  # Attempt 4: reset resolution, escalate model
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

### Complementary Backoff: Model Escalation (Deferred)

The resolution backoff above addresses image quality — it gives the model a better image to read. A separate failure mode exists: the model is simply not capable enough to extract a given label regardless of resolution (unusual typography, faded ink, non-standard layout, complex multilingual text). In those cases, giving the same model a larger image won't help.

**Alternatives for combining resolution and model escalation**

| Option | Description | Worst-case attempts | Cost per failure |
|---|---|---|---|
| A — Resolution-only (current) | 3 resolution steps, same model throughout | 3 | Low |
| B — Resolution-first, then model | Exhaust resolution steps; only then escalate model | 6 | Medium |
| C — Model-first | First retry switches model, keeps resolution | 3 | Medium (early escalation) |
| D — Parallel at Attempt 2 | Send higher-res to current model AND normal-res to next model simultaneously | — | High (concurrent calls) |
| E — Diagonal (resolution + model together) | Attempt 2: 2400px + next model; Attempt 3: original + top tier | 3 | High per retry |

**Recommendation: code the interface now, defer activation**

Option B (resolution-first-then-model) is the right long-term strategy: it keeps the common case cheap (resolution steps, inexpensive model) and only escalates model capability after the cheaper path is exhausted. However, we do not yet have real-world data showing that model-capability failures occur at a meaningful rate. Adding model escalation prematurely would increase cost on every label that needs any retry.

The `RETRY_STEPS` list above already carries a `model_override` field (defaulting to `None`). Adding model escalation later requires only uncommenting one line and adding the target model string — no architectural change. The ADR-001 fallback chain accepts a model override parameter at any retry step.

**Trigger condition to activate**: after running 50+ real labels through the system, inspect the audit log (ADR-010). If > 10% of Attempt-3 failures show a pattern the compliance checker attributes to extraction gaps rather than genuine label defects, enable Option B with `claude-sonnet-4-6` as the Attempt-4 model.

## Consequences

- Pre-submission validation (`validate_image_metadata`) runs before any model call and adds < 10 ms overhead; it produces clear rejection messages rather than cryptic model errors for unusable inputs
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
