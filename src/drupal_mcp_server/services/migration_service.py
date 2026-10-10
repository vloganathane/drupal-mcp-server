"""Migration orchestration service."""
from typing import Any


class MigrationService:
    """Orchestrates multi-step Drupal migrations."""

    def __init__(
        self,
        settings: Any,
        jsonapi_client: Any,
        drush_client: Any,
        ai_service: Any,
        site_manager: Any,
    ):
        self.settings = settings
        self.jsonapi = jsonapi_client
        self.drush = drush_client
        self.ai = ai_service
        self.site_manager = site_manager
