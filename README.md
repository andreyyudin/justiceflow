# JusticeFlow

JusticeFlow is a local-first, human-in-the-loop casework triage application built with synthetic data. It demonstrates a bounded workflow in which AI proposes a queue priority, deterministic rules enforce minimum priorities, and a named caseworker records the final decision.

Licensed under the MIT License. Contributions are welcome through focused pull requests that preserve the project's security, accessibility, and responsible-AI boundaries. See `CONTRIBUTING.md` and `SECURITY.md`.

## Why this project exists

Justice services often depend on high-volume queues, fragmented records, accessibility requirements, and time-sensitive events. JusticeFlow explores a deliberately narrow and responsible use of AI:

- summarise the evidence already present in a synthetic case
- recommend only a queue priority: `urgent`, `high`, or `standard`
- explain the evidence used for that recommendation
- apply deterministic safety floors around known operational risks
- require a named human to accept or change every recommendation
- record the final decision in an auditable database

JusticeFlow does not predict offending, guilt, legal outcomes, sentence, or individual risk. It does not infer protected characteristics. It is a casework prioritisation aid, not an automated decision-maker.

## What this demonstrates

- An end-to-end AI-assisted workflow spanning frontend, backend, database, model integration, deterministic safeguard regression, observability, and deployment configuration
- Next.js 16 and React 19 for an operational caseworker interface
- FastAPI with typed request and response contracts
- Async SQLAlchemy and PostgreSQL persistence
- Alembic database migrations
- A local Ollama-compatible LLM integration
- Deterministic safeguards around probabilistic model output
- Versioned synthetic safety-floor regression scenarios
- Structured JSON logs, request correlation IDs, and latency measurement
- Optional privacy-safe Langfuse generation tracing with operational generation metrics
- OpenID Connect Authorization Code with PKCE and signed JWT validation
- Caseworker and auditor roles with server-derived reviewer identity
- Real-browser OIDC journeys and automated WCAG A/AA accessibility scans
- Multi-stage, non-root Docker images with build-only package managers removed
- Locked dependency audits and high/critical runtime image vulnerability gates
- Health-checked Docker Compose orchestration
- Reviewable Azure infrastructure using Terraform and AzureRM
- Container Apps, ACR, Key Vault, managed identity, PostgreSQL, and Log Analytics
- Strict typing, linting, tests, coverage, and production dependency auditing

## Architecture

```text
Browser
  |
  v
Next.js casework interface
  |
  v
FastAPI application
  |                     \
  v                      v
PostgreSQL         Ollama-compatible LLM
  |
  v
Auditable human decisions
```

FastAPI owns all domain rules and AI orchestration. The browser never calls the model directly. The application sends only synthetic case data to the configured local model.

Authentication follows one production-shaped path in every environment. The browser uses OpenID Connect Authorization Code with PKCE, the API validates RS256 signatures through JWKS, and issuer, audience, expiry, subject, and role claims are mandatory. Local Docker Compose runs Keycloak as the identity provider; deployment supplies an approved OIDC authority such as Microsoft Entra ID without changing application authorization logic.

The reviewable Azure target maps this architecture to Azure Container Apps, Azure Container Registry, Azure Database for PostgreSQL, Key Vault, managed identity, and Log Analytics. It is validated without running a plan or applying resources to the currently authenticated organisation subscription.

## Responsible AI controls

### Human control

Every model result has `requires_human_review=true`. A recommendation does not update operational state without an explicit human decision and reviewer identity.

### Authentication and least privilege

The local stack runs Keycloak 26.8.0 and imports `local/keycloak/justiceflow-realm.json`. This is not an authentication bypass: the browser completes Authorization Code with PKCE and sends a bearer access token to every protected API endpoint.

Two realm roles demonstrate least privilege:

- `caseworker` can view cases, request advisory triage, and record human decisions
- `auditor` can view cases but cannot invoke triage or record decisions

Reviewer identity is derived from validated token claims and is not accepted in decision JSON. The API rejects missing, malformed, expired, wrong-issuer, wrong-audience, and invalid-role tokens.

Local synthetic users are defined in the imported realm:

