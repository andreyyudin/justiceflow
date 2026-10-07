# JusticeFlow free-tier deployment

This deployment runs the public portfolio demonstration across managed free tiers:

- Vercel Hobby hosts the Next.js interface.
- Render Free hosts the FastAPI container.
- Neon Free provides PostgreSQL.
- Auth0 Free provides OpenID Connect Authorization Code with PKCE.
- Groq Free provides an OpenAI-compatible model endpoint.
- Langfuse Cloud Hobby provides required privacy-safe model telemetry.

Local Docker Compose remains the reference local environment and continues to use Keycloak, PostgreSQL, Ollama, and self-hosted Langfuse.

## Scope and limitations

This deployment is for synthetic portfolio data only. It is not approved for real justice, personal, customer, or employer data.

Free services can sleep, throttle, change quotas, or take longer on their first request. Treat this as a demonstration environment, not a production service-level commitment.

Do not commit provider credentials. Enter secrets only in the relevant provider dashboard.

## Architecture

```text
Browser
  |
  v
Vercel: Next.js
  |
  +----> Auth0: OIDC Authorization Code with PKCE
  |
  v
Render: FastAPI
  |
  +----> Neon: PostgreSQL
  +----> Groq: OpenAI-compatible model inference
  +----> Langfuse Cloud: privacy-safe generation telemetry
```

FastAPI remains responsible for:

- signed JWT validation through the configured JWKS endpoint
- issuer and audience validation
- exact-one-role authorization
- model request construction
- strict model response validation
- prohibited-rationale rejection
- deterministic priority safety floors
- recommendation and human-decision persistence
- privacy-safe telemetry

## Prerequisites

Create personal free accounts for:

1. Neon
2. Auth0
3. Groq
4. Langfuse Cloud
5. Render
6. Vercel

Connect Render and Vercel to the `andreyyudin/justiceflow` GitHub repository.

## 1. Create the Neon database

Create a Neon project and database for JusticeFlow.

Copy the pooled PostgreSQL connection string. Convert its scheme for the async SQLAlchemy driver:

```text
postgresql://...        -> postgresql+asyncpg://...
postgres://...          -> postgresql+asyncpg://...
```

Preserve the hostname, username, password, database, and query parameters supplied by Neon. The backend normalizes Neon's libpq-style `sslmode` and `channel_binding` parameters for the asyncpg driver before application or migration connections are opened.

Store the converted value for the Render variable:

```text
JUSTICEFLOW_DATABASE_URL
```

The backend container entrypoint applies all Alembic migrations before starting the API. This is required because Render Free does not support pre-deploy commands. Alembic upgrades are idempotent, so restarts safely verify the database is at the current migration head before FastAPI starts.

## 2. Configure Auth0

### Create the API

Create an Auth0 API with:

```text
Name: JusticeFlow API
Identifier: https://justiceflow-api
Signing algorithm: RS256
```

The identifier becomes the access-token audience.

### Create the browser application

Create a Single Page Application for JusticeFlow.

After Vercel assigns the production URL, configure these Auth0 application settings:

```text
Allowed Callback URLs:
https://YOUR-VERCEL-DOMAIN/

Allowed Logout URLs:
https://YOUR-VERCEL-DOMAIN/

Allowed Web Origins:
https://YOUR-VERCEL-DOMAIN
```

The frontend derives its callback and logout redirect from `window.location.origin`.

### Add the role Action

Create an Auth0 Post Login Action and copy the repository file:

```text
deployment/auth0-post-login.js
```

Deploy the Action and add it to the Login flow.

The Action reads one protected application-metadata field:

```json
{
  "justiceflow_role": "caseworker"
}
```

The only accepted values are:

```text
caseworker
auditor
```

The Action denies login when the role is absent or invalid. It emits the approved role as a one-element array in this access-token claim:

```text
https://justiceflow.example/roles
```

Do not store this authorization role in editable user metadata.

