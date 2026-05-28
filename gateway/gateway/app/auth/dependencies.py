import hashlib
import hmac
import json
import os
from typing import Any

from fastapi import Request

from gateway.app.api.errors import api_error

from .models import RequestIdentity


API_TOKENS_ENV = "SKILL_GATEWAY_API_TOKENS"
API_TOKEN_IDENTITIES_ENV = "SKILL_GATEWAY_API_TOKEN_IDENTITIES"
AUTH_MODE_ENV = "SKILL_GATEWAY_AUTH_MODE"
AUTH_DISABLED_ENV = "SKILL_GATEWAY_AUTH_DISABLED"
TENANT_HEADER = "X-Tenant-Id"
ROLE_HEADER = "X-User-Role"
DEFAULT_TENANT_ID = "default"
DEFAULT_ROLE = "developer"
ALLOWED_ROLES = {"viewer", "developer"}


class TokenIdentityConfigError(ValueError):
    """Raised when server-side token identity config is malformed."""


def require_request_identity(request: Request) -> RequestIdentity:
    identity = _request_identity(request)
    request.state.identity = identity
    return identity


def _request_identity(request: Request) -> RequestIdentity:
    if _dev_auth_bypass_enabled():
        return RequestIdentity(
            auth_mode="dev",
            tenant_id=_tenant_id_from_request(request),
            role=_role_from_request(request),
            token_id=None,
        )

    supplied_token = _bearer_token_from_request(request)
    if supplied_token is None:
        raise _auth_error("auth_required", "Authentication is required.")

    try:
        token_identity = _identity_for_token(supplied_token)
        if token_identity is not None:
            return token_identity

        if not _has_token_config():
            raise _auth_error("auth_required", "Authentication is required.")
    except TokenIdentityConfigError as exc:
        raise _auth_error("auth_required", "Authentication is required.") from exc

    raise _auth_error("invalid_token", "Invalid authentication token.")


def _identity_for_token(token: str) -> RequestIdentity | None:
    for token_identity in _configured_token_identities():
        if hmac.compare_digest(token, token_identity["token"]):
            return RequestIdentity(
                auth_mode="token",
                tenant_id=token_identity["tenant_id"],
                role=token_identity["role"],
                token_id=_safe_token_id(token),
            )

    for allowed_token in _allowed_tokens():
        if hmac.compare_digest(token, allowed_token):
            return RequestIdentity(
                auth_mode="token",
                tenant_id=DEFAULT_TENANT_ID,
                role=DEFAULT_ROLE,
                token_id=_safe_token_id(token),
            )

    return None


def _configured_token_identities() -> list[dict[str, str]]:
    raw_env = os.getenv(API_TOKEN_IDENTITIES_ENV)
    if raw_env is None or not raw_env.strip():
        return []
    raw_config = raw_env.strip()

    try:
        decoded = json.loads(raw_config)
    except json.JSONDecodeError:
        raise TokenIdentityConfigError("token identity config must be valid JSON")

    if not isinstance(decoded, list):
        raise TokenIdentityConfigError("token identity config must be a JSON array")

    identities: list[dict[str, str]] = []
    tokens: set[str] = set()
    for record in decoded:
        identity = _token_identity_from_record(record)
        if identity["token"] in tokens:
            raise TokenIdentityConfigError("token identity config has duplicate tokens")
        tokens.add(identity["token"])
        identities.append(identity)
    return identities


def _token_identity_from_record(record: Any) -> dict[str, str]:
    if not isinstance(record, dict):
        raise TokenIdentityConfigError("token identity records must be objects")

    token = _non_empty_string(record.get("token"))
    tenant_id = _non_empty_string(record.get("tenant_id"))
    role = _non_empty_string(record.get("role"))
    if token is None or tenant_id is None or role is None:
        raise TokenIdentityConfigError("token identity records require token, tenant_id, and role")

    normalized_role = role.casefold()
    if normalized_role not in ALLOWED_ROLES:
        raise TokenIdentityConfigError("token identity role is unsupported")

    return {
        "token": token,
        "tenant_id": tenant_id,
        "role": normalized_role,
    }


def _non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _has_token_config() -> bool:
    return bool(_configured_token_identities() or _allowed_tokens())


def _allowed_tokens() -> list[str]:
    raw_tokens = os.getenv(API_TOKENS_ENV, "")
    return [token.strip() for token in raw_tokens.split(",") if token.strip()]


def _dev_auth_bypass_enabled() -> bool:
    auth_mode = os.getenv(AUTH_MODE_ENV, "").strip().casefold()
    auth_disabled = os.getenv(AUTH_DISABLED_ENV, "").strip().casefold()
    return auth_mode == "dev" or auth_disabled == "true"


def _bearer_token_from_request(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if authorization is None:
        return None

    scheme, separator, token = authorization.partition(" ")
    if separator == "" or scheme.casefold() != "bearer" or not token.strip():
        return None
    return token.strip()


def _tenant_id_from_request(request: Request) -> str:
    tenant_id = request.headers.get(TENANT_HEADER, "").strip()
    return tenant_id or DEFAULT_TENANT_ID


def _role_from_request(request: Request) -> str:
    role = request.headers.get(ROLE_HEADER, "").strip().casefold()
    if not role:
        return DEFAULT_ROLE
    if role in ALLOWED_ROLES:
        return role
    return "viewer"


def _safe_token_id(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def _auth_error(code: str, message: str) -> Exception:
    return api_error(
        status_code=401,
        code=code,
        message=message,
        headers={"WWW-Authenticate": "Bearer"},
    )
