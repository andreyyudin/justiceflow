from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt import PyJWKClient

from app.auth import Identity, OidcTokenValidator, Role

ISSUER = "http://identity.test/realms/justiceflow"
AUDIENCE = "justiceflow-api"


@pytest.fixture
def private_key():
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


def build_token(
    private_key,
    *,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    role_names: list[str] | None = None,
    expires_in: timedelta = timedelta(minutes=5),
    name: str | None = "Casey Worker",
    subject: str = "caseworker-001",
) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "iat": now,
        "exp": now + expires_in,
        "preferred_username": "caseworker",
        "realm_access": {
            "roles": role_names if role_names is not None else ["caseworker"],
        },
    }
    if name is not None:
        claims["name"] = name
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


def validator_for(private_key) -> OidcTokenValidator:
    validator = OidcTokenValidator(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url="http://identity.test/certs",
    )
    signing_key = Mock()
    signing_key.key = private_key.public_key()
    validator._jwks = Mock(spec=PyJWKClient)
    validator._jwks.get_signing_key_from_jwt.return_value = signing_key
    return validator


def test_valid_caseworker_token_returns_identity(private_key) -> None:
    identity = validator_for(private_key).validate(build_token(private_key))

    assert identity == Identity(
        subject="caseworker-001",
        display_name="Casey Worker",
        role=Role.caseworker,
    )


@pytest.mark.parametrize(
    ("claim_override", "value"),
    [
        ("issuer", "http://wrong-issuer.test"),
        ("audience", "wrong-audience"),
        ("expires_in", timedelta(minutes=-1)),
    ],
)
def test_invalid_standard_claim_is_rejected(
    private_key,
    claim_override: str,
    value,
) -> None:
    token = build_token(private_key, **{claim_override: value})
    validator = validator_for(private_key)

    with pytest.raises(HTTPException) as error:
        validator.validate(token)

    assert error.value.status_code == 401
    assert error.value.detail == "Bearer token is invalid or expired."


@pytest.mark.parametrize(
    "role_names",
    [
        [],
        ["administrator"],
        ["caseworker", "auditor"],
    ],
)
def test_token_requires_exactly_one_permitted_role(
    private_key,
    role_names: list[str],
) -> None:
    token = build_token(private_key, role_names=role_names)
    validator = validator_for(private_key)

    with pytest.raises(HTTPException) as error:
        validator.validate(token)

    assert error.value.status_code == 403
    assert error.value.detail == ("Token must contain exactly one permitted JusticeFlow role.")


def test_username_is_used_when_name_is_absent(private_key) -> None:
    token = build_token(private_key, name=None)

    identity = validator_for(private_key).validate(token)

    assert identity.display_name == "caseworker"


def test_namespaced_role_claim_returns_identity(private_key) -> None:
    claim_name = "https://justiceflow.example/roles"
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "hosted-caseworker-001",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "name": "Hosted Caseworker",
            claim_name: ["caseworker"],
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    validator = OidcTokenValidator(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url="http://identity.test/certs",
        role_claim=claim_name,
    )
    signing_key = Mock()
    signing_key.key = private_key.public_key()
    validator._jwks = Mock(spec=PyJWKClient)
    validator._jwks.get_signing_key_from_jwt.return_value = signing_key

    identity = validator.validate(token)

    assert identity == Identity(
        subject="hosted-caseworker-001",
        display_name="Hosted Caseworker",
        role=Role.caseworker,
    )


@pytest.mark.parametrize(
    "claim_value",
    [
        "caseworker",
        {"role": "caseworker"},
        ["caseworker", 42],
        ["caseworker", "auditor"],
    ],
)
def test_namespaced_role_claim_requires_string_list_with_one_permitted_role(
    private_key,
    claim_value,
) -> None:
    claim_name = "https://justiceflow.example/roles"
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "hosted-user-001",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "name": "Hosted User",
            claim_name: claim_value,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    validator = OidcTokenValidator(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url="http://identity.test/certs",
        role_claim=claim_name,
    )
    signing_key = Mock()
    signing_key.key = private_key.public_key()
    validator._jwks = Mock(spec=PyJWKClient)
    validator._jwks.get_signing_key_from_jwt.return_value = signing_key

    with pytest.raises(HTTPException) as error:
        validator.validate(token)

    assert error.value.status_code == 403
    assert error.value.detail == ("Token must contain exactly one permitted JusticeFlow role.")
