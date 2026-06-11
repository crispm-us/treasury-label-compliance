# ADR-002: LiteLLM Python Library as Model Abstraction Layer

Date: 2026-06-09
Status: Accepted

## Context

LiteLLM exists in two forms: a Python library (`pip install litellm`) and a self-hosted proxy server. The proxy form provides a unified HTTP endpoint, spend tracking, rate limiting, and a dashboard, but requires a running server process. The library form provides the same unified call interface as a pure Python dependency.

The app requires: multi-provider fallback (see ADR-001), a single call interface regardless of provider, and the ability to run on a public cloud platform with no sidecar services.

## Decision

Use the **LiteLLM Python library** as the sole model abstraction layer. No separate process, no HTTP hop, no infrastructure.

> **Implementation note:** The fallback chain is implemented via manual model iteration in `backend/app/services/extractor.py` rather than the `litellm.completion(fallbacks=[...])` parameter. This divergence was chosen to gain explicit per-error-code control: 400/401 errors (bad key, bad request) stop the chain immediately; 5xx and timeouts try the next model. The `EXTRACTION_FALLBACK_MODELS` env var holds a comma-separated ordered list. All model configuration remains in environment variables — no code changes needed to adjust the chain.

Original design called for using `litellm.completion` library parameters directly:

```python
# backend/app/services/model_client.py
import litellm

def call_vision_model(image_b64: str, prompt: str) -> str:
    response = litellm.completion(
        model=settings.PRIMARY_MODEL,
        messages=[...],
        fallbacks=settings.FALLBACK_MODELS,
        timeout=settings.MODEL_TIMEOUT_SECONDS,
        max_tokens=settings.MAX_TOKENS,
    )
    return response.choices[0].message.content
```

## Consequences

- One `pip install litellm` dependency; no infrastructure to operate
- The fallback chain (ADR-001) works out of the box — library handles retry, timeout, and provider switching
- No built-in spend dashboard or rate limiting (mitigated by: cheap primary model, `max_tokens` cap, and a simple IP rate limiter in FastAPI — see requirements-analysis.md NFR-04)
- All provider API keys must be present as environment variables in the deployment environment

## Alternatives Considered

**Self-hosted LiteLLM proxy:** This is the right architecture for a production system. The proxy provides spend tracking, per-user rate limiting, a dashboard, virtual keys (so application code never holds real provider credentials), and centralized model routing that can be updated without redeploying the app. For a prototype, however, standing up and operating the proxy server is unnecessary overhead — the Python library already delivers the architectural abstraction (single call interface, multi-provider fallback, model selection via config) that a production redesign would preserve. The transition from library to proxy in a production version would be a configuration change, not a code rewrite: `litellm.completion()` calls would point at the proxy's OpenAI-compatible endpoint rather than calling providers directly, and the application code would be unchanged.

**Use provider SDKs directly (anthropic, openai, google-generativeai):** Each has a different call interface. Implementing fallback across three SDKs would require custom logic. Rejected — LiteLLM already solves this cleanly.
