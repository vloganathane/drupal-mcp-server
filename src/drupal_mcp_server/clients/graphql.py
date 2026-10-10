"""GraphQL client for Drupal."""
from typing import Any, Dict, Optional
from .base import DrupalBaseClient


class GraphQLClient(DrupalBaseClient):
    """Client for Drupal GraphQL endpoints."""

    def __init__(self, settings: Any, auth_manager: Any = None):
        super().__init__(settings, auth_manager)
        self._gql_path = settings.DRUPAL_GRAPHQL_PATH.strip("/")

    async def execute(self, query: str, variables: Optional[Dict] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        return await self.post(self._gql_path, json_body=payload)
