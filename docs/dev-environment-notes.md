# Dev Environment Notes

**Status: ARCHIVE BEFORE SUBMISSION — internal context only, not relevant to evaluators**

---

This document collects references to the developer's personal infrastructure that informed architectural decisions but play no role in the deployed product. It exists so those decisions can be understood in context; it should be removed from the repository before the work is submitted.

---

## ubu-west

`ubu-west` is a personal home server (Intel NUC running Ubuntu, codenamed "claw server") on the developer's local network. It is a Tailscale-only machine — completely closed to the public internet, accessible only to devices on the developer's private Tailscale network (`tail032f87.ts.net`).

ubu-west hosts a production LiteLLM proxy server (`localhost:4000`) configured with API keys for Anthropic (two accounts), OpenAI, Google Gemini, DeepSeek, and OpenRouter. This installation is part of an unrelated project (HardClaw) and is not deployable as part of this application.

### Why it was discussed

The LiteLLM proxy on ubu-west is directly accessible from the developer's MacBook (Zulu) via Tailscale. During early planning, it was noted as a potential dev convenience — the developer could route model calls through it during local development sessions to avoid configuring API keys directly on Zulu. This was ultimately assessed as an unnecessary intermediate step: the LiteLLM Python library achieves the same abstraction with API keys sourced from a local `.env` file, and ubu-west's proxy plays no role in the deployed app.

### What replaced it

All model abstraction is handled by the LiteLLM Python library inside the app (see ADR-002). API keys are stored in `.env` locally and as Railway environment secrets in production. No external proxy or sidecar service is needed.

### What is reused

The same provider API keys available on ubu-west (Anthropic, OpenAI, Google) are used for this project, stored independently in the project's own `.env` and Railway secrets. No configuration files from HardClaw or ubu-west are included in this repository.

---

## Zulu

`Zulu` is the developer's MacBook Pro M4, used as the primary development machine. All source code is written here using Cursor. The name is referenced in git config and SSH key comments but has no significance to the application architecture.

---

## Tailscale

Tailscale is a WireGuard-based VPN mesh used to connect the developer's personal devices. It is mentioned in planning documents solely as the reason ubu-west has no public IP. Tailscale plays no role in the deployed application.
