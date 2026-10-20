#!/usr/bin/env python3
"""Drupal MCP Server - FastMCP server for Drupal operations."""

import asyncio
import logging
import os
import uuid
from typing import Any

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from drupal_mcp_server import __version__
from drupal_mcp_server.access import RateLimitMiddleware, ReadOnlyRegistrar
from drupal_mcp_server.auth import AuthManager
from drupal_mcp_server.auth.mcp_oauth import DrupalOAuthProvider
from drupal_mcp_server.clients import DrushClient, GraphQLClient, JSONAPIClient
from drupal_mcp_server.codebase import CodebaseService
from drupal_mcp_server.config import get_settings
from drupal_mcp_server.services import AIService, MigrationService, SiteManager
from drupal_mcp_server.tools import (
    accessibility,
    ai,
    analysis,
    code_audit,
    codebase,
    comments,
    commerce,
    contact,
    content,
    database,
    devops,
    drupal_org,
    exports,
    feeds,
    fields,
    headless,
    layout_builder,
    media_enhanced,
    menus,
    metatag,
    migration,
    moderation,
    module_dev,
    multilingual,
    paragraphs,
    pathauto,
    performance,
    redirects,
    revisions,
    scheduler,
    search_api,
    security_audit,
    status,
    taxonomy,
    testing,
    theme_analysis,
    theme_dev,
    users,
    views,
    webform,
)
from drupal_mcp_server.tools import config as config_tools

logger = logging.getLogger(__name__)

# Tool modules, in registration order. Order is load-bearing for the live
# sweep: tools share local fixture paths (the sweep's /tmp/sweep-file.txt,
# for example), so reordering modules changes which tool creates a path
# before another answers about it.
TOOLS = [
    analysis, migration, content, config_tools, devops, ai, taxonomy, users,
    database, views, paragraphs, menus, fields, revisions, redirects,
    scheduler, code_audit, codebase, security_audit, status, drupal_org,
    moderation, module_dev, theme_dev, layout_builder, search_api,
    multilingual, media_enhanced, pathauto, metatag, commerce, webform,
    headless, testing, accessibility, performance, contact, comments, feeds,
    exports, theme_analysis,
]


def _input_schema_of(tool: Any) -> dict[str, Any]:
    """Read a tool's input schema across the names the SDKs have used.

    FastMCP's own ``FunctionTool`` calls it ``parameters``, while the
    client-side ``Tool`` has shipped as both ``inputSchema`` and
    ``input_schema``. Probing only the latter two meant ``/mcp/tools/list``
    answered with an empty schema for all 366 tools, so a client using that
    endpoint could not build a single request.
    """
    for attr in ("input_schema", "inputSchema", "parameters"):
        value = getattr(tool, attr, None)
        if isinstance(value, dict) and value:
            return value
    return {}


def _registrar_for(mcp: FastMCP, settings: Any) -> Any:
    """The object tool modules register against.

    In read-only mode the registrar drops every writing tool at
    decoration time: a dropped tool never enters the registry, so
    ``tools/list`` cannot advertise it and a call by name is an unknown
    tool rather than a refused call (which would confirm the name).
    """
    if getattr(settings, "MCP_READ_ONLY", False):
        return ReadOnlyRegistrar(mcp)
    return mcp


