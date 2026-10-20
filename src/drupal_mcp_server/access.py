"""Network-surface controls: read-only mode and per-client rate limiting.

Serving over a socket came to require OAuth in 0.3.3; these are the
controls an operator reaches for once a socket *is* authenticated — a
mode where this server cannot write anything, and a request budget so
one misbehaving or compromised credential cannot drive the site (or the
token endpoint) at full speed.
"""

import hashlib
import json
import math
import time
from collections.abc import Callable
from typing import Any

# The read-only contract is naming: a tool is exposed only when its name
# starts with a query verb or ends with a query noun. That makes the mode
# fail-closed by construction — a new tool stays hidden until someone
# classifies it, because the failure mode of a wrong allow is a write and
# the failure mode of a wrong deny is an operator turning the mode off.
_READ_PREFIXES = (
    "list_",
    "get_",
    "find_",
    "search_",
    "validate_",
    "explain_",
    "inventory_",
    "analyze_",
)
_READ_SUFFIXES = (
    "_list",
    "_get",
    "_info",
    "_status",
    "_audit",
    "_analyze",
    "_inventory",
    "_check",
    "_stats",
    "_count",
    "_show",
    "_tables",
    "_view",
    "_validate",
    "_preview",
    "_diff",
    "_scan",
    "_find",
    "_search",
    "_read",
)

# Readers whose names carry no query shape — noun-named introspection and
# status tools, each verified against its source before being listed.
_READ_EXTRA = frozenset(
    {
        "available_updates",  # status-report lookup
        "code_quality_report",  # runs linters over local code, writes nothing
        "codebase_directory_tree",  # local tree listing
        "content_moderation_dashboard",
        "database_updates",  # updatedb:status — "read-only; runs nothing"
        "diff_config",  # config:export to /tmp scratch, then diff
        "jsonapi_include_optimize",
        "jsonapi_resource_types",
        "jsonapi_sparse_fieldsets",
        "module_compatibility",  # drupal.org lookups
        "module_dependencies",
        "module_popular",
        "module_recommendation",
        "module_versions",
        "project_usage",
        "release_history",
        "template_suggestions",
        "test_coverage_report",
        "theme_active",  # config:get
        "theme_blocks",
        "theme_lint_twig",  # lints local Twig, writes nothing
        "theme_regions",
        "theme_template_overrides",
        "theme_templates",
    }
)

# Names a read-shaped prefix would otherwise admit. `search_` heads the
# search_api mutation family — creating, reindexing, clearing, enabling
# and disabling are writes; the family's readers still pass on suffixes.
_PATTERN_DENY = frozenset(
    {
        "search_api_facet_create",
        "search_api_index_clear",
        "search_api_index_create",
        "search_api_index_reindex",
        "search_api_index_update",
        "search_api_server_create",
        "search_api_server_disable",
        "search_api_server_enable",
    }
)


def is_read_only(tool_name: str) -> bool:
    """Whether a tool name reads as a query rather than a write."""
    if tool_name in _PATTERN_DENY:
        return False
    if tool_name in _READ_EXTRA:
        return True
    return tool_name.startswith(_READ_PREFIXES) or tool_name.endswith(_READ_SUFFIXES)


class ReadOnlyRegistrar:
    """Registration view that never registers a writing tool.

    A dropped tool never enters the registry, so ``tools/list`` cannot
    advertise it and a call by name fails as an unknown tool — not as a
    refused call, which would confirm the name exists.
    """

    def __init__(self, mcp: Any) -> None:
        self._mcp = mcp
        self.registered: list[str] = []
        self.dropped: list[str] = []

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        def decorate(fn: Any) -> Any:
            if is_read_only(fn.__name__):
                self.registered.append(fn.__name__)
                return self._mcp.tool(*args, **kwargs)(fn)
            self.dropped.append(fn.__name__)
            return fn

        return decorate

    def __getattr__(self, name: str) -> Any:
        # Anything that is not registration (custom_route, instructions, ...)
        # reaches the wrapped server untouched.
        return getattr(self._mcp, name)


class RateLimitMiddleware:
    """Token-bucket request budget per client, as pure ASGI.

    Keyed by bearer token when the request carries one — a credential
    being guessed should burn its own budget, not the shared address of
    every client behind it — else by client IP. The bucket holds
    ``requests_per_minute`` requests and refills continuously at that
    rate: bursts up to one window pass, sustained traffic is level.
    """

    _MAX_BUCKETS = 4096
    _STALE_AFTER = 600.0

    def __init__(
        self,
        app: Any,
        requests_per_minute: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self.rate = int(requests_per_minute)
        self._clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}

    @staticmethod
    def _key(scope: Any) -> str:
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        authorization = headers.get("authorization", "")
        if authorization[:7].lower() == "bearer " and authorization[7:].strip():
            digest = hashlib.sha256(authorization[7:].strip().encode()).hexdigest()
            return f"token:{digest[:16]}"
        client = scope.get("client")
        return f"ip:{client[0]}" if client else "ip:unknown"

    def _consume(self, key: str) -> tuple[float, int]:
        """Spend one request; answer (retry_after_seconds, remaining)."""
        now = self._clock()
        tokens, last = self._buckets.get(key, (float(self.rate), now))
        tokens = min(float(self.rate), tokens + (now - last) * self.rate / 60.0)
        if tokens >= 1.0:
            self._buckets[key] = (tokens - 1.0, now)
            return 0.0, int(tokens - 1.0)
        self._buckets[key] = (tokens, now)
        return (1.0 - tokens) * 60.0 / self.rate, 0

    def _prune(self) -> None:
        """Drop refilled and long-idle buckets once the table grows.

        Every distinct client address or guessed token is a key, so the
        table must not grow with the internet.
        """
        if len(self._buckets) <= self._MAX_BUCKETS:
            return
        now = self._clock()
        for key in [
            key
            for key, (tokens, last) in self._buckets.items()
            if tokens >= self.rate or now - last >= self._STALE_AFTER
        ]:
            del self._buckets[key]

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or self.rate <= 0:
            await self.app(scope, receive, send)
            return

        retry_after, remaining = self._consume(self._key(scope))
        if retry_after > 0:
            wait = max(1, math.ceil(retry_after))
            body = json.dumps(
                {
                    "error": f"rate limit exceeded: {self.rate} requests/minute",
                    "retry_after": wait,
                }
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        (b"retry-after", str(wait).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            self._prune()
            return

        async def send_with_budget(message: Any) -> None:
            if message["type"] == "http.response.start":
                message = {
                    **message,
                    "headers": list(message.get("headers", []))
                    + [
                        (b"x-ratelimit-limit", str(self.rate).encode()),
                        (b"x-ratelimit-remaining", str(remaining).encode()),
                    ],
                }
            await send(message)

        await self.app(scope, receive, send_with_budget)
        self._prune()
