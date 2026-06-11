"""
Runtime configuration.

All tunables read from environment variables with safe defaults.

Feature flags
-------------
AUDIT_ENABLED                Set to "false" / "0" / "no" to skip audit-log writes entirely.
                             Default: true.

API_KEY                      Optional bearer key for the deployed API.
                             When set, every request to POST /v1/check must supply the header:
                                 X-API-Key: <value>
                             Leave unset (or empty) for local development — no auth required.
                             Set in the Railway environment dashboard before sharing the URL.

Model / provider
----------------
EXTRACTION_MODEL             LiteLLM model string for Layer 1 extraction.
                             Format: "<provider>/<model-name>"
                             Default: anthropic/claude-haiku-4-5-20251001
                             Examples:
                               anthropic/claude-sonnet-4-6
                               gemini/gemini-2.5-flash-lite
                               openai/gpt-5.4-nano

EXTRACTION_FALLBACK_MODELS   Comma-separated ordered list of fallback model strings.
                             Tried in order when the primary model returns a retryable
                             error (anything except 400/401).  Leave empty to disable
                             fallback (default).
                             Three-tier default (see ADR-001):
                               gemini/gemini-2.5-flash-lite,openai/gpt-5.4-nano

MODEL_TIMEOUT_SECONDS        Per-call timeout passed to litellm.completion().
                             Default: 30.0 seconds.
                             Note: 4.5 s (original ADR-001 target) is not achievable for
                             vision calls with two images on Claude Haiku at P90 — observed
                             latency is 8–9 s. See docs/adr/001-model-selection.md and the
                             latency analysis in docs/adr/010-audit-logging.md for details.
                             Recommended minimums: 20 s (Haiku), 12 s (Gemini Flash-Lite).

API keys (read by LiteLLM from the environment automatically)
--------------
ANTHROPIC_API_KEY            Required when using any anthropic/* model.
GEMINI_API_KEY               Required when using any gemini/* model.
OPENAI_API_KEY               Required when using any openai/* model.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------

AUDIT_ENABLED: bool = os.getenv("AUDIT_ENABLED", "true").lower() not in {"false", "0", "no"}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT: Path = Path(__file__).parents[2]  # backend/app/config.py → repo root
AUDIT_LOG_DIR: Path = REPO_ROOT / "audit_logs"

# ---------------------------------------------------------------------------
# Model / provider
# ---------------------------------------------------------------------------

EXTRACTION_MODEL: str = os.getenv(
    "EXTRACTION_MODEL", "anthropic/claude-haiku-4-5-20251001"
)

EXTRACTION_FALLBACK_MODELS: list[str] = [
    m.strip()
    for m in os.getenv("EXTRACTION_FALLBACK_MODELS", "").split(",")
    if m.strip()
]

MODEL_TIMEOUT_SECONDS: float = float(os.getenv("MODEL_TIMEOUT_SECONDS", "30"))

# ---------------------------------------------------------------------------
# API authentication (optional — for Railway deployment)
# ---------------------------------------------------------------------------

API_KEY: str = os.getenv("API_KEY", "")  # empty = no auth required
