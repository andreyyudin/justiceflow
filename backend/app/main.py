from collections.abc import AsyncIterator
from typing import Annotated

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings, SettingsConfigDict

from .auth import (
    Identity,
    OidcTokenValidator,
    Role,
    authorize,
    create_identity_dependency,
)
from .cases import CASES, get_case
from .database import create_engine, create_session_factory, session_scope
from .llm_observability import create_llm_telemetry
from .observability import configure_logging, request_context_middleware
from .repositories import DecisionRepository
from .schemas import Case, Decision, DecisionRequest, TriageRequest, TriageResult
from .triage import OllamaClient

logger = structlog.get_logger()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JUSTICEFLOW_")
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout_seconds: float = 120.0
    allowed_origins: str = "http://localhost:3000"
    database_url: str = "postgresql+asyncpg://localhost/justiceflow"
    log_level: str = "INFO"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str | None = None
    langfuse_environment: str = "local"
    release: str = "development"
    oidc_issuer: str = "http://localhost:8080/realms/justiceflow"
    oidc_audience: str = "justiceflow-api"
    oidc_jwks_url: str = "http://localhost:8080/realms/justiceflow/protocol/openid-connect/certs"


settings = Settings()
configure_logging(settings.log_level)
llm_telemetry = create_llm_telemetry(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    base_url=settings.langfuse_base_url,
    environment=settings.langfuse_environment,
    release=settings.release,
)
engine = create_engine(settings.database_url)
session_factory = create_session_factory(engine)

DecisionRepositoryIterator = AsyncIterator[DecisionRepository]


async def get_decision_repository() -> DecisionRepositoryIterator:
    async for session in session_scope(session_factory):
        yield DecisionRepository(session)


DecisionRepositoryDependency = Annotated[
    DecisionRepository,
    Depends(get_decision_repository),
]

oidc_validator = OidcTokenValidator(
    issuer=settings.oidc_issuer,
    audience=settings.oidc_audience,
    jwks_url=settings.oidc_jwks_url,
)
get_identity = create_identity_dependency(oidc_validator)
IdentityDependency = Annotated[Identity, Depends(get_identity)]


app = FastAPI(
    title="JusticeFlow API",
    version="0.1.0",
    description="Human-in-the-loop triage for synthetic justice casework.",
)
app.middleware("http")(request_context_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Authorization",
        "Content-Type",
    ],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.ollama_model}


@app.get("/api/identity")
async def current_identity(identity: IdentityDependency) -> Identity:
    return identity


@app.get("/api/cases")
async def list_cases(identity: IdentityDependency) -> list[Case]:
    authorize(identity, Role.caseworker, Role.auditor)
    return CASES


@app.post(
    "/api/triage",
    responses={
        404: {"description": "Case not found"},
        503: {"description": "Local AI provider unavailable"},
    },
)
async def triage_case(
    request: TriageRequest,
    identity: IdentityDependency,
) -> TriageResult:
    authorize(identity, Role.caseworker)
    case = get_case(request.case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    client = OllamaClient(
        settings.ollama_url,
        settings.ollama_model,
        settings.ollama_timeout_seconds,
        llm_telemetry,
    )
    try:
        result = await client.triage(case)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning(
            "triage_provider_failed",
            case_id=case.id,
            error_type=type(exc).__name__,
            error=str(exc) or repr(exc),
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Local AI is unavailable. Start Ollama and ensure the configured "
                "model is installed."
            ),
        ) from exc
    logger.info(
        "triage_completed",
        case_id=case.id,
        recommendation=result.recommendation,
        model=result.model,
        latency_ms=result.latency_ms,
        actor_subject=identity.subject,
        actor_role=identity.role,
    )
    return result


@app.post(
    "/api/decisions",
    status_code=201,
    responses={404: {"description": "Case not found"}},
)
async def record_decision(
    request: DecisionRequest,
    repository: DecisionRepositoryDependency,
    identity: IdentityDependency,
) -> Decision:
    authorize(identity, Role.caseworker)
    if get_case(request.case_id) is None:
        raise HTTPException(status_code=404, detail="Case not found")
    decision = await repository.add(
        request,
        reviewer=identity.display_name,
    )
    logger.info(
        "human_decision_recorded",
        case_id=decision.case_id,
        outcome=decision.outcome,
        reviewer=decision.reviewer,
        actor_subject=identity.subject,
        actor_role=identity.role,
    )
    return decision
