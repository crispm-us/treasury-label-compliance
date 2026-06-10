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
                               gemini/gemini-1.5-flash
                               openai/gpt-4o

EXTRACTION_FALLBACK_MODELS   Comma-separated ordered list of fallback model strings.
                             Tried in order when the primary model returns a retryable
                             error (anything except 400/401).  Leave empty to disable
                             fallback (default).
                             Example: gemini/gemini-1.5-flash,openai/gpt-4o

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

# ---------------------------------------------------------------------------
# API authentication (optional — for Railway deployment)
# ---------------------------------------------------------------------------

API_KEY: str = os.getenv("API_KEY", "")  # empty = no auth required
