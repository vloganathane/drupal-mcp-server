"""Session (cookie + CSRF) authentication for Drupal.

Drupal protects every mutating endpoint behind a per-session CSRF token.
Basic auth alone is sufficient for reads but is rejected with 403 on writes,
so tools that create/update/delete content must hold a real session.

Flow:
    1. POST /user/login with the credentials to obtain a session cookie.
    2. GET /session/token on that session to obtain the CSRF token.
    3. Send both the cookie and X-CSRF-Token on every mutating request.
"""

import httpx


class SessionAuth:
    """Cookie + CSRF token auth for Drupal write operations."""

    def __init__(self, base_url: str, username: str, password: str,
                 verify_ssl: bool = True, timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._verify_ssl = verify_ssl
        self._timeout = timeout
        self._cookies: dict[str, str] = {}
        self._csrf: str | None = None
        self._logged_in = False

    async def login(self) -> None:
        """Establish a session and fetch a CSRF token.

        The login POST is deliberately not followed past its redirect. Drupal
        answers a good login with 303 to the account page, built from the
        scheme and host it saw the request arrive on -- its own idea of its
        base URL, not the client's. Following that turns a successful login
        into a failure whenever the two disagree: reached on a port-mapped
        HTTPS endpoint the site reported itself as plain `http`, so the
        redirect was fetched as HTTP against a TLS port, nginx answered 400,
        and the session cookie the same response had just issued was thrown
        away. Every write then silently fell back to basic auth, which
        Drupal's mutating endpoints reject.

        Only the redirect's status and the cookie it sets are wanted here;
        the page it points at is the site's business.

        Raises:
            RuntimeError: If login fails or no token is issued.
        """
        async with httpx.AsyncClient(
            verify=self._verify_ssl,
            timeout=self._timeout,
            follow_redirects=False,
        ) as client:
            resp = await client.post(
                f"{self._base_url}/user/login",
                data={
                    "name": self._username,
                    "pass": self._password,
                    "form_id": "user_login_form",
                    "op": "Log in",
                },
            )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Drupal login failed (HTTP {resp.status_code}); "
                    "check DRUPAL_USERNAME and DRUPAL_PASSWORD"
                )

            # A 3xx here is the success path, and a refused login is a 200
            # re-rendering the form without setting a cookie -- so this check,
            # not the status above, is what actually rejects bad credentials.
            self._cookies = {k: v for k, v in client.cookies.items()}
            if not self._cookies:
                raise RuntimeError(
                    "Drupal login returned no session cookie; "
                    "the site may not expose /user/login, or the credentials "
                    "were refused."
                )

            token_resp = await client.get(
                f"{self._base_url}/session/token",
                cookies=self._cookies,
            )
            if token_resp.status_code >= 400:
                raise RuntimeError("Failed to fetch Drupal CSRF token")
            self._csrf = token_resp.text.strip() or None
            if not self._csrf:
                raise RuntimeError("Drupal issued an empty CSRF token")

            self._logged_in = True

    def get_headers(self) -> dict[str, str]:
        """Headers for a mutating request, including the CSRF token."""
        if not self._logged_in:
            return {}
        headers = {}
        if self._csrf:
            headers["X-CSRF-Token"] = self._csrf
        return headers

    def get_cookies(self) -> dict[str, str]:
        """Session cookies to attach to a request."""
        return dict(self._cookies) if self._logged_in else {}

    def is_logged_in(self) -> bool:
        """Whether a session has been established."""
        return self._logged_in
