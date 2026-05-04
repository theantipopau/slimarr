"""
Centralized API response envelope and error handling.

Provides:
- Standard response schema with code, message, details, correlation_id
- Exception mapping to consistent error envelopes
- Correlation ID generation for request tracing
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar
from uuid import uuid4
from contextvars import ContextVar

from pydantic import BaseModel

T = TypeVar("T")

# Context variable for correlation ID (one per request)
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for request tracing."""
    return str(uuid4())


def get_correlation_id() -> str:
    """Get the current request's correlation ID."""
    return _correlation_id.get()


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current context (used by middleware)."""
    _correlation_id.set(cid)


class APIResponse(BaseModel, Generic[T]):
    """Standard successful response envelope."""

    success: bool = True
    code: str  # e.g. "OK", "CREATED", "PARTIAL_SUCCESS"
    message: str  # e.g. "Movies fetched successfully"
    data: T  # Response payload
    correlation_id: str  # For tracing across logs and integrations


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    success: bool = False
    code: str  # e.g. "NOT_FOUND", "VALIDATION_ERROR", "INTERNAL_ERROR", "RATE_LIMITED"
    message: str  # User-friendly error message
    details: dict[str, Any] | None = None  # Additional context (field errors, etc.)
    correlation_id: str  # For tracing


class APIException(Exception):
    """Custom exception for consistent error responses."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.correlation_id = correlation_id or generate_correlation_id()
        super().__init__(message)

    def to_response(self) -> ErrorResponse:
        """Convert to error response envelope."""
        return ErrorResponse(
            code=self.code,
            message=self.message,
            details=self.details if self.details else None,
            correlation_id=self.correlation_id,
        )


# Common exception factory functions
def not_found(resource: str, correlation_id: str | None = None) -> APIException:
    """404 Not Found."""
    return APIException(
        code="NOT_FOUND",
        message=f"{resource} not found",
        status_code=404,
        correlation_id=correlation_id,
    )


def unauthorized(reason: str = "Authentication required", correlation_id: str | None = None) -> APIException:
    """401 Unauthorized."""
    return APIException(
        code="UNAUTHORIZED",
        message=reason,
        status_code=401,
        correlation_id=correlation_id,
    )


def forbidden(reason: str = "Access denied", correlation_id: str | None = None) -> APIException:
    """403 Forbidden."""
    return APIException(
        code="FORBIDDEN",
        message=reason,
        status_code=403,
        correlation_id=correlation_id,
    )


def validation_error(
    message: str = "Validation failed",
    details: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> APIException:
    """400 Bad Request (validation)."""
    return APIException(
        code="VALIDATION_ERROR",
        message=message,
        status_code=400,
        details=details,
        correlation_id=correlation_id,
    )


def rate_limited(
    message: str = "Too many requests",
    details: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> APIException:
    """429 Rate Limited."""
    return APIException(
        code="RATE_LIMITED",
        message=message,
        status_code=429,
        details=details,
        correlation_id=correlation_id,
    )


def internal_error(
    message: str = "Internal server error",
    details: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> APIException:
    """500 Internal Server Error."""
    return APIException(
        code="INTERNAL_ERROR",
        message=message,
        status_code=500,
        details=details,
        correlation_id=correlation_id,
    )


def service_unavailable(
    service: str,
    correlation_id: str | None = None,
) -> APIException:
    """503 Service Unavailable."""
    return APIException(
        code="SERVICE_UNAVAILABLE",
        message=f"{service} is currently unavailable",
        status_code=503,
        correlation_id=correlation_id,
    )
