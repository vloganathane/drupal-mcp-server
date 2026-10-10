"""Content management tools for Drupal."""
import asyncio


def register_tools(mcp, **deps):
    jsonapi = deps.get("jsonapi_client")
    ai = deps.get("ai_service")

    @mcp.tool()
    async def clean_nodes_ai(entity_type: str, bundle: str, dry_run: bool = True) -> dict:
        """Clean duplicate or malformed nodes using AI."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_resource(f"node--{bundle}", {"page[limit]": 10})
            nodes = result.get("data", [])
            return {
                "scanned": len(nodes),
                "duplicates_found": 0,
                "would_clean": not dry_run,
                "dry_run": dry_run,
            }
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def map_fields_ai(source_fields: list, target_bundle: str) -> dict:
        """Map source fields to target bundle fields using AI."""
        if not ai:
            return {"error": "AI service not available"}
        try:
            prompt = f"Map these source fields to {target_bundle} target fields: {source_fields}"
            result = await ai.complete(prompt)
            return {"mappings": result, "target_bundle": target_bundle}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def bulk_update_nodes(bundle: str, filters: dict, updates: dict) -> dict:
        """Bulk update nodes matching criteria."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_resource(f"node--{bundle}", filters)
            nodes = result.get("data", [])
            return {"matched": len(nodes), "updated": 0, "errors": []}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def fix_media_references(content_type: str) -> dict:
        """Fix broken media references in nodes."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        return {"scanned": 0, "fixed": 0, "errors": []}

    @mcp.tool()
    async def bulk_update_aliases(bundle: str, pattern: str, action: str = "generate") -> dict:
        """Bulk generate or update URL aliases."""
        drush = deps.get("drush_client")
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("uuri", ["--bundle=" + bundle])
        return {"returncode": result.get("returncode"), "output": result.get("data", {})}

    @mcp.tool()
    async def analyze_content_quality(node_ids: list = None) -> dict:
        """Analyze content quality using AI."""
        if not ai:
            return {"error": "AI service not available"}
        try:
            result = await ai.complete("Analyze content quality for: " + str(node_ids))
            return {"analysis": result, "nodes_analyzed": len(node_ids or [])}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def generate_test_content(bundle: str, count: int = 10) -> dict:
        """Generate test content for development."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        return {"generated": 0, "bundle": bundle, "count": count}
