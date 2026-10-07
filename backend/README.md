# JusticeFlow API

The FastAPI service owns JusticeFlow domain rules, OIDC bearer-token validation, role authorization, provider-neutral model orchestration, persistence, deterministic safety-floor regression, fail-closed rejection of prohibited model rationale, structured logging, and required privacy-safe Langfuse tracing.

## Commands

```sh
uv sync
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest --cov=app --cov-report=term-missing
uv run python -m evals.run
OLLAMA_URL=http://localhost:11434 OLLAMA_MODEL=qwen3:4b uv run python -m evals.run_model
uv run alembic upgrade head --sql
```

Runtime configuration uses environment variables prefixed with `JUSTICEFLOW_`. See the repository `.env.example` for the supported deployment values.

## Authentication

Protected routes require an RS256 bearer access token. The API resolves signing keys from `JUSTICEFLOW_OIDC_JWKS_URL` and validates the configured issuer and audience before deriving exactly one caseworker or auditor role from `JUSTICEFLOW_OIDC_ROLE_CLAIM`. The claim setting supports Keycloak's nested `realm_access.roles` path and a literal top-level namespaced Auth0 claim. Reviewer names come from validated token claims rather than request JSON.

Docker Compose provides Keycloak locally so development exercises the same browser PKCE and API JWT flow used by a deployed OIDC provider. `JUSTICEFLOW_MODEL_PROVIDER` selects local Ollama or a hosted OpenAI-compatible endpoint without changing application-owned validation and safeguards.
