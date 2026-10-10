"""Custom exceptions for Drupal MCP Server."""


class DrupalMCPError(Exception):
    """Base exception for Drupal MCP Server."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}


class AuthenticationError(DrupalMCPError):
    """Authentication failed."""

    pass


class AuthorizationError(DrupalMCPError):
    """Authorization failed (insufficient permissions)."""

    pass


class ConfigurationError(DrupalMCPError):
    """Invalid or missing configuration."""

    pass


class ClientError(DrupalMCPError):
    """Client-side error (4xx)."""

    def __init__(self, message: str, status_code: int = 400, details: dict = None):
        super().__init__(message, details)
        self.status_code = status_code


class ServerError(DrupalMCPError):
    """Server-side error (5xx)."""

    def __init__(self, message: str, status_code: int = 500, details: dict = None):
        super().__init__(message, details)
        self.status_code = status_code


class NotFoundError(ClientError):
    """Resource not found (404)."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, status_code=404, details=details)


class ValidationError(ClientError):
    """Validation failed (422)."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, status_code=422, details=details)


class AIProviderError(DrupalMCPError):
    """AI provider error."""

    pass


class MigrationError(DrupalMCPError):
    """Migration operation error."""

    pass


class DDEVError(DrupalMCPError):
    """DDEV operation error."""

    pass