# Extraction Latency Benchmarks

Observed latency for the two core scenarios: single-panel and two-panel (front + back) extraction. All timings are end-to-end wall time from `curl` on localhost (`%{time_total}`), measured on Zulu (Apple Silicon Mac). Localhost eliminates network RTT; add ~50–200 ms for a Railway deployment depending on region.

Use `scripts/benchmark-latency.sh` to reproduce or extend.

---

## 2026-06-11 — Initial Flash-Lite measurement (pre-benchmark-script)

**Setup:** localhost, uvicorn single worker, manual curl batches. First batch is cold; second is warm.

### Gemini 2.5 Flash-Lite — cold vs. warm

| Scenario | Run 1 | Run 2 | Run 3 | Avg |
|---|---|---|---|---|
| Single panel (beer) — cold | 2.710s | 2.199s | 2.528s | 2.479s |
| Single panel (beer) — warm | 1.861s | 2.315s | 1.524s | **1.900s** |
| Two panel (spirits) — cold | 5.082s | 4.439s | 3.940s | 4.487s |
| Two panel (spirits) — warm | 3.844s | 4.157s | 3.899s | **3.967s** |

---

## 2026-06-11 — Three-provider benchmark (`scripts/benchmark-latency.sh -n 3`)

**Setup:** localhost, uvicorn single worker, `AUDIT_ENABLED=false`, no fallback chain, 1 warm-up request per scenario before timed runs.

### Results

| Model | Single panel avg | Two panel avg | Notes |
|---|---|---|---|
| `gemini/gemini-2.5-flash-lite` | **2.550s** | **5.111s** ⚠ | 1 HTTP 500 on two-panel run 3 (excluded from avg) |
| `anthropic/claude-haiku-4-5-20251001` | 3.773s | 7.748s | Consistent; no errors |
| `openai/gpt-5.4-nano` | 4.054s | 11.823s | High variance (8.9–16.2s); quality regression (see below) |

### Raw timings

**gemini/gemini-2.5-flash-lite**

| Scenario | Run 1 | Run 2 | Run 3 | Avg | Tokens (in+out) |
|---|---|---|---|---|---|
| Single panel | 2.598s | 2.581s | 2.471s | 2.550s | 1429+609 |
| Two panel | 5.226s | 4.995s | ✗ 500 | 5.111s | 2858+~1290 |

**anthropic/claude-haiku-4-5-20251001**

| Scenario | Run 1 | Run 2 | Run 3 | Avg | Tokens (in+out) |
|---|---|---|---|---|---|
| Single panel | 3.120s | 4.142s | 4.057s | 3.773s | 2634+~619 |
| Two panel | 7.846s | 7.761s | 7.635s | 7.748s | 5268+~1261 |

**openai/gpt-5.4-nano**

| Scenario | Run 1 | Run 2 | Run 3 | Avg | Tokens (in+out) |
|---|---|---|---|---|---|
| Single panel | 4.202s | 3.551s | 4.409s | 4.054s | 2405+~500 |
| Two panel | 10.398s | 16.156s | 8.915s | 11.823s | 4810+~1073 |

### Quality observations

- **Flash-Lite and Haiku** both returned `NONCOMPLIANT` on the single-panel beer front — correct (GWS is on the back panel, not submitted).
- **gpt-5.4-nano** returned `UNVERIFIABLE` on all three single-panel runs. This is a quality regression: the label is readable, and the expected verdict is `NONCOMPLIANT`. Nano appears to be marking the GWS fields as `not_found` rather than `gws_present=false`, which produces UNVERIFIABLE instead of NONCOMPLIANT. The extraction prompt was developed against Flash-Lite and Haiku; nano may require prompt tuning.
- **Flash-Lite HTTP 500** on two-panel run 3: transient API error. The fallback chain (Haiku) would handle this in production. Not seen on any other run.

### Input token comparison

Flash-Lite encodes the same image at significantly fewer input tokens than Haiku (1,429 vs 2,634 for a single panel). This contributes to Flash-Lite's latency advantage beyond raw decode speed.

---

## Summary comparison

| Model | Single panel | Two panel | Quality | vs. 5s target |
|---|---|---|---|---|
| `gemini/gemini-2.5-flash-lite` | 2.55s | 5.11s | ✅ Correct verdicts | ✅ Single; ⚠ Two-panel borderline |
| `anthropic/claude-haiku-4-5-20251001` | 3.77s | 7.75s | ✅ Correct verdicts | ❌ Two-panel exceeds |
| `openai/gpt-5.4-nano` | 4.05s | 11.82s | ⚠ Quality regression | ❌ Both exceed |

Flash-Lite is the clear primary choice. Haiku is the correct fallback-1 (reliable, correct). gpt-5.4-nano is not recommended as fallback without prompt tuning — quality regression outweighs cost savings.

---

## Running the benchmark

Each model gets its own isolated uvicorn instance (port 8099). Before each scenario, the script sends one untimed warm-up request to prime the provider connection and any server-side caches. The `-n N` runs that follow are the timed measurements. So `-n 3` means 4 total API calls per scenario: 1 warm-up + 3 timed. Averages exclude non-200 responses and `verdict=ERROR` runs.

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
