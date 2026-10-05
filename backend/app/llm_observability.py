from typing import Any, Protocol

from langfuse import Langfuse


class GenerationHandle(Protocol):
    def succeed(
        self,
        *,
        recommendation: str,
        confidence: float,
        latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None: ...

    def fail(self, *, error_type: str, latency_ms: int) -> None: ...


class LlmTelemetry(Protocol):
    def start_generation(
        self,
        *,
        model: str,
        case_id: str,
        service: str,
        risk_flag_count: int,
    ) -> GenerationHandle: ...


class LangfuseGenerationHandle:
    def __init__(self, observation: Any) -> None:
        self._observation = observation

    def succeed(
        self,
        *,
        recommendation: str,
        confidence: float,
        latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        self._observation.update(
            output={
                "recommendation": recommendation,
                "confidence": confidence,
            },
            metadata={
                "latency_ms": latency_ms,
                "human_review_required": True,
            },
            usage_details={
                "input": prompt_tokens,
                "output": completion_tokens,
            },
        )
        self._observation.score(
            name="schema_valid",
            value=1.0,
            data_type="NUMERIC",
            comment="Model output passed typed schema validation.",
        )
        self._observation.end()

    def fail(self, *, error_type: str, latency_ms: int) -> None:
        self._observation.update(
            level="ERROR",
            status_message=error_type,
            metadata={"latency_ms": latency_ms},
        )
        self._observation.end()


class LangfuseTelemetry:
    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        base_url: str | None,
        environment: str,
        release: str,
    ) -> None:
        self._client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            base_url=base_url,
            environment=environment,
            release=release,
        )

    def start_generation(
        self,
        *,
        model: str,
        case_id: str,
        service: str,
        risk_flag_count: int,
    ) -> GenerationHandle:
        observation = self._client.start_observation(
            name="justiceflow-triage",
            as_type="generation",
            model=model,
            model_parameters={
                "temperature": 0,
                "max_tokens": 256,
                "thinking": False,
            },
            metadata={
                "case_id": case_id,
                "service": service,
                "risk_flag_count": risk_flag_count,
                "synthetic_data": True,
                "prompt_capture": False,
            },
        )
        return LangfuseGenerationHandle(observation)

    def shutdown(self) -> None:
        self._client.shutdown()


def create_llm_telemetry(
    *,
    public_key: str | None,
    secret_key: str | None,
    base_url: str | None,
    environment: str,
    release: str,
) -> LlmTelemetry | None:
    if not public_key or not secret_key:
        return None
    return LangfuseTelemetry(
        public_key=public_key,
        secret_key=secret_key,
        base_url=base_url,
        environment=environment,
        release=release,
    )
