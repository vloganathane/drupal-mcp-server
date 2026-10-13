# Importer/Caller: server.py uses SiteManager
# Affected API: Internal services module
# Data Schemas: None
# User Instruction: "Implement the actual MCP server (the tools, resources, and FastMCP app)"
from typing import Any


class SiteManager:
    def __init__(self, settings: Any): self.settings = settings
    async def get_status(self) -> dict[str, Any]:
        return {"base_url": self.settings.DRUPAL_BASE_URL}
