"""JSON:API client for Drupal."""
from typing import Any, Dict, Optional
from .base import DrupalBaseClient


class JSONAPIClient(DrupalBaseClient):
    """Client for Drupal JSON:API endpoints."""

    def __init__(self, settings: Any, auth_manager: Any = None):
        super().__init__(settings, auth_manager)
        self._api_path = settings.DRUPAL_JSONAPI_PATH.strip("/")

    def _jsonapi_url(self, resource: str) -> str:
        return f"{self._api_path}/{resource.lstrip('/')}"

    async def get_resource(self, resource_type: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        return await self.get(self._jsonapi_url(resource_type), params=params)

    async def get_by_id(self, resource_type: str, uuid: str) -> Dict[str, Any]:
        return await self.get(self._jsonapi_url(f"{resource_type}/{uuid}"))

    async def create_resource(self, resource_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self.post(self._jsonapi_url(resource_type), json_body=data)

    async def update_resource(self, resource_type: str, uuid: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self.patch(self._jsonapi_url(f"{resource_type}/{uuid}"), json_body=data)

    async def delete_resource(self, resource_type: str, uuid: str) -> Dict[str, Any]:
        return await self.delete(self._jsonapi_url(f"{resource_type}/{uuid}"))
