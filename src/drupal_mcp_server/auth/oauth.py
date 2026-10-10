"""OAuth2 client credentials authentication for Drupal."""
from typing import Dict, Optional
import httpx


class OAuth2Auth:
    def __init__(self, client_id: str, client_secret: str, token_url: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._access_token: Optional[str] = None

    async def _fetch_token(self) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self._token_url, data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            })
        resp.raise_for_status()
        self._access_token = resp.json()["access_token"]
        return self._access_token

    def get_headers(self) -> Dict[str, str]:
        # Token fetched lazily on first real request via AuthManager
        if self._access_token:
            return {"Authorization": f"Bearer {self._access_token}"}
        return {}
