"""Read-only mode and HTTP rate limiting — the two network-surface controls.

Serving over a socket was made to require OAuth (0.3.3); these are the
controls an operator reaches for once a socket *is* authenticated: a
mode where the server cannot write anything, and a budget per client so
one misbehaving or compromised credential cannot drive the site (or the
token endpoint) at full speed.

The read-only classifier is a naming contract, verified empirically over
the real tool surface: the census test registers all 414 tools through
the registrar and pins the exposed count, so a tool that changes its
read/mutate posture — or a new tool with a read-shaped name that writes
— cannot slip through unreviewed.
"""

import asyncio
import json

import httpx
import pytest

from drupal_mcp_server.access import (
    RateLimitMiddleware,
    ReadOnlyRegistrar,
    is_read_only,
)
from drupal_mcp_server.server import TOOLS

# --- is_read_only -----------------------------------------------------------


def test_query_shaped_names_are_read_only() -> None:
    for name in (
        "list_vocabularies",
        "get_node",
        "db_tables",
        "db_count",
        "db_table_info",
        "security_audit",
        "csp_audit",
        "composer_audit",
        "find_deprecated_code",
        "search_entities",
        "module_search",
        "validate_migration",
        "inventory_modules",
        "analyze_d7_site",
        "accessibility_wcag_check",
        "accessibility_axe_scan",
        "sql_injection_scan",
        "performance_cache_stats",
        "views_list",
        "revision_diff",
        "codebase_file_read",
        "codebase_hooks_find",
        "theme_active",
        "module_popular",
        "jsonapi_resource_types",
        "database_updates",
        "diff_config",
    ):
        assert is_read_only(name), f"{name} should be read-only"


def test_write_and_exec_families_are_never_read_only() -> None:
    for name in (
        # Arbitrary command execution — the whole reason read-only mode exists.
        "drush_command",
        "drush_php_eval",
        "drush_updb",
        "ddev_exec",
        "lando_exec",
        "composer_install",
        "composer_require",
        "composer_update",
        "db_query",
        # Site mutations.
        "create_node",
        "update_node",
        "delete_node",
        "create_user",
        "block_user",
        "unblock_user",
        "delete_user",
        "assign_role",
        "remove_role",
        "config_set",
        "views_create",
        "views_update",
        "views_delete",
        "views_execute",
        "comment_approve",
        "revision_revert",
        "moderation_transition_execute",
        "language_enable",
        "language_disable",
        "performance_bigpipe_enable",
        # Local work and scaffolding.
        "module_create",
        "theme_create",
        "theme_debug_enable",
        "theme_template_override",
        "generate_migration_yaml",
        "generate_module_migration",
        "test_scaffold_behat",
        "test_run_phpunit",
        "export_config",
        "import_config",
        "backup_database",
        "acquia_deploy",
        "upload_media",
        "pathauto_generate",
        # Queues, cron, containers.
        "queue_run",
        "cron_run",
        "cache_clear",
        "cache_rebuild",
        "ddev_start",
        "ddev_stop",
        # Migration writes.
        "run_migration",
        "run_migration_wave",
        "migrate_records",
        "migrate_taxonomy",
        "sync_media_files",
        "rollback_migration",
    ):
        assert not is_read_only(name), f"{name} must not pass as read-only"


def test_search_api_mutations_are_denied_despite_the_search_prefix() -> None:
    """`search_` is a read-shaped prefix, but it heads the search_api
    mutation family — creating and clearing indexes is a write."""
    for name in (
        "search_api_facet_create",
        "search_api_index_clear",
        "search_api_index_create",
        "search_api_index_reindex",
        "search_api_index_update",
        "search_api_server_create",
        "search_api_server_disable",
        "search_api_server_enable",
    ):
        assert not is_read_only(name), f"{name} must not pass as read-only"
    # The family's readers still pass through their own suffixes.
    for name in (
        "search_api_facet_list",
        "search_api_index_get",
        "search_api_index_list",
        "search_api_server_get",
        "search_api_server_list",
    ):
        assert is_read_only(name), f"{name} is a read"


# --- ReadOnlyRegistrar ------------------------------------------------------


class _FakeMCP:
    """Collects the names registered through it, like the real tool manager."""

    def __init__(self) -> None:
        self.registered: list[str] = []

    def tool(self, *args, **kwargs):
        def decorate(fn):
            self.registered.append(fn.__name__)
            return fn

        return decorate

    def custom_route(self, *args, **kwargs):
        def decorate(fn):
            return fn

        return decorate