### Create demonstration users

Create two synthetic users. Set their `app_metadata` separately:

Caseworker:

```json
{
  "justiceflow_role": "caseworker"
}
```

Auditor:

```json
{
  "justiceflow_role": "auditor"
}
```

Use synthetic names and personal demonstration credentials only.

### Record Auth0 values

Record:

```text
AUTH0_DOMAIN
AUTH0_CLIENT_ID
```

Derive these API settings:

```text
JUSTICEFLOW_OIDC_ISSUER=https://AUTH0_DOMAIN/
JUSTICEFLOW_OIDC_AUDIENCE=https://justiceflow-api
JUSTICEFLOW_OIDC_JWKS_URL=https://AUTH0_DOMAIN/.well-known/jwks.json
JUSTICEFLOW_OIDC_ROLE_CLAIM=https://justiceflow.example/roles
```

The issuer must retain its trailing slash because JWT issuer comparison is exact.

## 3. Configure Groq

Create a Groq API key.

Choose a current chat-completions model that supports JSON response mode. Store its exact model identifier for:

```text
JUSTICEFLOW_MODEL_NAME
```

The repository does not hard-code a hosted model identifier because provider catalogues and free-tier availability can change.

The hosted API settings are:

```text
JUSTICEFLOW_MODEL_PROVIDER=openai-compatible
JUSTICEFLOW_MODEL_BASE_URL=https://api.groq.com/openai/v1
JUSTICEFLOW_MODEL_NAME=YOUR-GROQ-MODEL
JUSTICEFLOW_MODEL_API_KEY=YOUR-GROQ-API-KEY
JUSTICEFLOW_MODEL_TIMEOUT_SECONDS=120
```

JusticeFlow sends only synthetic case data. The application still treats every case field as untrusted data, validates the returned JSON strictly, rejects prohibited rationale, and applies deterministic safety floors.

Run the opt-in model evaluation against the chosen hosted model before describing it as suitable. A provider connection alone is not evidence of model quality.

## 4. Configure Langfuse Cloud

Create a Langfuse Cloud project and copy its public and secret project keys.

Use the base URL shown for the selected Langfuse Cloud region. Record:

```text
JUSTICEFLOW_LANGFUSE_PUBLIC_KEY
JUSTICEFLOW_LANGFUSE_SECRET_KEY
JUSTICEFLOW_LANGFUSE_BASE_URL
```

JusticeFlow deliberately excludes prompts, case summaries, rationales, and rendered evidence from telemetry. It exports operational model metadata, token counts, latency, final recommendation, confidence, and failure type.

## 5. Create the Render API

In Render, create a Blueprint from the repository root. Render will discover:

```text
render.yaml
```

The Blueprint creates one free Docker web service named `justiceflow-api`.

Enter every variable marked `sync: false`:

```text
JUSTICEFLOW_DATABASE_URL
JUSTICEFLOW_MODEL_NAME
JUSTICEFLOW_MODEL_API_KEY
JUSTICEFLOW_ALLOWED_ORIGINS
JUSTICEFLOW_LANGFUSE_PUBLIC_KEY
JUSTICEFLOW_LANGFUSE_SECRET_KEY
JUSTICEFLOW_LANGFUSE_BASE_URL
JUSTICEFLOW_OIDC_ISSUER
JUSTICEFLOW_OIDC_JWKS_URL
```

Set `JUSTICEFLOW_ALLOWED_ORIGINS` to the final Vercel production origin:

```text
https://YOUR-VERCEL-DOMAIN
```

Do not include a trailing slash in the CORS origin.

The remaining hosted values are declared in `render.yaml`.

After deployment, verify:

```text
https://YOUR-RENDER-DOMAIN/health
```

A healthy response includes `status`, `model`, and `provider`.

## 6. Create the Vercel site

Import the GitHub repository into Vercel.

Set the project Root Directory to:

```text
web
```

Use the repository's detected Next.js framework settings.

Configure these production environment variables:

```text
NEXT_PUBLIC_API_URL=https://YOUR-RENDER-DOMAIN
NEXT_PUBLIC_OIDC_AUTHORITY=https://AUTH0_DOMAIN
NEXT_PUBLIC_OIDC_CLIENT_ID=YOUR-AUTH0-CLIENT-ID
NEXT_PUBLIC_OIDC_AUDIENCE=https://justiceflow-api
```

Do not add a trailing slash to `NEXT_PUBLIC_API_URL` or `NEXT_PUBLIC_OIDC_AUTHORITY`.

`NEXT_PUBLIC_OIDC_AUDIENCE` must exactly match the Auth0 API identifier and the backend `JUSTICEFLOW_OIDC_AUDIENCE` value. The SPA sends it as the OAuth authorization request `audience` parameter so Auth0 issues an access token for the JusticeFlow API.

All `NEXT_PUBLIC_` values are embedded during the Next.js build. Redeploy the site after changing any of them.

## 7. Resolve the deployment URL dependency

Render needs the Vercel origin for CORS, while Auth0 needs the Vercel URL for redirects. Use this order:

1. Create all external provider projects.
2. Import the Vercel project to obtain its stable production domain.
3. Configure the Vercel environment variables with the intended Render domain.
4. Add the Vercel domain to Auth0 callback, logout, and web-origin settings.
5. Create the Render Blueprint and set `JUSTICEFLOW_ALLOWED_ORIGINS` to the Vercel origin.
6. Deploy Render.
7. Redeploy Vercel after confirming the final Render domain.
8. Test both roles through the browser.

If Render assigns a different domain than expected, update `NEXT_PUBLIC_API_URL` in Vercel and redeploy.

## 8. Verify the hosted deployment

### Health

Open the Render health endpoint and confirm the configured provider and model are reported.

### Authentication

Verify:

- unauthenticated users see the sign-in page
- Auth0 uses Authorization Code with PKCE
- the caseworker can view cases, select the hosted model, request triage, and record a decision
- the auditor can view cases, observability status, and decision history
- the auditor cannot request triage or record decisions
- sign-out returns to the application

### Persistence

Record a synthetic human decision, refresh the browser, and confirm the decision remains visible.

### Model controls

Verify:

- the model selector exposes only the configured hosted model
- malformed model output produces no recommendation
- prohibited rationale produces no recommendation
- hearing-deadline cases cannot be downgraded below urgent
- accessibility and housing-instability cases cannot be downgraded to standard

### Observability

Generate a recommendation and verify a Langfuse generation appears with:

- model identifier
- bounded model parameters
- token counts
- latency
- final recommendation
- model confidence
- synthetic-data marker
- human-review-required marker

Confirm the trace does not contain the prompt, case summary, rationale, or evidence.

## 9. Free-tier operational behavior

Expect the first Render request after inactivity to be slower while the service starts.

Neon, Auth0, Groq, Langfuse Cloud, Render, and Vercel each enforce their own quotas and acceptable-use rules. Check each dashboard before demonstrations and configure spending controls wherever a provider offers them.

The repository declares only the Render service. Neon, Auth0, Groq, Langfuse Cloud, and Vercel require account-level setup and secrets that must not be committed.

## 10. Local development remains unchanged

Local development still uses:

```sh
ollama serve
ollama pull qwen3:4b
docker compose up --build
```

The default local provider settings are:

```text
MODEL_PROVIDER=ollama
MODEL_BASE_URL=http://host.docker.internal:11434
MODEL_NAME=qwen3:4b
MODEL_API_KEY=
MODEL_TIMEOUT_SECONDS=120
```

Keycloak continues to supply roles through:

```text
realm_access.roles
```

The hosted Auth0 configuration changes only the configured role-claim path, not the API's exact-one-role authorization rule.
