from urllib.parse import quote

import pytest
from sqlalchemy.engine import make_url

from app.database_url import normalize_asyncpg_url


def test_normalize_asyncpg_url_converts_neon_connection_parameters() -> None:
    database_url = (
        "postgresql+asyncpg://justiceflow:secret@database.example/justiceflow"
        "?sslmode=require&channel_binding=require&application_name=justiceflow"
    )

    normalized = make_url(normalize_asyncpg_url(database_url))

    assert normalized.drivername == "postgresql+asyncpg"
    assert normalized.username == "justiceflow"
    assert normalized.password == "secret"
    assert normalized.host == "database.example"
    assert normalized.database == "justiceflow"
    assert normalized.query == {
        "application_name": "justiceflow",
        "ssl": "require",
    }


def test_normalize_asyncpg_url_preserves_url_without_libpq_parameters() -> None:
    database_url = (
        "postgresql+asyncpg://justiceflow:secret@database.example/justiceflow"
        "?ssl=require&application_name=justiceflow"
    )

    assert normalize_asyncpg_url(database_url) == database_url


def test_normalize_asyncpg_url_leaves_other_drivers_unchanged() -> None:
    database_url = (
        "postgresql+psycopg://justiceflow:secret@database.example/justiceflow"
        "?sslmode=require&channel_binding=require"
    )

    assert normalize_asyncpg_url(database_url) == database_url


def test_normalize_asyncpg_url_rejects_conflicting_ssl_parameters() -> None:
    database_url = (
        "postgresql+asyncpg://justiceflow:secret@database.example/justiceflow"
        "?sslmode=require&ssl=verify-full"
    )

    with pytest.raises(
        ValueError,
        match="conflicting ssl and sslmode parameters",
    ):
        normalize_asyncpg_url(database_url)


def test_normalize_asyncpg_url_preserves_encoded_credentials() -> None:
    credential = "fixture:value"
    encoded_credential = quote(credential, safe="")
    database_url = (
        "postgresql+asyncpg://justiceflow:"
        f"{encoded_credential}@database.example/justiceflow?sslmode=require"
    )

    normalized = make_url(normalize_asyncpg_url(database_url))

    assert normalized.password == credential
    assert normalized.query == {"ssl": "require"}