def _register_all(registrar, monkeypatch, tmp_path) -> list[str]:
    monkeypatch.setenv("DRUPAL_MCP_MIGRATION_DIR", str(tmp_path / "store"))
    for module in TOOLS:
        module.register_tools(registrar)
    return list(getattr(registrar, "registered", []))


def test_registrar_drops_mutating_tools_at_registration(
    monkeypatch, tmp_path
) -> None:
    """A dropped tool is never in the registry: tools/list cannot show it
    and calling it by name is an unknown tool, not a refused call."""
    fake = _FakeMCP()
    registrar = ReadOnlyRegistrar(fake)

    from drupal_mcp_server.tools import users

    monkeypatch.setenv("DRUPAL_MCP_MIGRATION_DIR", str(tmp_path / "store"))
    users.register_tools(registrar)

    assert "get_user_roles" in fake.registered
    for dangerous in ("block_user", "unblock_user", "delete_user"):
        assert dangerous not in fake.registered
        assert dangerous in registrar.dropped


def test_registrar_delegates_everything_else(monkeypatch, tmp_path) -> None:
    """Modules reach past .tool() for other server APIs (custom_route and
    friends); the registrar must forward them untouched."""
    fake = _FakeMCP()
    registrar = ReadOnlyRegistrar(fake)

    # Bound methods compare equal per access, not identical, so == here.
    assert registrar.custom_route == fake.custom_route
    with pytest.raises(AttributeError):
        _ = registrar.anything_at_all


def test_the_full_surface_census(monkeypatch, tmp_path) -> None:
    """Register all 414 tools through the registrar and pin the exposed
    set's size: a tool changing its read/mutate posture moves this count
    and must be classified deliberately."""
    fake = _FakeMCP()
    registrar = ReadOnlyRegistrar(fake)
    _register_all(registrar, monkeypatch, tmp_path)

    exposed = set(fake.registered)
    assert exposed == set(registrar.registered)
    total = len(registrar.registered) + len(registrar.dropped)
    assert total == 414, f"census covered {total} of 414 tools"

    # The command-execution surface is invisible in read-only mode.
    for dangerous in ("drush_command", "ddev_exec", "lando_exec", "db_query", "drush_php_eval"):
        assert dangerous in registrar.dropped
        assert dangerous not in exposed

    # Every write-shaped name is hidden, whatever its family.
    write_suffixes = (
        "_create", "_update", "_delete", "_remove", "_run", "_exec", "_set",
        "_enable", "_disable", "_revert", "_clear", "_rebuild", "_import",
        "_deploy", "_start", "_stop", "_place", "_approve", "_execute",
        "_rollout", "_reindex",
    )
    leaked = [n for n in exposed if n.endswith(write_suffixes)]
    assert leaked == [], f"write-shaped tools exposed in read-only mode: {leaked}"

    # And every exposed name is classified read-only by contract.
    misread = [n for n in exposed if not is_read_only(n)]
    assert misread == []

    # The read surface, pinned: 185 of 414. A count change means a tool
    # changed posture or a new one arrived — classify it deliberately.
    assert len(exposed) == 185, f"read-only surface moved to {len(exposed)} tools"


# --- RateLimitMiddleware ----------------------------------------------------


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


async def _ok_app(scope, receive, send) -> None:
    body = b'{"ok": true}'
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


def test_rate_limit_allows_the_burst_then_answers_429() -> None:
    clock = _Clock()
    app = RateLimitMiddleware(_ok_app, requests_per_minute=3, clock=clock)

    async def main():
        async with _client(app) as client:
            statuses = []
            for _ in range(4):
                response = await client.get("/mcp")
                statuses.append(response.status_code)
            return statuses, await client.get("/mcp")

    statuses, last = asyncio.run(main())
    # The first three pass, the fourth and fifth are refused.
    assert statuses == [200, 200, 200, 429]
    assert last.status_code == 429
    payload = json.loads(last.content)
    assert "rate limit exceeded" in payload["error"]
    assert payload["retry_after"] >= 1
    assert int(last.headers["retry-after"]) >= 1


