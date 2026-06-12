# ADR-012: Multi-Panel Submission — Two-Panel Design and N-Panel Extension Path

**Status:** Deferred (two-panel built; N-panel design assessed, not implemented)
**Date:** 2026-06-11
**Deciders:** Cris Pedregal Martin

---

## Context

The current API accepts two named image slots: `front` (required) and optional `back`. This covers the dominant label submission pattern — a two-face bottle or a flat manufacturer-supplied label sheet — and was the correct scope for the prototype.

Real-label testing surfaced a concrete gap: cylindrical cans with three distinct printed panels. The Henninger Lager and Delirium Tremens can test images both illustrate this case. The brand face, the importer/info face, and the Government Warning Statement face are separated by the geometry of the cylinder. A two-panel submission must choose two of three faces; the omitted face yields `not_found` results for fields it exclusively carries, producing UNVERIFIABLE rather than a complete verdict.

This ADR records the design analysis for extending to three or more panels. No implementation decision has been made; this documents what was assessed, what the tradeoffs are, and what the implementation path would look like if the decision is taken.

---

## What the current two-panel design relies on

Before assessing extension, the load-bearing properties of the current design:

1. **Named slots are semantic, not geometric.** `front` and `back` do not mean "physical front face" and "physical back face" — they are submission hints. The merge is panel-order-agnostic; swapped panels produce correct results.

2. **Merge by highest confidence is associative.** For each field, the value with the highest confidence wins. `high > low > not_found`. This operation is commutative and associative, which means it naturally extends to N inputs via reduce.

3. **`panels_provided` is already a list.** The extraction schema records which panels were submitted as `list[string]`. No schema change needed for this field.

4. **Receipt fields are named per panel.** `front_filename`, `front_label_ref`, `front_sha256`, `back_filename`, `back_label_ref`, `back_sha256` are explicit fields in `CheckResponse` and the audit log. These are the most structurally coupled artifacts.

---

## Decision dimensions

### 1. API input shape

**Option A — Add a named `side` slot.**
Extend `POST /v1/check` with an optional third multipart field alongside `front` and `back`. Handles the Henninger/Delirium Tremens use case directly. No breaking change to existing callers.

Downsides: arbitrary name (`side`? `panel3`?); does not generalize beyond three; still a flat, ad-hoc naming scheme.

**Option B — Replace with list-based `panels[]`.**
Accept `panels[]` as a repeated multipart field. One required, up to N (suggest cap at 4 or 5). Panel identity comes from the filename or an optional `panel_hint[]` parallel field.

Cleaner for N > 3. Breaking API change. Callers currently using `-F "front=@..."` must update to `-F "panels[]=@..."`.

**Recommendation:** Option A for any near-term extension (avoids a breaking change); Option B if this goes to a versioned v2 API.

---

### 2. Extraction — already panel-agnostic

`_extract_single()` operates on one image and returns one `ExtractionResult`. It does not need to change. Three panels = three calls to `_extract_single`.

---

### 3. Merge — generalize the fold

Current signature:

```python
def _merge_panels(front: ExtractionResult, back: ExtractionResult) -> ExtractionResult:
```

Generalized:

```python
def _merge_panels(panels: list[ExtractionResult]) -> ExtractionResult:
    result = panels[0]
    for panel in panels[1:]:
        result = _merge_two(result, panel)
    return result
```

Where `_merge_two` is the existing field-by-field highest-confidence logic, extracted into its own function. The merge algorithm is unchanged; only the call structure changes. This is a low-risk refactor.

---

### 4. Latency — the hard constraint

This is the most significant architectural consequence.

Timings (Gemini Flash-Lite, warm):

| Panels | Sequential | Parallel | Notes |
|---|---|---|---|
| 1 | ~2.5 s | ~2.5 s | Parallel N/A for single panel |
| 2 | ~5.1 s | **~2.2 s** | ✅ Implemented (ThreadPoolExecutor) |
| 3 | ~7.5 s | ~3.5 s (est.) | Not yet implemented |

**Two-panel parallel extraction is implemented** as of 2026-06-12 via `ThreadPoolExecutor(max_workers=2)` inside the sync `extract()` function, with `asyncio.to_thread()` in `main.py` to avoid blocking the event loop. This achieves a 57% latency reduction (5.1s → 2.2s) for two-panel requests.

Three sequential model calls exceed the 5 s SLA with no margin. Parallel extraction is required for three-panel support too.

**Parallel extraction path for N-panel (not yet implemented):**

```python
import asyncio

async def extract_all(images: list[...]) -> list[ExtractionResult]:
    tasks = [extract_single_async(img) for img in images]
    return await asyncio.gather(*tasks)
```

The correct upgrade from the current `ThreadPoolExecutor` bridge is full async using `litellm.acompletion` + `asyncio.gather` — do not layer another thread pool on top. `_extract_single` becomes async; the fallback chain inside becomes an async retry loop. `main.py` already uses `async def` and the `asyncio.to_thread()` wrapper is removed once the function is natively async.

Estimated parallel latency for three panels: ~3.5 s (dominated by slowest panel, plus minor scheduling overhead). Within SLA.

**Key point:** parallel extraction is not optional if three-panel support is to be meaningful. The two-panel implementation validates the approach; N-panel extends it.

---

### 5. Receipt fields — two options

**Option A (named, parallel to API input):** Add `side_filename`, `side_label_ref`, `side_sha256` to `CheckResponse` and the audit log. Consistent with the named-slot API approach. Simple; no schema restructuring.

**Option B (list):** Replace the six named fields with:

```json
"panels": [
  {"slot": "front", "filename": "...", "label_ref": "...", "sha256": "..."},
  {"slot": "back",  "filename": "...", "label_ref": "...", "sha256": "..."}
]
```

Scales to N panels. Breaking change to API response schema and audit log format.

Recommendation: Option A if the API input stays named; Option B only as part of a coordinated v2 API redesign.

---

## What is not affected

- The compliance checker (`compliance_checker.py`) operates on a single merged `ExtractionResult`. It has no knowledge of how many panels were submitted. **No changes needed.**
- Extraction fixtures and unit tests for the checker are unaffected.
- The extraction prompt is per-panel and does not need to change.
- `panels_provided` in `ExtractionResult` already accepts a list of strings.

---

## Summary of impact by component

| Component | Impact | Notes |
|---|---|---|
| `POST /v1/check` input | Low–Medium | Add `side` (Option A) or redesign as `panels[]` (Option B) |
| `_extract_single` | Low | Already panel-agnostic; make async for parallel execution |
| `_merge_panels` | Low | Refactor to fold over list; algorithm unchanged |
| `extractor.py` async | Medium | `litellm.acompletion`, async retry loop — required for SLA |
| `main.py` | Medium | Async gather over panels; receipt computation per panel |
| `CheckResponse` receipt fields | Low–Medium | Add named fields (Option A) or refactor to list (Option B) |
| Audit log | Low–Medium | Same choice as receipt fields |
| `compliance_checker.py` | None | Operates on merged result; unaffected |
| Extraction prompt | None | Per-panel; no change |
| Unit tests (checker) | None | Unaffected |
| Integration tests (`test_api.py`) | Medium | New fields; parallel mock pattern |

---

## Motivating test cases

- `test-labels/beer/henninger-front.jpg` + `test-labels/beer/henninger-gws.jpg`: importer info on a third face not submitted → UNVERIFIABLE
- `test-labels/beer/delirium-tremens-can-front.jpg` + `test-labels/beer/delirium-tremens-can-gws.jpg`: ABV and net contents on a separate side panel

Both cases currently yield UNVERIFIABLE (not false NONCOMPLIANT) — the two-panel design handles them gracefully, just incompletely. Three-panel support would allow full verdicts on these labels.

---

## Decision

**Not implemented in this prototype.** The two-panel design is sufficient for manufacturer-supplied flat images (the primary production use case) and handles two-face bottle photographs correctly. Three-panel support is well-motivated by real-label edge cases but introduces non-trivial latency complexity (async extraction) and API/schema changes that are out of scope for this prototype phase.

If taken up: implement parallel extraction first (latency gate), then extend the API under a coordinated Option A or Option B choice. The merge and checker layers require minimal changes.
