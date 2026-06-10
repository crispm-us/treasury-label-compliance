# ADR-004: Backend Framework

Date: 2026-06-09
Status: Accepted

## Context

The backend needs to: accept image uploads, call a vision model API, run compliance logic, and return structured results. It must run in a Docker container on Railway.

## Decision

**Python 3.12 + FastAPI**, with `uv` for package management.

Key reasons:
- Python has first-class support in every LLM SDK and in litellm
- FastAPI is async-native (important for non-blocking model API calls), generates OpenAPI docs automatically, and has Pydantic validation built in
- `uv` is dramatically faster than pip for dependency resolution and installs — relevant for Docker build times on Railway

## Consequences

- Docker image uses `python:3.12-slim` base; `uv` handles the venv
- All request/response shapes defined as Pydantic models — serves as living schema documentation
- Async route handlers (`async def`) throughout; no blocking I/O on the main thread

## Alternatives Considered

**Flask:** Simpler but synchronous by default. Async support requires additional work. No built-in validation. Rejected.

**Django:** Too heavy for a single-purpose API. Rejected.

**Node.js / TypeScript:** Would share a language with the frontend, but Python's LLM ecosystem is substantially richer. Rejected.
