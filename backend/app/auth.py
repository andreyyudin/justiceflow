from collections.abc import Callable
from enum import StrEnum
from typing import Annotated, Any

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient
from pydantic import BaseModel


class Role(StrEnum):
    caseworker = "caseworker"
    auditor = "auditor"


class Identity(BaseModel):
    subject: str
    display_name: str
    role: Role


IdentityDependencyCallable = Callable[..., Identity]


class OidcTokenValidator:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_url: str,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks = PyJWKClient(
            jwks_url,
            cache_keys=True,
            lifespan=300,
            timeout=5,
        )

    def validate(self, token: str) -> Identity:
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": ["exp", "iat", "iss", "sub"],
                },
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=401,
                detail="Bearer token is invalid or expired.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        roles = claims.get("realm_access", {}).get("roles", [])
        permitted_roles = [role for role in (Role.caseworker, Role.auditor) if role.value in roles]
        if len(permitted_roles) != 1:
            raise HTTPException(
                status_code=403,
                detail="Token must contain exactly one permitted JusticeFlow role.",
            )

        display_name = claims.get("name") or claims.get("preferred_username")
        if not isinstance(display_name, str) or not display_name.strip():
            raise HTTPException(
                status_code=403,
                detail="Token does not contain a display identity.",
            )

        subject = claims["sub"]
        if not isinstance(subject, str) or not subject:
            raise HTTPException(
                status_code=403,
                detail="Token does not contain a subject.",
            )

        return Identity(
            subject=subject,
            display_name=display_name,
            role=permitted_roles[0],
        )


def create_identity_dependency(
    validator: OidcTokenValidator,
) -> IdentityDependencyCallable:
    def get_identity(
        authorization: Annotated[
            str | None,
            Header(alias="Authorization"),
        ] = None,
    ) -> Identity:
        if not authorization:
            raise HTTPException(
                status_code=401,
                detail="Bearer token is required.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        scheme, separator, token = authorization.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(
                status_code=401,
                detail="Authorization header must use the Bearer scheme.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return validator.validate(token.strip())

    return get_identity


def authorize(identity: Identity, *allowed_roles: Role) -> None:
    if identity.role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail="Role is not permitted for this operation.",
        )
