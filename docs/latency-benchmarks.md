# Extraction Latency Benchmarks

Observed latency for the two core scenarios: single-panel and two-panel (front + back) extraction. All timings are end-to-end wall time from `curl` on localhost (`%{time_total}`), measured on Zulu (Apple Silicon Mac). Localhost eliminates network RTT; add ~50–200 ms for a Railway deployment depending on region.

Use `scripts/benchmark-latency.sh` to reproduce or extend.

---

## 2026-06-11 — Gemini 2.5 Flash-Lite vs. Haiku (research)

**Setup:** localhost, uvicorn single worker, `AUDIT_ENABLED=false`, no fallback chain.

### Gemini 2.5 Flash-Lite (`gemini/gemini-2.5-flash-lite`)

| Scenario | Run 1 | Run 2 | Run 3 | Avg (warm) |
|---|---|---|---|---|
| Single panel (beer) — cold batch | 2.710s | 2.199s | 2.528s | 2.479s |
| Single panel (beer) — warm batch | 1.861s | 2.315s | 1.524s | **1.900s** |
| Two panel (spirits) — cold batch | 5.082s | 4.439s | 3.940s | 4.487s |
| Two panel (spirits) — warm batch | 3.844s | 4.157s | 3.899s | **3.967s** |

Notes:
- First batch of a session shows higher latency on run 1 (connection setup, model cache cold). The warm batch is the representative steady-state number.
- Output tokens: 1,281 for the two-panel spirits call. Haiku typically produces ~400–500 for the same schema. Flash-Lite is a thinking model; the extra tokens are internal reasoning counted in output billing, not additional response text.
- Verdict: `COMPLIANT` — extraction quality confirmed correct on the Blue Ridge Rye two-panel pair.

### Claude Haiku 4.5 (`anthropic/claude-haiku-4-5-20251001`) — from latency research

Not directly measured on Zulu. Figures from provider documentation and community benchmarks (see ADR-001 §Latency note):

| Scenario | Typical | P90 |
|---|---|---|
| Single panel | 4–7s | ~7s |
| Two panel | 5–9s | 7–9s |

---

## Summary comparison

| Model | Single panel avg | Two panel avg | vs. 5s target |
|---|---|---|---|
| `gemini/gemini-2.5-flash-lite` | ~1.9s | ~4.0s | ✅ within target |
| `anthropic/claude-haiku-4-5-20251001` | ~5s (est.) | ~7–9s P90 | ❌ exceeds target |
| `openai/gpt-5.4-nano` | — | — | pending key |

Flash-Lite meets the original stakeholder target (< 5 s, see ADR-001) for two-panel calls on Haiku. Haiku did not.

---

## Running the benchmark

```bash
# Default: 3 runs, Gemini Flash-Lite + Haiku
./scripts/benchmark-latency.sh

# More runs for better statistics
./scripts/benchmark-latency.sh -n 5

# Add OpenAI once key is available
./scripts/benchmark-latency.sh -n 3 openai/gpt-5.4-nano

# All three providers
./scripts/benchmark-latency.sh -n 5 \
  gemini/gemini-2.5-flash-lite \
  anthropic/claude-haiku-4-5-20251001 \
  openai/gpt-5.4-nano
```

The script starts and stops a dedicated uvicorn instance (port 8099) for each model so runs are isolated and do not interfere with a running dev server.

---

## Latency drivers (reference)

From the ADR-001 latency research:

| Driver | Contribution |
|---|---|
| Vision encoder (per image) | ~400–600 ms |
| Image tokens (~1,280/image at 1MP JPEG) | ~30% of prefill budget |
| JSON output overhead (18-field schema) | ~60–80 extra tokens |
| Haiku TTFT | ~0.87s |
| Gemini Flash-Lite TTFT | ~1.08s |
| Decode 150 tokens at Haiku rate (89 t/s) | ~1.7s |
| Decode 150 tokens at Flash-Lite rate (233 t/s) | ~0.6s |

Optimization levers (not implemented): resize images to ≤1568px before submission, enable LiteLLM prompt caching for the system prompt, disable `LITELLM_LOG=DEBUG`.
