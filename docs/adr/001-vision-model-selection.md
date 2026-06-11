# ADR-001: Vision Model Selection, Multi-Provider Strategy, and SLA

Date: 2026-06-09
Updated: 2026-06-10
Status: Accepted (SLA target revised — see §Latency note below)

## Context

The core function of this system is reading alcohol label images and extracting structured fields. This requires a vision-capable LLM. The hard latency constraint from stakeholder interviews is **< 5 seconds per label** (Sarah Chen: "If we can't get results back in about 5 seconds, nobody's going to use it").

Two additional constraints shape this decision:

1. **Availability:** The app must remain operational if any single provider is unavailable. A single-provider design is a single point of failure unacceptable for a compliance tool.
2. **Cost:** The default path must be fast and cheap. Occasional failover to a better/more expensive model is acceptable; the weighted average cost across all requests must remain close to the cheapest tier.

We have valid API keys for: Anthropic, OpenAI, Google, and OpenRouter.

## Decision

### Provider tier structure

Three providers are wired in, forming a priority-ordered fallback chain:

| Tier | Model | Provider | Role |
|---|---|---|---|
| Primary | `gemini/gemini-2.0-flash` | Google | Default for all requests — fast, cheap, strong vision |
| Fallback-1 | `claude-haiku-4-5-20251001` | Anthropic | First failover — still cheap, very fast |
| Fallback-2 | `claude-sonnet-4-6` | Anthropic | Second failover — higher quality, higher cost |

A third provider (OpenAI `gpt-4o`) is configured as a fourth-tier fallback for extreme availability scenarios but is not expected to activate in normal operation.

### Fallback mechanics

The LiteLLM Python library handles the fallback chain natively:

```python
response = litellm.completion(
    model="gemini/gemini-2.0-flash",
    messages=[...],
    fallbacks=[
        {"model": "claude-haiku-4-5-20251001"},
        {"model": "claude-sonnet-4-6"},
        {"model": "gpt-4o"},
    ],
    timeout=4.5,          # hard cutoff; leaves 0.5s for network/UI overhead
    num_retries=1,        # retry primary once before falling back
)
```

If the primary model exceeds `timeout` or returns an error, LiteLLM automatically tries the next tier. No application logic changes required.

### SLA target

**95th percentile end-to-end latency < 5 seconds** for the prototype.

- `timeout=4.5s` on the model call reserves 0.5s for HTTP overhead, image preprocessing, and compliance logic
- Gemini Flash and Claude Haiku both typically respond in 1–3 seconds for structured extraction tasks
- A fallback invocation adds one round-trip latency; this is acceptable if it occurs in < 5% of requests
- The SLA is monitored via response time logging in the API; no external APM required for the prototype

### Cost profile

Expected distribution under normal operation: ~95% primary (Gemini Flash), ~4% Fallback-1 (Haiku), ~1% Fallback-2+ (Sonnet/GPT-4o). The weighted average cost remains close to Gemini Flash pricing.

## Consequences

- All three Anthropic, Google, and OpenAI API keys must be present as environment secrets in Railway
- If a provider has a sustained outage, the next tier absorbs the traffic automatically — no operator intervention needed
- The `timeout` value is a tunable env var (`MODEL_TIMEOUT_SECONDS`, default `30.0`) — see §Latency note for rationale
- Prompts must be model-agnostic; no provider-specific features used
- Response parsing must handle minor output format variation (mitigated by requiring strict JSON output in the prompt)

## Latency note (updated 2026-06-10)

The 4.5 s timeout target and "1–3 seconds" estimate in this ADR reflect text-only benchmarks. Vision calls with two label images are materially slower.

Observed (two-image submissions in testing): 5–9 s on Haiku; 3–5 s on Gemini Flash-Lite. The P90 for a Haiku two-image call is 7–9 s. The 4.5 s target is **not achievable** as a default for two-image Haiku calls.

**Root causes:** vision encoder overhead (~400–600 ms per image), image token count (~1,280 tokens per 1MP JPEG filling ~30% of the prefill budget), and JSON output token overhead (~60–80 extra tokens for the 18-field schema. TTFT for Haiku is ~0.87 s; decode 150 output tokens at ~89 t/s adds ~1.7 s; total including vision encoder is 4–9 s.

**Revised guidance:**
- `MODEL_TIMEOUT_SECONDS` default is now **30 s** (safe P99 guard for two-image Haiku)
- Recommended minimums: 20 s (Haiku), 12 s (Gemini Flash-Lite)
- The 4.5 s target is achievable only with a single image, Gemini Flash-Lite, warm prompt cache, and pre-resized images — not as a general default

**Optimizations available (not implemented):** resize to ≤1568px before submission (reduces token count and prefill time), enable LiteLLM prompt caching for the system prompt (saves ~500 ms on cache hit), disable `LITELLM_LOG=DEBUG` in production (adds measurable overhead).

The stakeholder's "5 seconds" intuition (Sarah Chen) aligns with single-image text-heavy labels. Two-image compliance checks require a wider default window. The `MODEL_TIMEOUT_SECONDS` env var allows operators to tighten the budget if their workload and provider mix support it.

---

## Alternatives Considered

**Single provider:** Simple but a single point of failure. Rejected.

**Round-robin across providers:** Distributes load but doesn't optimize for cost or latency. Rejected in favor of primary/fallback which keeps the cheapest model on the hot path.

**Build a custom retry/fallback layer:** LiteLLM already implements this well. Rejected — not invented here is fine when the library is mature and widely used.
