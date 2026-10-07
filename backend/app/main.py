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
from .triage import (
    ModelOutputSafetyError,
    OllamaClient,
    OpenAICompatibleClient,
    TriageClient,
)

logger = structlog.get_logger()

ModelNames = list[str]
HealthStatus = dict[str, str]

HARDWARE_APPROPRIATE_MODELS = frozenset(
    {
        "deepseek-r1:1.5b",
        "llama3.2:latest",
        "phi3:latest",
        "phi4-mini-reasoning:latest",
        "phi4-mini:3.8b",
        "qwen3.5:2b",
        "qwen3:4b",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JUSTICEFLOW_")
    model_provider: str = "ollama"
    model_base_url: str = "http://localhost:11434"
    model_name: str = "qwen3:4b"
    model_api_key: str = ""
    model_timeout_seconds: float = 120.0
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
    oidc_role_claim: str = "realm_access.roles"


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
    role_claim=settings.oidc_role_claim,
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
async def health() -> HealthStatus:
    return {
        "status": "ok",
        "model": settings.model_name,
        "provider": settings.model_provider,
    }


@app.get("/api/identity")
async def current_identity(identity: IdentityDependency) -> Identity:
    return identity


async def available_models() -> ModelNames:
    if settings.model_provider == "openai-compatible":
        if not settings.model_api_key.strip():
            raise ValueError("Hosted model API key is required.")
        return [settings.model_name]

    if settings.model_provider != "ollama":
        raise ValueError(f"Unsupported model provider: {settings.model_provider}")

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{settings.model_base_url}/api/tags")
        response.raise_for_status()

    installed = {
        model["name"]
        for model in response.json().get("models", [])
        if isinstance(model, dict) and isinstance(model.get("name"), str)
    }
    available = sorted(installed & HARDWARE_APPROPRIATE_MODELS)

    if settings.model_name in available:
        available.remove(settings.model_name)
        available.insert(0, settings.model_name)

    return available


def create_triage_client(model: str) -> TriageClient:
    if settings.model_provider == "openai-compatible":
        if not settings.model_api_key.strip():
            raise ValueError("Hosted model API key is required.")
        return OpenAICompatibleClient(
            base_url=settings.model_base_url,
            api_key=settings.model_api_key,
            model=model,
            timeout_seconds=settings.model_timeout_seconds,
            telemetry=llm_telemetry,
        )

    if settings.model_provider != "ollama":
        raise ValueError(f"Unsupported model provider: {settings.model_provider}")

    return OllamaClient(
        base_url=settings.model_base_url,
        model=model,
        timeout_seconds=settings.model_timeout_seconds,
        telemetry=llm_telemetry,
    )


@app.get(
    "/api/models",
    responses={503: {"description": "AI provider unavailable"}},
)
async def list_models(identity: IdentityDependency) -> ModelNames:
    authorize(identity, Role.caseworker)
    try:
        models = await available_models()
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning(
            "model_inventory_failed",
            error_type=type(exc).__name__,
            error=str(exc) or repr(exc),
        )
        raise HTTPException(
            status_code=503,
            detail="The configured AI provider is unavailable.",
        ) from exc

    if not models:
        raise HTTPException(
            status_code=503,
            detail="No approved models are available from the configured AI provider.",
        )

    return models


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
        422: {"description": "Selected model is not approved or installed"},
        503: {"description": "AI provider unavailable"},
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

    if settings.model_provider == "ollama" and request.model not in HARDWARE_APPROPRIATE_MODELS:
        raise HTTPException(
            status_code=422,
            detail="Selected model is not approved for this hardware.",
        )

    try:
        installed_models = await available_models()
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning(
            "model_inventory_failed",
            case_id=case.id,
            error_type=type(exc).__name__,
            error=str(exc) or repr(exc),
        )
        raise HTTPException(
            status_code=503,
            detail="The configured AI provider is unavailable.",
        ) from exc

    if request.model not in installed_models:
        raise HTTPException(
            status_code=422,
            detail="Selected model is not available from the configured AI provider.",
        )

    try:
        client = create_triage_client(request.model)
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail="Configured AI provider is unavailable.",
        ) from exc

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
            detail=("AI provider returned an invalid response. No recommendation was recorded."),
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
            detail="The configured AI provider or model is unavailable.",
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
