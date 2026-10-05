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
                        "rationale": "Synthetic model rationale.",
                        "evidence": ["hearing deadline"],
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
    assert result.requires_human_review is True
