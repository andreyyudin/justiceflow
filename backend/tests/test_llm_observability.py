import json
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from app.cases import get_case
from app.llm_observability import (
    GenerationHandle,
    LangfuseTelemetry,
    create_llm_telemetry,
)
from app.triage import OllamaClient


@pytest.mark.asyncio
async def test_telemetry_receives_metrics_but_not_case_text() -> None:
    case = get_case("case-1038")
    assert case is not None

    request = httpx.Request("POST", "http://ollama.test/api/chat")
    response = httpx.Response(
        200,
        request=request,
        json={
            "message": {
                "content": json.dumps(
                    {
                        "recommendation": "urgent",
                        "rationale": ("Synthetic rationale that must not reach telemetry."),
                        "evidence": ["summary", "risk_flags"],
                        "confidence": 0.95,
                    }
                )
            },
            "prompt_eval_count": 120,
            "eval_count": 40,
        },
    )
    post = AsyncMock(return_value=response)
    handle = Mock(spec=GenerationHandle)
    telemetry = Mock()
    telemetry.start_generation.return_value = handle

    with patch.object(httpx.AsyncClient, "post", post):
        await OllamaClient(
            "http://ollama.test",
            "qwen3:4b",
            120.0,
            telemetry,
        ).triage(case)

    telemetry.start_generation.assert_called_once_with(
        model="qwen3:4b",
        case_id="case-1038",
        service="Courts",
        risk_flag_count=2,
    )
    handle.succeed.assert_called_once()
    telemetry_payload = repr(telemetry.mock_calls) + repr(handle.mock_calls)
    assert case.summary not in telemetry_payload
    assert "Synthetic rationale" not in telemetry_payload
    assert "Synthetic evidence" not in telemetry_payload


def test_langfuse_adapter_omits_prompt_and_case_summary() -> None:
    client = Mock()
    observation = Mock()
    client.start_observation.return_value = observation

    with patch("app.llm_observability.Langfuse", return_value=client):
        telemetry = LangfuseTelemetry(
            public_key="public",
            secret_key="secret",
            base_url=None,
            environment="test",
            release="test-release",
        )
        telemetry.start_generation(
            model="qwen3:4b",
            case_id="case-1038",
            service="Courts",
            risk_flag_count=2,
        )

    kwargs = client.start_observation.call_args.kwargs
    assert "input" not in kwargs
    assert "output" not in kwargs
    assert kwargs["metadata"]["prompt_capture"] is False
    assert kwargs["metadata"]["synthetic_data"] is True


@pytest.mark.parametrize(
    ("public_key", "secret_key", "base_url"),
    [
        ("", "secret", "http://langfuse.test"),
        ("public", "", "http://langfuse.test"),
        ("public", "secret", ""),
    ],
)
def test_langfuse_rejects_incomplete_configuration(
    public_key: str,
    secret_key: str,
    base_url: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="Langfuse public key, secret key, and base URL are required",
    ):
        create_llm_telemetry(
            public_key=public_key,
            secret_key=secret_key,
            base_url=base_url,
            environment="test",
            release="test",
        )