- `caseworker` with password `local-caseworker-password`
- `auditor` with password `local-auditor-password`

These credentials are local development fixtures only. Production uses an approved OIDC tenant, HTTPS issuer and JWKS endpoints, managed user lifecycle, conditional access, and deployment-specific client registration.

### Deterministic safety floors

Model output is constrained by application-owned rules:

- `hearing_deadline` always results in at least `urgent`
- accessibility, hearing-deadline, and housing-instability flags cannot be downgraded to `standard`
- a model can recommend a higher priority, but cannot bypass the fixed safety floor

### Bounded task

The model can return only one of three queue priorities. The system prompt prohibits inference about protected characteristics, guilt, offending, or legal outcomes.

### Synthetic data

All included cases and safeguard scenarios are fictional. No operational or personal justice data is included.

### Deterministic safeguard regression

The offline safeguard regression is deterministic and does not require a running model:

```sh
cd backend
uv run python -m evals.run
```

Each versioned scenario supplies a synthetic case and a preselected recommendation, then verifies the priority produced by the application-owned safety floor. The command fails unless every scenario passes. It currently covers deadline escalation, accessibility and housing safeguards, routine requests, and preservation of a valid high-priority recommendation.

This suite does not invoke the configured model and is not a model-quality evaluation. It does not measure recommendation accuracy, rationale quality, evidence grounding, output-schema reliability, prompt-injection resilience, or confidence calibration. Strict output validation and grounded-evidence behaviour are covered separately by backend tests, while the real local model is exercised manually through the browser workflow.

### Browser accessibility and authentication journeys

Playwright drives the complete Docker Compose stack and signs in through the real local Keycloak Authorization Code with PKCE flow. The browser suite covers:

- the unauthenticated sign-in page
- caseworker login and access to triage controls
- auditor login and enforced read-only access
- OIDC sign-out
- automated axe-core scans against WCAG 2 A and AA rules

The accessibility gate found and fixed a queue metadata contrast defect during implementation. Automated checks complement, rather than replace, manual accessibility testing and user research.

## Run locally

### Prerequisites

- Docker with Docker Compose
- Ollama
- A machine capable of running the configured local model

The default model is `qwen3:4b`, selected as a practical compact model for a 16 GB Intel Mac. You can override it with `OLLAMA_MODEL`.

### 1. Start Ollama

```sh
ollama serve
```

In another terminal, install the configured model:

```sh
ollama pull qwen3:4b
```

### 2. Configure the application

```sh
cp .env.example .env
```

Replace `POSTGRES_PASSWORD` and `KEYCLOAK_ADMIN_PASSWORD` with long random local passwords. The `.env` file is ignored by Git. The imported caseworker and auditor accounts are synthetic local fixtures used to exercise the real OIDC flow.

### 3. Start the local production-mode stack

```sh
docker compose up --build
```

The identity service imports the local Keycloak realm and must become healthy before the API starts. The migration service waits for PostgreSQL readiness and applies Alembic migrations before the API starts. The web service waits for the API health check.

Open the caseworker interface on port 3000. The FastAPI OpenAPI documentation is available on port 8000 under `/docs`.

### 4. Stop the stack

```sh
docker compose down
```

To remove local database data as well:

```sh
docker compose down --volumes
```

## Run without Docker

Backend:

```sh
cd backend
uv sync
uv run alembic upgrade head
uv run fastapi dev main.py
```

Frontend:

```sh
cd web
npm ci
npm run dev
```

This mode expects PostgreSQL at the configured `JUSTICEFLOW_DATABASE_URL`, Ollama at `JUSTICEFLOW_OLLAMA_URL`, and an OIDC provider matching `JUSTICEFLOW_OIDC_ISSUER`, `JUSTICEFLOW_OIDC_AUDIENCE`, and `JUSTICEFLOW_OIDC_JWKS_URL`. Running Keycloak through Docker Compose while starting the API and web processes natively preserves the same authentication flow.

## Quality checks

Backend:

```sh
cd backend
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest --cov=app --cov-report=term-missing
uv run python -m evals.run
uv run alembic upgrade head --sql
```

Frontend:

