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

NTFY_TOPIC                   Optional ntfy.sh topic for push notifications after each
                             POST /v1/check.  Leave empty (default) to disable.
                             Choose an unguessable, URL-safe string — the topic name is
                             the only access control.  See https://ntfy.sh.

Model / provider
----------------
EXTRACTION_MODEL             LiteLLM model string for Layer 1 extraction.
                             Format: "<provider>/<model-name>"
                             Default: gemini/gemini-2.5-flash-lite
                             Examples:
                               anthropic/claude-sonnet-4-6
                               anthropic/claude-haiku-4-5-20251001
                               openai/gpt-5.4-nano

EXTRACTION_FALLBACK_MODELS   Comma-separated ordered list of fallback model strings.
                             Tried in order when the primary model returns a retryable
                             error (anything except 400/401).  Leave empty to disable
                             fallback (default).
                             Three-tier default (see ADR-001):
                               anthropic/claude-haiku-4-5-20251001,openai/gpt-5.4-nano

MODEL_TIMEOUT_SECONDS        Per-call timeout passed to litellm.completion().
                             Default: 30.0 seconds.
                             Note: 4.5 s (original ADR-001 target) is not achievable for
                             vision calls with two images on Claude Haiku at P90 — observed
                             latency is 8–9 s. See docs/adr/001-vision-model-selection.md
                             and docs/latency-benchmarks.md for details.
                             Recommended minimums: 12 s (Gemini Flash-Lite), 20 s (Haiku).

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
    "EXTRACTION_MODEL", "gemini/gemini-2.5-flash-lite"
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

# ---------------------------------------------------------------------------
# Push notifications (optional — ntfy.sh)
# ---------------------------------------------------------------------------

# When set, a background notification is sent to https://ntfy.sh/<NTFY_TOPIC>
# after every POST /v1/check.  Leave empty (default) to disable.
# Choose an unguessable string — the topic name is the only access control.
NTFY_TOPIC: str = os.getenv("NTFY_TOPIC", "")

# ---------------------------------------------------------------------------
# Layer 1 schema enforcement
# ---------------------------------------------------------------------------

# When True: any schema violation (non-dict field value from the model) causes
# an ExtractionError after successful extraction, surfacing the violation as an
# ERROR verdict.  Default False — violations are logged but extraction proceeds.
# Set EXTRACTION_SCHEMA_STRICT=true in production to enforce prompt compliance.
EXTRACTION_SCHEMA_STRICT: bool = os.getenv("EXTRACTION_SCHEMA_STRICT", "false").lower() in {"true", "1", "yes"}
