#!/usr/bin/env python3
"""Drupal MCP Server - FastMCP server for Drupal operations."""

from fastmcp import FastMCP
from drupal_mcp_server.config import get_settings
from drupal_mcp_server.auth import AuthManager
from drupal_mcp_server.clients import JSONAPIClient, GraphQLClient, DrushClient
from drupal_mcp_server.services import AIService, SiteManager, MigrationService
from drupal_mcp_server.tools import analysis, migration, content, config as config_tools, devops, ai


def create_server() -> FastMCP:
    """Create and configure the FastMCP server."""
    settings = get_settings()
    auth_manager = AuthManager(settings)
    jsonapi_client = JSONAPIClient(settings, auth_manager)
    graphql_client = GraphQLClient(settings, auth_manager)
    drush_client = DrushClient(settings)
    ai_service = AIService(settings)
    site_manager = SiteManager(settings)
    migration_service = MigrationService(
        settings=settings, jsonapi_client=jsonapi_client,
        drush_client=drush_client, ai_service=ai_service, site_manager=site_manager,
    )
    mcp = FastMCP(
        name="drupal-mcp-server",
        instructions="Drupal MCP Server - JSON:API, GraphQL, Drush, AI-powered migration.",
    )
    for module in [analysis, migration, content, config_tools, devops, ai]:
        module.register_tools(
            mcp, jsonapi_client=jsonapi_client, graphql_client=graphql_client,
            drush_client=drush_client, ai_service=ai_service, site_manager=site_manager,
        )
    return mcp


def main():
    mcp = create_server()
    mcp.run()

if __name__ == "__main__":
    main()