def test_rate_limit_refills_over_time() -> None:
    clock = _Clock()
    app = RateLimitMiddleware(_ok_app, requests_per_minute=2, clock=clock)

    async def main():
        async with _client(app) as client:
            first = [await client.get("/mcp") for _ in range(2)]
            assert [r.status_code for r in first] == [200, 200]
            assert (await client.get("/mcp")).status_code == 429
            clock.advance(30)  # half a window: one token is back
            after = await client.get("/mcp")
            assert after.status_code == 200
            assert (await client.get("/mcp")).status_code == 429
            clock.advance(60)  # a full window: the bucket is full again
            refilled = [await client.get("/mcp") for _ in range(2)]
            assert [r.status_code for r in refilled] == [200, 200]

    asyncio.run(main())


def test_rate_limit_budget_headers_report_the_remaining_allowance() -> None:
    clock = _Clock()
    app = RateLimitMiddleware(_ok_app, requests_per_minute=5, clock=clock)

    async def main():
        async with _client(app) as client:
            remainings = []
            for _ in range(3):
                response = await client.get("/mcp")
                assert response.headers["x-ratelimit-limit"] == "5"
                remainings.append(int(response.headers["x-ratelimit-remaining"]))
            return remainings

    remainings = asyncio.run(main())
    assert remainings == [4, 3, 2]


def test_rate_limit_keys_isolate_clients_behind_one_address() -> None:
    """A credential being guessed should burn its own budget, not the
    shared address's; two tokens from one host are two buckets."""
    clock = _Clock()
    app = RateLimitMiddleware(_ok_app, requests_per_minute=2, clock=clock)

    async def main():
        async with _client(app) as client:
            exhausted = {"Authorization": "Bearer guess-1"}
            other = {"Authorization": "Bearer legit-token"}
            assert (await client.get("/mcp", headers=exhausted)).status_code == 200
            assert (await client.get("/mcp", headers=exhausted)).status_code == 200
            assert (await client.get("/mcp", headers=exhausted)).status_code == 429
            # Same address, different credential: unaffected.
            assert (await client.get("/mcp", headers=other)).status_code == 200
            # And the no-token key is its own bucket too.
            assert (await client.get("/mcp")).status_code == 200

    asyncio.run(main())


def test_rate_limit_covers_every_path_including_the_token_endpoint() -> None:
    clock = _Clock()
    app = RateLimitMiddleware(_ok_app, requests_per_minute=2, clock=clock)

    async def main():
        async with _client(app) as client:
            assert (await client.post("/token", json={})).status_code == 200
            assert (await client.get("/mcp")).status_code == 200
            third = await client.post("/token", json={})
            return third

    refused = asyncio.run(main())
    assert refused.status_code == 429, "the token endpoint shares the budget"


def test_rate_limit_zero_leaves_everything_alone() -> None:
    app = RateLimitMiddleware(_ok_app, requests_per_minute=0, clock=_Clock())

    async def main():
        async with _client(app) as client:
            return [await client.get("/mcp") for _ in range(50)]

    responses = asyncio.run(main())
    assert all(r.status_code == 200 for r in responses)
    assert "x-ratelimit-limit" not in responses[0].headers


def test_stale_keys_are_pruned_so_a_long_runner_cannot_grow_forever() -> None:
    clock = _Clock()
    app = RateLimitMiddleware(_ok_app, requests_per_minute=1, clock=clock)

    async def main():
        async with _client(app) as client:
            for i in range(4100):
                clock.advance(61)  # each client arrives after the last refilled
                await client.get("/mcp", headers={"Authorization": f"Bearer t{i}"})
            return len(app._buckets)

    buckets = asyncio.run(main())
    assert buckets <= 4096, "bucket table grew without bound"


# --- wiring -----------------------------------------------------------------


def test_http_middleware_is_only_built_when_configured() -> None:
    from drupal_mcp_server.access import RateLimitMiddleware as RL
    from drupal_mcp_server.server import _http_middleware

    class _Settings:
        MCP_RATE_LIMIT = 0

    assert _http_middleware(_Settings()) == []

    class _Limited:
        MCP_RATE_LIMIT = 120

    middleware = _http_middleware(_Limited())
    assert len(middleware) == 1
    assert middleware[0].cls is RL
    assert middleware[0].kwargs == {"requests_per_minute": 120}


def test_registrar_selection_follows_the_setting() -> None:
    from drupal_mcp_server.server import _registrar_for

    class _Off:
        MCP_READ_ONLY = False

    class _On:
        MCP_READ_ONLY = True

    fake = _FakeMCP()
    assert _registrar_for(fake, _Off()) is fake
    registrar = _registrar_for(fake, _On())
    assert isinstance(registrar, ReadOnlyRegistrar)
    assert registrar._mcp is fake
