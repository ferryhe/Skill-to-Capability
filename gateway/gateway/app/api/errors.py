from collections.abc import Mapping
from http import HTTPStatus
import re
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from gateway.app.security.output_filter import OutputFilterViolation
from gateway.app.security.redaction import redact_sensitive_data


_SAFE_ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SAFE_ERROR_HEADERS = {"www-authenticate", "retry-after", "allow"}


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(
        RequestValidationError,
        request_validation_exception_handler,
    )
    app.add_exception_handler(OutputFilterViolation, output_filter_exception_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)


def api_error(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
            "details": dict(details or {}),
        },
    )


async def http_exception_handler(
    _request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    code, message, details = _normalize_http_detail(exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_content(code=code, message=message, details=details),
        headers=_safe_error_headers(getattr(exc, "headers", None)),
    )


async def request_validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    safe_errors = [
        {
            "type": str(error.get("type", "validation_error")),
            "message": str(error.get("msg", "Request validation failed.")),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=_error_content(
            code="request_validation_error",
            message="Request validation failed.",
            details={"errors": safe_errors},
        ),
    )


async def output_filter_exception_handler(
    _request: Request,
    exc: OutputFilterViolation,
) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content=_error_content(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        ),
    )


async def unexpected_exception_handler(
    _request: Request,
    _exc: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=_error_content(
            code="internal_server_error",
            message="Internal server error.",
            details={},
        ),
    )


def _normalize_http_detail(
    status_code: int,
    detail: Any,
) -> tuple[str, str, Mapping[str, Any]]:
    if isinstance(detail, Mapping):
        code = str(detail.get("code") or _default_error_code(status_code))
        message = str(detail.get("message") or _default_error_message(status_code))
        raw_details = detail.get("details", {})
        details = (
            raw_details if isinstance(raw_details, Mapping) else {"value": raw_details}
        )
        return code, message, details

    if isinstance(detail, str):
        return _default_error_code(status_code), detail, {}

    return _default_error_code(status_code), _default_error_message(status_code), {}


def _error_content(
    *,
    code: str,
    message: str,
    details: Mapping[str, Any],
) -> dict[str, Any]:
    safe_message = redact_sensitive_data(message)
    safe_details = redact_sensitive_data(dict(details))
    return {
        "error": {
            "code": _normalize_error_code(code),
            "message": safe_message,
            "details": safe_details,
        }
    }


def _normalize_error_code(code: str) -> str:
    if _SAFE_ERROR_CODE_PATTERN.fullmatch(code):
        return code
    return "http_error"


def _safe_error_headers(headers: Mapping[str, Any] | None) -> dict[str, str] | None:
    if not headers:
        return None

    safe_headers: dict[str, str] = {}
    for name, value in headers.items():
        if name.lower() in _SAFE_ERROR_HEADERS:
            safe_headers[name] = str(redact_sensitive_data(str(value)))
    return safe_headers or None


def _default_error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        404: "not_found",
        422: "request_validation_error",
        500: "internal_server_error",
    }.get(status_code, "http_error")


def _default_error_message(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "HTTP error"
