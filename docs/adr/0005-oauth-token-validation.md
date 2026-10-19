# ADR 0005: Where MCP OAuth Tokens Are Validated

## Status
Accepted

## Date
2026-10-19

## Context

ADR 0004 introduced `DrupalOAuthProvider` for HTTP transport. An audit of
the OAuth surface (2026-10-19) established what actually happens:

- `get_mcp_oauth_provider()` passes `DRUPAL_OAUTH_CLIENT_ID`,
  `DRUPAL_OAUTH_CLIENT_SECRET` and `DRUPAL_OAUTH_TOKEN_URL` into the
  provider, which stores them as `_drupal_client_id`,
  `_drupal_client_secret` and `_drupal_token_url` — **and never reads
  them again**.
- Authorization codes and access tokens are generated **in process**:
  `authorize()` / `exchange_authorization_code()` self-issue, and
  `load_access_token()` validates against an in-memory dict. Nothing
  calls Drupal to authorize an MCP client, despite the docstrings that
  say "redirect to Drupal OAuth".
- The same three settings do a separate, real job: the **outbound**
  client-credentials leg (`AuthManager._fetch_oauth_token` POSTs
  `grant_type=client_credentials` to `DRUPAL_OAUTH_TOKEN_URL` so tool
  calls carry a bearer to Drupal).
- Consequences of the in-process half: tokens die with the process
  (a multi-worker deployment would reject its own siblings), Drupal-side
  revocation and roles never reach the MCP side, and the `ROLE_SCOPES`
  table plus `get_role_scopes()` are decorative — nothing assigns a role.
- The session-scope custom routes (`/mcp/scopes`, `/mcp/roles`,
  `/mcp/session/{id}/scopes`) read `mcp._oauth_provider`, an attribute
  FastMCP never sets, so they answer 500 today. Wiring them to `mcp.auth`
  instead would activate an *unauthenticated* scope-mutation route, so
  they must not be "fixed" blindly.
- Enforcement itself is real, and now tested at three layers: unit
  (issue / exchange / refresh / replay), ASGI integration (401
  unauthenticated, 200 issued, 401 forged, 403 missing scope), and a
  real socket (discovery 200, unauthenticated 401 carrying the
  production scope challenge).

## Decision

Serve the in-process authorization server as the default, and document
the credential split honestly:

- `DRUPAL_OAUTH_CLIENT_ID` is the HTTP-transport guard's
  deliberate-intent switch; the enforcement it gates is FastMCP's bearer
  middleware, not Drupal.
- `DRUPAL_OAUTH_CLIENT_SECRET` / `DRUPAL_OAUTH_TOKEN_URL` belong to the
  outbound client-credentials leg.
- No code path claims Drupal delegation until one of the options below
  is implemented; the `_drupal_*` attributes, `ROLE_SCOPES` and the
  `_oauth_provider` routes are recorded as follow-up — remove or wire,
  never wire without an auth decision.

When a multi-user networked deployment needs Drupal-side identity, pick
one of:

- **Introspection** — validate presented tokens at Drupal's
  `/oauth/token/introspect` (simple_oauth). Only works for tokens Drupal
  issued, so issuance must delegate too, and each validation is a
  network hop (cacheable).
- **Proxy delegation** — FastMCP's OAuth proxy pattern: MCP clients keep
  standard discovery/DCR/PKCE against us, while authorize/token requests
  are forwarded to Drupal's simple_oauth AS. Needs the module enabled
  and an OAuth client registered in Drupal.
- **JWT verification** — Drupal signs access tokens; validate the
  signature via JWKS locally. No per-request hop; revocation lands at
  token TTL instead of immediately.

Recommended for that mode: proxy delegation for issuance plus local JWT
verification, with introspection as the fallback. None of it is required
for the default posture — stdio, or loopback HTTP behind the guard.

## Consequences

### Positive
- The served default works with no Drupal reachable and no extra
  modules enabled.
- Documentation and the guard's refusal message match observed
  behaviour; the credential split is explicit.
- Enforcement is pinned by tests at three layers, including the
  production scope requirement over a real socket.

### Negative
- MCP tokens cannot be revoked from Drupal, and roles never influence
  scopes — by design until delegation is chosen.
- Multi-worker HTTP deployments are unsupported (per-process token
  dicts).
- Dead scaffolding (`_drupal_*`, `ROLE_SCOPES`, session routes) remains
  until its follow-up lands.

## Alternatives Considered

- **Delegate to Drupal now** — rejected for the default: couples startup
  to site reachability and the simple_oauth module, and breaks offline
  local use, which is the primary mode.
- **A dedicated guard flag (`MCP_REQUIRE_AUTH`)** — rejected as a
  parallel knob; `DRUPAL_OAUTH_CLIENT_ID` already marks the deliberate
  intent and is the setting operators know.
- **Leave the documentation vague** — rejected: "OAuth is configured"
  implied Drupal-validated tokens that do not exist.
