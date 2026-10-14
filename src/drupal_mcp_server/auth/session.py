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

        Raises:
            RuntimeError: If login fails or no token is issued.
        """
        async with httpx.AsyncClient(
            verify=self._verify_ssl,
            timeout=self._timeout,
            follow_redirects=True,
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

            # Cookies are set across the redirect chain, so read the client's
            # accumulated jar rather than the final response's own set.
            self._cookies = {k: v for k, v in client.cookies.items()}
            if not self._cookies:
                raise RuntimeError(
                    "Drupal login returned no session cookie; "
                    "the site may not expose /user/login."
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
