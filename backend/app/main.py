from collections.abc import AsyncIterator
from typing import Annotated

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
from .schemas import (
    Case,
    CaseStatus,
    Decision,
    DecisionHistory,
    DecisionRequest,
    ObservabilityStatus,
    RecommendationCreate,
    TriageRequest,
    TriageResult,
)
from .triage import ModelOutputSafetyError, OllamaClient

logger = structlog.get_logger()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JUSTICEFLOW_")
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout_seconds: float = 120.0
    allowed_origins: str = "http://localhost:3000"
    database_url: str = "postgresql+asyncpg://localhost/justiceflow"
    log_level: str = "INFO"
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_base_url: str
    langfuse_environment: str = "local"
    release: str = "development"
    oidc_issuer: str = "http://localhost:8080/realms/justiceflow"
    oidc_audience: str = "justiceflow-api"
    oidc_jwks_url: str = "http://localhost:8080/realms/justiceflow/protocol/openid-connect/certs"


settings = Settings()  # type: ignore[call-arg]  # Values are loaded from required environment variables.
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
    expose_headers=["X-Request-ID"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.ollama_model}


@app.get("/api/identity")
async def current_identity(identity: IdentityDependency) -> Identity:
    return identity


@app.get("/api/cases")
async def list_cases(
    identity: IdentityDependency,
    repository: DecisionRepositoryDependency,
) -> list[Case]:
    authorize(identity, Role.caseworker, Role.auditor)
    latest_decisions = await repository.latest_by_case_id()

    return [
        case.model_copy(
            update={
                "priority": latest.outcome,
                "status": CaseStatus.approved,
                "latest_decision": latest,
            }
        )
        if (latest := latest_decisions.get(case.id))
        else case
        for case in CASES
    ]


@app.get("/api/observability")
async def observability_status(identity: IdentityDependency) -> ObservabilityStatus:
    authorize(identity, Role.auditor)
    return ObservabilityStatus(
        langfuse_enabled=True,
        environment=settings.langfuse_environment,
        release=settings.release,
    )


@app.get("/api/decisions/history")
async def decision_history(
    identity: IdentityDependency,
    repository: DecisionRepositoryDependency,
) -> DecisionHistory:
    authorize(identity, Role.auditor)
    return await repository.decision_history()


@app.post(
    "/api/triage",
    responses={
        404: {"description": "Case not found"},
        503: {"description": "Local AI provider unavailable"},
    },
)
async def triage_case(
    request: TriageRequest,
    repository: DecisionRepositoryDependency,
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
    except ModelOutputSafetyError as exc:
        logger.warning(
            "triage_output_rejected",
            case_id=case.id,
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail=("Local AI returned an invalid response. No recommendation was recorded."),
        ) from exc
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
    persisted = await repository.add_recommendation(
        RecommendationCreate(
            case_id=result.case_id,
            recommendation=result.recommendation,
            rationale=result.rationale,
            evidence=result.evidence,
            model=result.model,
            model_confidence=result.model_confidence,
            latency_ms=result.latency_ms,
        )
    )
    logger.info(
        "triage_completed",
        case_id=case.id,
        recommendation_id=str(persisted.id),
        recommendation=persisted.recommendation,
        model=persisted.model,
        latency_ms=persisted.latency_ms,
        actor_subject=identity.subject,
        actor_role=identity.role,
    )
    return TriageResult(
        recommendation_id=persisted.id,
        case_id=persisted.case_id,
        recommendation=persisted.recommendation,
        rationale=persisted.rationale,
        evidence=persisted.evidence,
        model=persisted.model,
        latency_ms=persisted.latency_ms,
    )


@app.post(
    "/api/decisions",
    status_code=201,
    response_model=Decision,
    responses={
        200: {"description": "Existing decision returned for an idempotent replay"},
        404: {"description": "Case or recommendation not found"},
        409: {
            "description": (
                "Recommendation is stale, already has a conflicting decision, "
                "or belongs to another case"
            )
        },
    },
)
async def record_decision(
    request: DecisionRequest,
    repository: DecisionRepositoryDependency,
    identity: IdentityDependency,
) -> Decision | JSONResponse:
    authorize(identity, Role.caseworker)
    if get_case(request.case_id) is None:
        raise HTTPException(status_code=404, detail="Case not found")

    recommendation = await repository.get_recommendation(
        request.recommendation_id,
    )
    if recommendation is None:
        raise HTTPException(
            status_code=404,
            detail="Recommendation not found.",
        )
    if recommendation.case_id != request.case_id:
        raise HTTPException(
            status_code=409,
            detail="Recommendation does not belong to this case.",
        )

    existing = await repository.decision_for_recommendation(
        request.recommendation_id,
    )
    if existing is not None:
        if (
            existing.case_id == request.case_id
            and existing.outcome == request.outcome
            and existing.reason == request.reason
            and existing.reviewer == identity.display_name
        ):
            return JSONResponse(
                status_code=200,
                content=existing.model_dump(mode="json"),
            )
        raise HTTPException(
            status_code=409,
            detail="Recommendation already has a different human decision.",
        )

    latest_recommendation_id = await repository.latest_recommendation_id(
        request.case_id,
    )
    if latest_recommendation_id != request.recommendation_id:
        raise HTTPException(
            status_code=409,
            detail="Recommendation is stale. Generate a new recommendation.",
        )

    decision = await repository.add(
        request,
        reviewer=identity.display_name,
        recommendation=recommendation,
    )
    logger.info(
        "human_decision_recorded",
        case_id=decision.case_id,
        recommendation_id=str(decision.recommendation_id),
        decision_type=decision.decision_type,
        outcome=decision.outcome,
        reviewer=decision.reviewer,
        actor_subject=identity.subject,
        actor_role=identity.role,
    )
    return decision
