from collections.abc import AsyncIterator
from typing import Annotated

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings, SettingsConfigDict

from .cases import CASES, get_case
from .database import create_engine, create_session_factory, session_scope
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


settings = Settings()
configure_logging(settings.log_level)
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
    allow_headers=["Content-Type"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.ollama_model}


@app.get("/api/cases")
async def list_cases() -> list[Case]:
    return CASES


@app.post(
    "/api/triage",
    responses={
        404: {"description": "Case not found"},
        503: {"description": "Local AI provider unavailable"},
    },
)
async def triage_case(request: TriageRequest) -> TriageResult:
    case = get_case(request.case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    client = OllamaClient(
        settings.ollama_url,
        settings.ollama_model,
        settings.ollama_timeout_seconds,
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
) -> Decision:
    if get_case(request.case_id) is None:
        raise HTTPException(status_code=404, detail="Case not found")
    decision = await repository.add(request)
    logger.info(
        "human_decision_recorded",
        case_id=decision.case_id,
        outcome=decision.outcome,
        reviewer=decision.reviewer,
    )
    return decision
