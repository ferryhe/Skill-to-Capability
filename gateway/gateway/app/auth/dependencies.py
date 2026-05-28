import hashlib
import hmac
import os

from fastapi import Request

from gateway.app.api.errors import api_error

from .models import RequestIdentity


API_TOKENS_ENV = "SKILL_GATEWAY_API_TOKENS"
AUTH_MODE_ENV = "SKILL_GATEWAY_AUTH_MODE"
AUTH_DISABLED_ENV = "SKILL_GATEWAY_AUTH_DISABLED"
TENANT_HEADER = "X-Tenant-Id"
DEFAULT_TENANT_ID = "default"


def require_request_identity(request: Request) -> RequestIdentity:
    identity = _request_identity(request)
    request.state.identity = identity
    return identity


def _request_identity(request: Request) -> RequestIdentity:
    if _dev_auth_bypass_enabled():
        return RequestIdentity(
            auth_mode="dev",
            tenant_id=_tenant_id_from_request(request),
            token_id=None,
        )

    allowed_tokens = _allowed_tokens()
    supplied_token = _bearer_token_from_request(request)
    if supplied_token is None:
        raise _auth_error("auth_required", "Authentication is required.")

    if not allowed_tokens:
        raise _auth_error("auth_required", "Authentication is required.")

    for allowed_token in allowed_tokens:
        if hmac.compare_digest(supplied_token, allowed_token):
            return RequestIdentity(
                auth_mode="token",
                tenant_id=_tenant_id_from_request(request),
                token_id=_safe_token_id(supplied_token),
            )

    raise _auth_error("invalid_token", "Invalid authentication token.")


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


def _safe_token_id(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def _auth_error(code: str, message: str) -> Exception:
    return api_error(
        status_code=401,
        code=code,
        message=message,
        headers={"WWW-Authenticate": "Bearer"},
    )
