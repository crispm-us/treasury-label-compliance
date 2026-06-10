"""
Runtime configuration.

All tunables read from environment variables with safe defaults.

Feature flags
-------------
AUDIT_ENABLED       Set to "false" / "0" / "no" to skip audit-log writes entirely.
                    Default: true.

API_KEY             Optional bearer key for the deployed API.
                    When set, every request to POST /v1/check must supply the header:
                        X-API-Key: <value>
                    Leave unset (or empty) for local development — no auth required.
                    Set in the Railway environment dashboard before sharing the URL.

Model
-----
EXTRACTION_MODEL    Claude model string used by Layer 1.
                    Default: claude-haiku-4-5-20251001 (fastest/cheapest for prototyping).
                    Override for quality comparison: claude-sonnet-4-6

ANTHROPIC_API_KEY   Required for real extraction calls.
                    Not read during tests that use fixture JSON.
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
# Model
# ---------------------------------------------------------------------------

EXTRACTION_MODEL: str = os.getenv("EXTRACTION_MODEL", "claude-haiku-4-5-20251001")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# ---------------------------------------------------------------------------
# API authentication (optional — for Railway deployment)
# ---------------------------------------------------------------------------

API_KEY: str = os.getenv("API_KEY", "")  # empty = no auth required
