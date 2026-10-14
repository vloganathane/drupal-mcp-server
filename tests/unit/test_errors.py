"""Tests for the shared error format and the exception hierarchy."""

import pytest

from drupal_mcp_server.errors import (
    ERROR_AUTHENTICATION,
    ERROR_AUTHORIZATION,
    ERROR_NOT_FOUND,
    ERROR_RATE_LIMIT,
    error_response,
)
from drupal_mcp_server.exceptions import (
    AIProviderError,
    AuthenticationError,
    AuthorizationError,
    ClientError,
    ConfigurationError,
    DDEVError,
    DrupalMCPError,
    MigrationError,
    NotFoundError,
    ServerError,
    ValidationError,
)


class TestErrorResponse:
    def test_builds_the_documented_shape(self) -> None:
        """Tools hand LLMs these payloads; a shape change breaks parsing."""
        assert error_response("nope") == {
            "error": {"code": "ERROR", "message": "nope", "status_code": 400}
        }

    def test_carries_code_and_status(self) -> None:
        payload = error_response("gone", code=ERROR_NOT_FOUND, status_code=404)
        assert payload["error"]["code"] == "NOT_FOUND"
        assert payload["error"]["status_code"] == 404

    def test_omits_details_when_there_are_none(self) -> None:
        """An empty `details` key would still be truthy noise to a caller."""
        assert "details" not in error_response("nope")["error"]

    def test_includes_details_when_supplied(self) -> None:
        payload = error_response("nope", details={"field": "title"})
        assert payload["error"]["details"] == {"field": "title"}

    def test_common_codes_are_stable(self) -> None:
        assert ERROR_AUTHENTICATION == "AUTHENTICATION_ERROR"
        assert ERROR_AUTHORIZATION == "AUTHORIZATION_ERROR"
        assert ERROR_RATE_LIMIT == "RATE_LIMIT_ERROR"


class TestExceptions:
    def test_base_carries_message_and_details(self) -> None:
        err = DrupalMCPError("boom", {"k": "v"})
        assert str(err) == "boom"
        assert err.details == {"k": "v"}

    def test_base_defaults_details_to_empty(self) -> None:
        assert DrupalMCPError("boom").details == {}

    @pytest.mark.parametrize(
        "exc,expected",
        [
            (ClientError("bad"), 400),
            (ServerError("bad"), 500),
            (NotFoundError("bad"), 404),
            (ValidationError("bad"), 422),
        ],
    )
    def test_status_codes(self, exc: Exception, expected: int) -> None:
        assert exc.status_code == expected

    @pytest.mark.parametrize(
        "exc",
        [
            AuthenticationError("x"),
            AuthorizationError("x"),
            ConfigurationError("x"),
            AIProviderError("x"),
            MigrationError("x"),
            DDEVError("x"),
        ],
    )
    def test_every_error_inherits_the_base(self, exc: Exception) -> None:
        """Callers catch DrupalMCPError once; a stray plain Exception escapes."""
        assert isinstance(exc, DrupalMCPError)

    @pytest.mark.parametrize(
        "exc", [NotFoundError("x"), ValidationError("x")]
    )
    def test_specialised_errors_are_still_client_errors(self, exc: Exception) -> None:
        assert isinstance(exc, ClientError)

    def test_details_reach_specialised_errors(self) -> None:
        assert NotFoundError("x", {"id": 7}).details == {"id": 7}

    def test_client_error_accepts_a_status_override(self) -> None:
        assert ClientError("x", status_code=409).status_code == 409
