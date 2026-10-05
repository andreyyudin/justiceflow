import json
import logging

import pytest
import structlog
from fastapi.testclient import TestClient

from app.main import app
from app.observability import REQUEST_ID_HEADER, configure_logging


def test_request_id_is_preserved_in_response() -> None:
    client = TestClient(app)

    response = client.get("/health", headers={REQUEST_ID_HEADER: "test-request-123"})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "test-request-123"


def test_request_id_is_generated_when_absent() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER]


def test_configure_logging_emits_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")

    structlog.get_logger().info("test_event", outcome="passed")

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["event"] == "test_event"
    assert payload["outcome"] == "passed"
    assert payload["level"] == "info"

    logging.shutdown()
