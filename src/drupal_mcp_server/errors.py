"""Standardized error response format for all MCP tools."""

from typing import Any


def error_response(
    message: str,
    code: str = "ERROR",
    details: dict[str, Any] | None = None,
    status_code: int = 400,
) -> dict[str, Any]:
    """Build a standardized error response.

    All MCP tools should return errors in this format for consistency.

    Args:
        message: Human-readable error message
        code: Machine-readable error code
        details: Additional error context
        status_code: HTTP-equivalent status code

    Returns:
        Standardized error dict
    """
    response = {
        "error": {
            "code": code,
            "message": message,
            "status_code": status_code,
        }
    }
    if details:
        response["error"]["details"] = details
    return response


# Common error codes
ERROR_AUTHENTICATION = "AUTHENTICATION_ERROR"
ERROR_AUTHORIZATION = "AUTHORIZATION_ERROR"
ERROR_NOT_FOUND = "NOT_FOUND"
ERROR_VALIDATION = "VALIDATION_ERROR"
ERROR_RATE_LIMIT = "RATE_LIMIT_ERROR"
ERROR_SERVER = "SERVER_ERROR"
ERROR_TIMEOUT = "TIMEOUT"
ERROR_CONFIGURATION = "CONFIGURATION_ERROR"
