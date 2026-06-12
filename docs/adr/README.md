# Architecture Decision Records

One ADR per significant design decision. Read them for rationale and context. For what is actually built, see `../../IMPLEMENTATION_STATUS.md` — several decisions here were accepted but not implemented in the prototype.

## Status legend

| Icon | Meaning |
|---|---|
| ✅ Built | Decision and implementation align |
| ⚠ Partial | Core decision implemented; some aspects deferred — see ADR body |
| ❌ Not built | Decision accepted but not implemented in this prototype |

## Index

| # | Title | Implementation |
|---|---|---|
| [001](001-vision-model-selection.md) | Vision model selection, multi-provider strategy, SLA | ⚠ Partial — primary model is `gemini/gemini-2.5-flash-lite` (not original `gemini-2.0-flash`); fallback is manual iteration in `extractor.py`, not LiteLLM-native `fallbacks=`; SLA revised to 30 s default |
| [002](002-litellm-library-vs-proxy.md) | LiteLLM Python library as model abstraction layer | ⚠ Partial — library used; but fallback via manual model iteration in `extractor.py`, not `litellm.completion(fallbacks=[...])` as designed |
| [003](003-dual-mode-input.md) | Dual-mode input (extract / verify) | ⚠ Partial — see `application_checker.py` and `test-labels/applications/`; file-based application JSON on `POST /v1/check`; COLA integration deferred |
| [004](004-backend-framework.md) | Backend framework (FastAPI) | ✅ Built |
| [005](005-frontend-framework.md) | Frontend framework (React + Vite + Tailwind) | ⚠ Partial — React + Vite + Tailwind v4 UI built and served from FastAPI; drag-and-drop panel upload, compliance result display, duration/version/clear implemented; base64 JSON endpoint and mobile layout deferred |
| [006](006-deployment-target.md) | Deployment target (Railway) | ✅ Built |
| [007](007-batch-processing-design.md) | Batch processing design | ❌ Not built — single label per request; batch endpoint deferred |
| [008](008-image-preprocessing.md) | Image preprocessing and format handling | ⚠ Partial — magic-byte format validation, 10 MB size limit, and EXIF orientation correction (Pillow `exif_transpose`) implemented; HEIC conversion and resolution normalization deferred |
| [009](009-two-layer-architecture.md) | Two-layer architecture: AI extraction + deterministic compliance | ✅ Built |
| [010](010-audit-logging.md) | Audit logging | ⚠ Partial — JSONL audit log implemented; sensitivity-tier enforcement (Level A/B/C) from original design not implemented — see ADR-010 body |
| [011](011-extraction-schema.md) | Extraction JSON schema (18-field ExtractionResult) | ✅ Built |
| [012](012-multi-panel-submission.md) | Multi-panel submission — two-panel design and N-panel extension path | ⚠ Partial — two-panel submission and parallel extraction (ThreadPoolExecutor) implemented; three-panel extension assessed and deferred; see ADR body |
