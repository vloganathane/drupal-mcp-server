"""Base HTTP client for Drupal REST endpoints."""

from typing import Any, Dict, Optional

import httpx


class DrupalBaseClient:
    """Base client for Drupal REST endpoints (JSON:API, GraphQL)."""

    def __init__(self, settings: Any, auth_manager: Any = None):
        self.settings = settings
        self.auth_manager = auth_manager
        self._base_url = settings.DRUPAL_BASE_URL.rstrip("/")
        self._timeout = 60

    def _build_url(self, endpoint: str) -> str:
        return f"{self._base_url}/{endpoint.lstrip('/')}"

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.auth_manager:
            headers.update(self.auth_manager.get_headers())
        return headers

    async def get(
        self,
        endpoint: str,
        params: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Perform a GET request to the Drupal endpoint."""
        url = self._build_url(endpoint)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(url, headers=self._headers(), params=params)
        response.raise_for_status()
        return response.json()

    async def post(
        self,
        endpoint: str,
        data: Dict[str, Any] = None,
        json_body: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Perform a POST request to the Drupal endpoint."""
        url = self._build_url(endpoint)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                url, headers=self._headers(), json=json_body or data, params=data
            )
        response.raise_for_status()
        return response.json()

    async def patch(self, endpoint: str, json_body: Dict[str, Any]) -> Dict[str, Any]:
        """Perform a PATCH request to the Drupal endpoint."""
        url = self._build_url(endpoint)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.patch(url, headers=self._headers(), json=json_body)
        response.raise_for_status()
        return response.json()

    async def delete(self, endpoint: str) -> Dict[str, Any]:
        """Perform a DELETE request to the Drupal endpoint."""
        url = self._build_url(endpoint)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.delete(url, headers=self._headers())
        response.raise_for_status()
        return response.json()