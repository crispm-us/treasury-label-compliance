# ADR-001: Vision Model Selection, Multi-Provider Strategy, and SLA

Date: 2026-06-09
Status: Accepted

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
- The `timeout` value is a tunable env var (`MODEL_TIMEOUT_SECONDS`, default `4.5`) — adjustable if a provider is consistently slow
- Prompts must be model-agnostic; no provider-specific features used
- Response parsing must handle minor output format variation (mitigated by requiring strict JSON output in the prompt)

## Alternatives Considered

**Single provider:** Simple but a single point of failure. Rejected.

**Round-robin across providers:** Distributes load but doesn't optimize for cost or latency. Rejected in favor of primary/fallback which keeps the cheapest model on the hot path.

**Build a custom retry/fallback layer:** LiteLLM already implements this well. Rejected — not invented here is fine when the library is mature and widely used.
