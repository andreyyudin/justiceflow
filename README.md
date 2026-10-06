# JusticeFlow

JusticeFlow is a production-oriented, human-in-the-loop casework triage application built with synthetic data. It demonstrates how AI can support justice caseworkers with explainable queue-priority recommendations while preserving human judgement, auditability, and operational control.

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

- A production-style AI product owned across frontend, backend, database, model integration, evaluation, observability, and deployment
- Next.js 16 and React 19 for an operational caseworker interface
- FastAPI with typed request and response contracts
- Async SQLAlchemy and PostgreSQL persistence
- Alembic database migrations
- A local Ollama-compatible LLM integration
- Deterministic safeguards around probabilistic model output
- Versioned synthetic evaluation scenarios
- Structured JSON logs, request correlation IDs, and latency measurement
- Optional privacy-safe Langfuse generation tracing and quality scores
- Multi-stage, non-root Docker images
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

The reviewable Azure target maps this architecture to Azure Container Apps, Azure Container Registry, Azure Database for PostgreSQL, Key Vault, managed identity, and Log Analytics. It is validated without running a plan or applying resources to the currently authenticated organisation subscription.

## Responsible AI controls

### Human control

Every model result has `requires_human_review=true`. A recommendation does not update operational state without an explicit human decision and reviewer identity.

### Deterministic safety floors

Model output is constrained by application-owned rules:

- `hearing_deadline` always results in at least `urgent`
- accessibility, hearing-deadline, and housing-instability flags cannot be downgraded to `standard`
- a model can recommend a higher priority, but cannot bypass the fixed safety floor

### Bounded task

The model can return only one of three queue priorities. The system prompt prohibits inference about protected characteristics, guilt, offending, or legal outcomes.

### Synthetic data

All included cases and evaluation scenarios are fictional. No operational or personal justice data is included.

### Evaluation

The offline evaluation suite is deterministic and does not require a running model:

```sh
cd backend
uv run python -m evals.run
```

The suite fails unless every versioned scenario passes. It currently covers deadline escalation, accessibility and housing safeguards, routine requests, and valid high-priority recommendations.

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

Replace `POSTGRES_PASSWORD` with a long random local password. The `.env` file is ignored by Git.

### 3. Start the production-style stack

```sh
docker compose up --build
```

The migration service waits for PostgreSQL readiness and applies Alembic migrations before the API starts. The web service waits for the API health check.

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

This mode expects PostgreSQL at the configured `JUSTICEFLOW_DATABASE_URL` and Ollama at the configured `JUSTICEFLOW_OLLAMA_URL`.

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
```

Deployment configuration:

```sh
POSTGRES_PASSWORD=compose-validation-password docker compose config --quiet
```

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
- final queue recommendation and confidence
- schema-validation score
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
  app/               FastAPI, domain rules, persistence, and Langfuse observability
  evals/             Versioned synthetic evaluation scenarios
  migrations/        Alembic database migrations
  tests/             Unit and API tests
web/
  src/app/           Next.js caseworker interface
infra/               Validated AzureRM Terraform target
compose.yaml         Production-style local orchestration
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
- harden the validated Azure target with private networking and Entra ID
- deploy immutable digest-pinned images through an approved sandbox pipeline
- route privacy-safe Langfuse telemetry to the organisation's approved observability platform
- add authentication, authorisation, retention, redaction, and information-governance controls
- run user research and accessibility testing with frontline staff
- establish model and rule change approval, rollback, incident, and monitoring processes

The local implementation is not presented as ready for real justice data. It is a production-shaped technical demonstration with the important safety and operational boundaries made explicit.
