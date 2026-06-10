"""
Audit log writer.

Appends one JSONL entry per compliance check to audit_logs/YYYY-MM-DD.jsonl.
The audit file is the primary observability artefact for the prototype — it
captures every extraction result, verdict, and any model-API failures.

Controlled by AUDIT_ENABLED (see config.py).  Set to false during unit tests
so the test suite doesn't create audit_logs/ or require filesystem write access.

Schema of each line
-------------------
{
  "request_id":            string (UUID4),
  "timestamp":             string (ISO-8601 UTC),
  "extraction_model":      string,
  "extraction_duration_ms": number,
  "model_error":           null | { "status_code": int|null, "message": string },
  "extraction_result":     null | <full ExtractionResult dict>,
  "verdict":               string,
  "beverage_class":        string | null,
  "issues": [
    { "rule_id": string, "severity": string, "field": string }
  ]
}

Production notes — model_error.status_code values
--------------------------------------------------
These are documented here but intentionally not distinguished in the prototype
because different providers use different HTTP codes and error shapes, and
multi-provider support is out of scope until after the real-label pilot.

  401  → Invalid or expired API key.
         Action: ops alert → check key rotation; do NOT retry.

  400  → Spending cap / zero balance (Anthropic-specific; message contains
         "credit balance is too low").
         Action: billing alert → add funds or raise limit; do NOT retry.
         Note: Anthropic uses 400 for this, not 402 as originally assumed.

  429  → Rate-limited.
         Action: infra → exponential back-off + request queue (see ADR-008).

  500  → Provider internal server error.
  529  → Provider overloaded (Anthropic-specific).
         Action: retry with jitter (ADR-008 retry ladder applies).

  null → Network or client-side error before HTTP response was received.
         Action: inspect message; may be a DNS/proxy issue.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from backend.app.config import AUDIT_ENABLED, AUDIT_LOG_DIR

_lock = threading.Lock()


def write_entry(entry: dict[str, Any]) -> None:
    """
    Append *entry* as one JSON line to today's audit log.

    Thread-safe.  No-op when AUDIT_ENABLED is False.
    Creates audit_logs/ on first write.
    """
    if not AUDIT_ENABLED:
        return

    AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = AUDIT_LOG_DIR / f"{date_str}.jsonl"

    line = json.dumps(entry, default=str) + "\n"
    with _lock:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
