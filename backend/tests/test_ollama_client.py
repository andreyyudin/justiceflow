import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.cases import get_case
from app.schemas import Priority
from app.triage import OllamaClient


@pytest.mark.asyncio
async def test_ollama_payload_disables_thinking_and_bounds_output() -> None:
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
                        "recommendation": "standard",
                        "rationale": ("The recorded hearing deadline requires urgent review."),
                        "evidence": ["summary", "risk_flags"],
                        "confidence": 0.9,
                    }
                )
            }
        },
    )
    post = AsyncMock(return_value=response)

    with patch.object(httpx.AsyncClient, "post", post):
        result = await OllamaClient(
            "http://ollama.test",
            "qwen3:4b",
            120.0,
        ).triage(case)

    payload = post.await_args.kwargs["json"]
    assert payload["think"] is False
    assert payload["options"] == {
        "temperature": 0,
        "num_predict": 256,
    }
    assert result.recommendation == Priority.urgent
    assert result.model_confidence == 0.9
    assert result.evidence == [
        (
            "Source summary: Interpreter requirement was not transferred to the "
            "revised hearing record. Hearing is due within two working days."
        ),
        "Recorded operational flags: accessibility, hearing deadline",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_output",
    [
        {
            "recommendation": "urgent",
            "rationale": "Too short.",
            "evidence": ["summary"],
            "confidence": 0.9,
        },
        {
            "recommendation": "urgent",
            "rationale": "The supplied case information requires urgent review.",
            "evidence": ["fabricated_source"],
            "confidence": 0.9,
        },
        {
            "recommendation": "urgent",
            "rationale": "The supplied case information requires urgent review.",
            "evidence": [],
            "confidence": 0.9,
        },
        {
            "recommendation": "urgent",
            "rationale": "The supplied case information requires urgent review.",
            "evidence": ["summary"],
            "confidence": 1.4,
        },
        {
            "recommendation": "urgent",
            "rationale": "The supplied case information requires urgent review.",
            "evidence": ["summary"],
            "confidence": 0.9,
            "unsupported_field": "must be rejected",
        },
    ],
)
async def test_invalid_or_ungrounded_model_output_is_rejected(
    model_output: dict[str, object],
) -> None:
    case = get_case("case-1038")
    assert case is not None

    request = httpx.Request("POST", "http://ollama.test/api/chat")
    response = httpx.Response(
        200,
        request=request,
        json={"message": {"content": json.dumps(model_output)}},
    )
    client = OllamaClient(
        "http://ollama.test",
        "qwen3:4b",
        120.0,
    )
    post = AsyncMock(return_value=response)

    with patch.object(httpx.AsyncClient, "post", post):
        with pytest.raises(ValueError):
            await client.triage(case)


@pytest.mark.asyncio
async def test_malformed_model_json_is_rejected() -> None:
    case = get_case("case-1038")
    assert case is not None

    request = httpx.Request("POST", "http://ollama.test/api/chat")
    response = httpx.Response(
        200,
        request=request,
        json={"message": {"content": "not-json"}},
    )
    client = OllamaClient(
        "http://ollama.test",
        "qwen3:4b",
        120.0,
    )
    post = AsyncMock(return_value=response)

    with patch.object(httpx.AsyncClient, "post", post):
        with pytest.raises(ValueError):
            await client.triage(case)