```sh
cd web
npm ci
npm run lint
npm run build
npm audit --omit=dev --audit-level=high
npm run test:e2e:install
npm run test:e2e
```

The browser suite expects the complete Docker Compose stack to be running because it exercises the real Keycloak login and protected API.

Deployment and security:

```sh
POSTGRES_PASSWORD=compose-validation-password \
KEYCLOAK_ADMIN_PASSWORD=compose-validation-identity-password \
docker compose config --quiet

docker compose build api web

cd backend
uv export \
  --locked \
  --no-dev \
  --no-emit-project \
  --format requirements-txt \
  --output-file /tmp/justiceflow-requirements.txt
uvx --from pip-audit==2.10.0 pip-audit \
  --requirement /tmp/justiceflow-requirements.txt \
  --progress-spinner off
```

CI scans the built API and web runtime images with Trivy 0.72.0 and fails on fixed high or critical vulnerabilities. The runtime images remain non-root and exclude package managers that are required only while building: system pip is absent from the API image, and npm and npx are absent from the web image.

## Observability

Every HTTP response carries an `X-Request-ID`. If the caller provides one, JusticeFlow preserves it; otherwise the API generates one. Structured JSON logs include:

- request ID
- method and path
- status code
- request duration
- model name
- model latency
- recommendation
- human reviewer and outcome for recorded decisions

Logs intentionally avoid emitting case summaries or prompts.

### Langfuse LLM tracing

Langfuse tracing is optional and disabled unless both `LANGFUSE_PUBLIC_KEY` and
`LANGFUSE_SECRET_KEY` are configured. When enabled, each model request creates a
generation observation containing:

- model name and bounded inference parameters
- token usage and latency
- final queue recommendation and model-reported confidence for operational diagnosis
- failure type for unsuccessful generations
- synthetic-data and mandatory-human-review markers

Prompts, case summaries, model rationales, and evidence are deliberately excluded
from Langfuse. Regression tests inspect the telemetry calls and fail if those values
are exported.

Configure a Langfuse Cloud or self-hosted project in `.env`:

```text
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=
LANGFUSE_ENVIRONMENT=local
JUSTICEFLOW_RELEASE=development
```

Leaving either key blank keeps tracing disabled and does not affect local operation.

## Repository structure

```text
backend/
  app/               FastAPI, OIDC authorization, persistence, and observability
  evals/             Versioned deterministic safety-floor regression scenarios
  migrations/        Alembic database migrations
  tests/             Unit and API tests
web/
  src/app/           Next.js caseworker interface and OIDC PKCE client
local/keycloak/       Reproducible local identity-provider realm
infra/               Validated AzureRM Terraform target
compose.yaml         Local production-mode orchestration
```

## Azure and Terraform target

The `infra/` directory supplies a pinned and validated AzureRM deployment design for:

- Azure Container Apps hosting the FastAPI and Next.js workloads
- Azure Container Registry with managed-identity image pulls
- Azure Key Vault references for runtime secrets
- Azure Database for PostgreSQL Flexible Server
- Log Analytics-backed platform observability
- health probes and HTTP autoscaling

Validation is intentionally offline with respect to Azure resources:

```sh
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra init -backend=false
terraform -chdir=infra validate
```

No Terraform plan or apply was run against the authenticated organisation subscription. The target requires a dedicated personal sandbox, protected remote state, and the hardening steps documented in `infra/README.md` before deployment.

## Production path

The local deployment is designed to make the next production steps explicit:

- replace local Ollama with an approved, private model endpoint through the existing provider boundary
- register the existing OIDC client and API audience in the approved Entra ID tenant
- harden the validated Azure target with private networking
- deploy immutable digest-pinned images through an approved sandbox pipeline
- route privacy-safe Langfuse telemetry to the organisation's approved observability platform
- add retention, redaction, and information-governance controls
- run manual accessibility testing and user research with frontline staff
- establish model and rule change approval, rollback, incident, and monitoring processes

The local implementation is not ready for real justice data. It is a bounded technical demonstration with explicit safety and operational controls, but it still requires genuine model-quality evaluation, information-governance controls, private networking, deployment hardening, user research, and organisational approval before production use.