def create_server(auth_manager: AuthManager | None = None) -> FastMCP:
    """Create and configure the FastMCP server."""
    settings = get_settings()
    if auth_manager is None:
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
    codebase_service = CodebaseService(
        root=settings.DRUPAL_ROOT, modules_path=settings.DRUPAL_MODULES_PATH,
    )
    mcp = FastMCP(
        name=settings.MCP_SERVER_NAME,
        version=__version__,
        instructions="Drupal MCP Server - JSON:API, GraphQL, Drush, AI-powered migration.",
    )
    registrar = _registrar_for(mcp, settings)
    for module in TOOLS:
        module.register_tools(
            registrar, jsonapi_client=jsonapi_client, graphql_client=graphql_client,
            drush_client=drush_client, ai_service=ai_service, site_manager=site_manager,
            migration_service=migration_service, codebase_service=codebase_service,
        )
    if isinstance(registrar, ReadOnlyRegistrar):
        logger.info(
            "read-only mode (MCP_READ_ONLY): %d tools exposed, %d writing tools hidden",
            len(registrar.registered),
            len(registrar.dropped),
        )
    
    # Add dynamic tool discovery endpoint
    @mcp.custom_route("/mcp/tools/list", methods=["GET"])
    async def list_tools_endpoint(request: Request) -> JSONResponse:
        # Require authentication for tool listing
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "Authentication required"}, status_code=401)
        tools = await mcp.list_tools()
        return JSONResponse({
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": _input_schema_of(tool),
                }
                for tool in tools
            ]
        })
    
    # Add per-session scope management endpoints
    @mcp.custom_route("/mcp/session/start", methods=["POST"])
    async def start_session(request: Request) -> JSONResponse:
        """Start a new authenticated session with optional role/scopes."""
        body = await request.json()
        role = body.get("role", "authenticated")
        scopes = body.get("scopes")
        
        session_id = str(uuid.uuid4())
        
        oauth_provider = getattr(mcp, "_oauth_provider", None)
        if oauth_provider and isinstance(oauth_provider, DrupalOAuthProvider):
            if scopes:
                oauth_provider.set_session_scopes(session_id, scopes)
            else:
                oauth_provider.set_session_scopes(session_id, oauth_provider.get_role_scopes(role))
        
        return JSONResponse({
            "session_id": session_id,
            "role": role,
            "scopes": oauth_provider.get_session_scopes(session_id) if oauth_provider else [],
        })
    
    @mcp.custom_route("/mcp/session/{session_id}/scopes", methods=["GET"])
    async def get_session_scopes(request: Request) -> JSONResponse:
        """Get scopes for a session."""
        session_id = request.path_params["session_id"]
        oauth_provider = getattr(mcp, "_oauth_provider", None)
        if oauth_provider and isinstance(oauth_provider, DrupalOAuthProvider):
            scopes = oauth_provider.get_session_scopes(session_id)
            return JSONResponse({"session_id": session_id, "scopes": scopes})
        return JSONResponse({"error": "No OAuth provider"}, status_code=500)
    
    @mcp.custom_route("/mcp/session/{session_id}/scopes", methods=["PUT"])
    async def update_session_scopes(request: Request) -> JSONResponse:
        """Update scopes for a session."""
        session_id = request.path_params["session_id"]
        body = await request.json()
        scopes = body.get("scopes", [])
        
        oauth_provider = getattr(mcp, "_oauth_provider", None)
        if oauth_provider and isinstance(oauth_provider, DrupalOAuthProvider):
            oauth_provider.set_session_scopes(session_id, scopes)
            return JSONResponse({"session_id": session_id, "scopes": oauth_provider.get_session_scopes(session_id)})
        return JSONResponse({"error": "No OAuth provider"}, status_code=500)
    
    @mcp.custom_route("/mcp/scopes", methods=["GET"])
    async def list_available_scopes(request: Request) -> JSONResponse:
        """List all available scopes."""
        oauth_provider = getattr(mcp, "_oauth_provider", None)
        if oauth_provider and isinstance(oauth_provider, DrupalOAuthProvider):
            return JSONResponse({"scopes": oauth_provider.get_available_scopes()})
        return JSONResponse({"error": "No OAuth provider"}, status_code=500)
    
    @mcp.custom_route("/mcp/roles", methods=["GET"])
    async def list_roles(request: Request) -> JSONResponse:
        """List available roles and their default scopes."""
        oauth_provider = getattr(mcp, "_oauth_provider", None)
        if oauth_provider and isinstance(oauth_provider, DrupalOAuthProvider):
            roles = {role: oauth_provider.get_role_scopes(role) for role in oauth_provider.ROLE_SCOPES}
            return JSONResponse({"roles": roles})
        return JSONResponse({"error": "No OAuth provider"}, status_code=500)
    
    return mcp


async def _login_session(auth_manager: AuthManager) -> None:
    """Log in to Drupal and cache a CSRF token before the server starts."""
    await auth_manager.ensure_session()


