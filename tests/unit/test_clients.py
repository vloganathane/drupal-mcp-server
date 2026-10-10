"""Unit tests for Drupal clients."""
import pytest


def test_jsonapi_client_exists():
    from drupal_mcp_server.clients import JSONAPIClient
    assert JSONAPIClient is not None
