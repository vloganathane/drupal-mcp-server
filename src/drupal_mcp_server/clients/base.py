"""Base HTTP client for Drupal REST endpoints."""

from typing import Any

import httpx


class DrupalBaseClient:
    """Base client for Drupal REST endpoints (JSON:API, GraphQL)."""

    # Media type for requests. JSON:API rejects application/json with 415.
    _media_type = "application/json"

    def __init__(self, settings: Any, auth_manager: Any = None):
        self.settings = settings
        self.auth_manager = auth_manager
        self._base_url = settings.DRUPAL_BASE_URL.rstrip("/")
        self._timeout = 60
        self._verify_ssl = bool(getattr(settings, "DRUPAL_VERIFY_SSL", True))

    def _cookies(self) -> dict[str, str]:
        """Session cookies from SessionAuth, if one is configured."""
        mgr = self.auth_manager
        if mgr is None:
            return {}
        getter = getattr(mgr, "get_session_cookies", None)
        if getter is None:
            return {}
        return getter()

    def _client(self) -> httpx.AsyncClient:
        """Build an AsyncClient honouring the DRUPAL_VERIFY_SSL setting.

        Local dev environments (DDEV, Lando) serve self-signed certs, so this
        must be configurable or every request fails with CERTIFICATE_VERIFY_FAILED.

        Session cookies are attached here so reads see the same authenticated
        session as writes.
        """
        return httpx.AsyncClient(
            timeout=self._timeout,
            verify=self._verify_ssl,
            cookies=self._cookies(),
        )

    def _build_url(self, endpoint: str) -> str:
        return f"{self._base_url}/{endpoint.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": self._media_type,
            "Content-Type": self._media_type,
        }
        if self.auth_manager:
            headers.update(self.auth_manager.get_headers())
        return headers

    @staticmethod
    def _raise(response: httpx.Response) -> None:
        """Raise for status, preserving Drupal's JSON:API error body.

        ``raise_for_status()`` alone reports only the status code, which hides
        the actionable ``errors[].detail`` Drupal returns on validation failures.
        """
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip()
            if detail:
                # Drupal returns HTML for some 40x pages; keep it short.
                detail = detail[:400]
                raise httpx.HTTPStatusError(
                    f"{exc} — {detail}", request=exc.request, response=exc.response
                ) from None
            raise

    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Perform an HTTP request and return the raw response."""
        url = self._build_url(endpoint)
        async with self._client() as client:
            return await client.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json_body,
                data=data,
            )

    async def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Perform a GET request to the Drupal endpoint."""
        response = await self.request("GET", endpoint, params=params)
        self._raise(response)
        data = response.json()
        return data  # type: ignore[no-any-return]

    async def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Perform a POST request to the Drupal endpoint."""
        response = await self.request("POST", endpoint, json_body=json_body or data)
        self._raise(response)
        data = response.json()
        return data

    async def patch(self, endpoint: str, json_body: dict[str, Any]) -> dict[str, Any] | list[Any]:
        """Perform a PATCH request to the Drupal endpoint."""
        response = await self.request("PATCH", endpoint, json_body=json_body)
        self._raise(response)
        data = response.json()
        return data  # type: ignore[no-any-return]

    async def delete(self, endpoint: str) -> dict[str, Any] | list[Any]:
        """Perform a DELETE request to the Drupal endpoint.

        Drupal answers DELETE with 204 No Content, so an empty body is normal
        and must not be parsed as JSON.
        """
        response = await self.request("DELETE", endpoint)
        self._raise(response)
        return {"deleted": True, "status_code": response.status_code}
