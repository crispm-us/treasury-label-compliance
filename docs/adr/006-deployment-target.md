# ADR-006: Deployment Target

Date: 2026-06-09
Status: Accepted

## Context

The deliverables include a "Deployed Application URL" — a live, publicly accessible prototype. A cloud platform is required; local tunneling options (ngrok, etc.) are fragile and unsuitable for a submitted deliverable. Railway account is already set up, authenticated via the project GitHub account.

## Decision

**Railway**, connected to the project GitHub repository.

- Push to `main` → Railway auto-builds and redeploys
- API keys for all three model providers stored as Railway environment secrets (never in the repo)
- Single service: FastAPI serves both the API and the React static build
- Public URL: `https://treasury-label-compliance.up.railway.app` (or Railway-assigned subdomain)

## Consequences

- No separate frontend deployment — FastAPI mounts `frontend/dist/` as static files
- `.env.example` in the repo documents all required environment variables; Railway secrets mirror them exactly
- Free tier ($5/month credit) is sufficient for a prototype demo with light traffic
- Cold start latency possible if the service idles on the free tier; acceptable for a demo context

## Alternatives Considered

**Fly.io:** More control, globally distributed, similar cost (~$1.94/month for smallest VM after trial credit). Requires `fly.toml` configuration and `flyctl` CLI. Rejected in favor of Railway's simpler GitHub-native deploy flow for a prototype.

**Render:** Similar to Railway. Railway chosen because account was already set up.
