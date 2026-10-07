# JusticeFlow Azure target

This directory is a reviewable Azure deployment target for the JusticeFlow portfolio project. It demonstrates Terraform and Azure platform design without creating resources in the currently authenticated organisation subscription.

## Architecture

The configuration provisions:

- Azure Container Registry for immutable API and web images
- Azure Container Apps for the FastAPI and Next.js workloads
- a shared user-assigned managed identity for ACR pulls and Key Vault access
- Azure Key Vault for the runtime database URL and optional Langfuse credentials
- Azure Database for PostgreSQL Flexible Server
- a Log Analytics-backed Container Apps environment
- health probes and HTTP autoscaling for both workloads

The model remains behind an externally supplied, approved Ollama-compatible endpoint. Terraform does not attempt to deploy a large language model into the subscription.

The registry intentionally uses public network access in this compact portfolio target. It does not use its own managed identity because Container Apps authenticate to ACR through the dedicated `azurerm_user_assigned_identity.workload` identity and the `AcrPull` role assignment.

## Safety guardrail

Do not run `terraform plan` or `terraform apply` while authenticated to an employer or customer subscription. This repository intentionally contains no backend configuration and no subscription identifier.

Use a dedicated personal sandbox subscription and remote state with locking before deployment.

## Validate without Azure changes

```sh
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra init -backend=false
terraform -chdir=infra validate
```

These commands install the pinned provider and validate configuration only. They do not propose or create Azure resources.

## Deployment inputs

Copy `terraform.tfvars.example` to an ignored `terraform.tfvars` only in an approved sandbox. Supply secrets through protected CI variables rather than committing them.

Image inputs must be immutable SHA-256 digest references; Terraform rejects mutable tags and malformed digests. The web image must be built with the final public API URL, OIDC authority, and public client ID because `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_OIDC_AUTHORITY`, and `NEXT_PUBLIC_OIDC_CLIENT_ID` are embedded during the Next.js build.

The API receives the matching HTTPS issuer, audience, JWKS URL, and role-claim path as runtime settings. Terraform derives the API CORS allowlist from the deployed web Container App HTTPS FQDN, so the production API does not retain the localhost development origin. The Azure target selects the `ollama` provider through the provider-neutral runtime contract and requires HTTPS for its model endpoint and for any configured Langfuse endpoint; insecure HTTP endpoints are rejected. Optional Langfuse public and secret keys must be configured together or both left empty, and one shared condition controls their Key Vault secrets and Container App environment variables. The local Keycloak realm proves the protocol and role contract; Azure deployment uses an approved OIDC tenant such as Microsoft Entra ID rather than deploying the local development identity service.

## Production hardening

This portfolio target deliberately exposes public ingress, public ACR access, and public PostgreSQL networking to keep the example reviewable and compact. A real justice deployment requires:

- private endpoints and delegated subnets
- private DNS
- WAF or API gateway controls
- approved Entra ID tenant configuration, conditional access, and lifecycle governance
- customer-managed Terraform state
- Azure Policy enforcement
- backup and restore testing
- threat modelling
- formal information-governance approval

The PostgreSQL administrator password is a sensitive Terraform input and is therefore present in state. Production must use an approved secret bootstrap and rotation process, and state must be encrypted with tightly controlled access.

## Deliberately not executed

This repository validates Terraform syntax and provider compatibility only. No `terraform plan` or `terraform apply` was run against the authenticated Azure subscription.