def _require_network_auth(settings: Any, transport: str) -> None:
    """Refuse to serve command-execution tools over a socket without auth.

    The tool surface runs drush, composer and shell commands. On stdio that
    is whoever started the server; over HTTP it is everyone who can reach
    the bind address, so an unauthenticated network listener here is a
    remote code execution endpoint by construction. OAuth configuration is
    the intended path; MCP_ALLOW_INSECURE_HTTP is the deliberate mistake.
    """
    if transport not in ("http", "sse", "streamable-http"):
        return
    if getattr(settings, "DRUPAL_OAUTH_CLIENT_ID", None):
        return
    if getattr(settings, "MCP_ALLOW_INSECURE_HTTP", False) or os.getenv(
        "MCP_ALLOW_INSECURE_HTTP"
    ):
        return
    raise SystemExit(
        f"MCP_TRANSPORT={transport} serves tools that execute drush, composer "
        "and shell commands, and no OAuth client is configured "
        "(DRUPAL_OAUTH_CLIENT_ID/CLIENT_SECRET/TOKEN_URL), so the server "
        "refuses to bind. Configure OAuth, use the default stdio transport, "
        "or set MCP_ALLOW_INSECURE_HTTP=1 to serve unauthenticated - sane "
        "only on the default loopback MCP_HOST behind a trusted network."
    )


def _http_middleware(settings: Any) -> list[Middleware]:
    """Per-client request budget for the HTTP transports, when configured.

    Applies to every route the app serves — MCP endpoints, custom routes
    and the OAuth token endpoint alike — because it sits at the ASGI
    edge of FastMCP's HTTP app. ``mcp.run()`` forwards it through
    ``run_http_async`` to the app builder.
    """
    rate = int(getattr(settings, "MCP_RATE_LIMIT", 0) or 0)
    if rate <= 0:
        return []
    return [Middleware(RateLimitMiddleware, requests_per_minute=rate)]


def _oauth_provider_for(settings: Any, auth_manager: Any) -> Any:
    """Pick the MCP OAuth posture: proxy delegation or in-process (ADR 0005).

    Delegation is the opt-in networked mode: issuance forwarded to
    Drupal's simple_oauth server, presented tokens validated per
    request. The default remains the in-process authorization server,
    which works with no Drupal reachable.
    """
    if getattr(settings, "DRUPAL_OAUTH_DELEGATE", False):
        from drupal_mcp_server.auth.delegation import delegate_provider

        provider = delegate_provider(settings)
        logger.info(
            "OAuth delegation (ADR 0005): authorize/token forwarded to %s",
            settings.DRUPAL_OAUTH_TOKEN_URL,
        )
        return provider
    return auth_manager.get_mcp_oauth_provider(settings)


def run_server() -> None:
    settings = get_settings()

    # Establish a Drupal session up front so mutating tools carry a CSRF token.
    # Basic auth alone is rejected with 403 on Drupal's write endpoints. The
    # same AuthManager instance is handed to create_server() so the cookies and
    # CSRF token are visible to every client.
    auth_manager = AuthManager(settings)
    try:
        asyncio.run(_login_session(auth_manager))
    except Exception as exc:  # noqa: BLE001 - login must not block server startup
        logger.warning("Drupal session login failed: %s", exc)

    mcp = create_server(auth_manager)

    # Determine transport
    transport = os.getenv("MCP_TRANSPORT", settings.MCP_TRANSPORT)

    if transport in ("http", "sse", "streamable-http"):
        _require_network_auth(settings, transport)
        # FastMCP reads the provider off `self.auth` when it builds the HTTP
        # app. It was being passed to run() instead, which forwards unknown
        # keywords straight to run_http_async() and raised
        # "unexpected keyword argument 'auth'" before binding a socket - so
        # every HTTP transport died at startup and only stdio ever worked.
        oauth_provider = _oauth_provider_for(settings, auth_manager)
        if oauth_provider:
            mcp.auth = oauth_provider
        middleware = _http_middleware(settings)
        if middleware:
            logger.info(
                "rate limiting (MCP_RATE_LIMIT): %d requests/minute per client",
                settings.MCP_RATE_LIMIT,
            )
        mcp.run(
            transport=transport,  # type: ignore[arg-type]
            host=settings.MCP_HOST,
            port=settings.MCP_PORT,
            path=f"/{transport}" if transport != "http" else "/mcp",
            middleware=middleware,
        )
    else:
        # Stdio transport (default)
        mcp.run(transport="stdio")


if __name__ == "__main__":
    run_server()
