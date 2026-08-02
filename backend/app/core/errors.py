"""Fachliche Fehlertypen und deren Abbildung auf HTTP-Antworten."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Basisklasse fuer alle fachlichen Fehler."""

    status_code = 400
    code = "domain_error"

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class ValidationError(DomainError):
    status_code = 422
    code = "validation_error"


class PermissionError_(DomainError):
    status_code = 403
    code = "forbidden"


class AuthError(DomainError):
    status_code = 401
    code = "unauthorized"


class AIError(DomainError):
    """Die KI hat keine verwertbare Antwort geliefert."""

    status_code = 502
    code = "ai_error"


class RateLimitedError(DomainError):
    status_code = 429
    code = "rate_limited"


def register_exception_handlers(app: FastAPI) -> None:
    """Registriert die Umsetzung von DomainError auf JSON-Antworten."""

    @app.exception_handler(DomainError)
    async def _handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )
