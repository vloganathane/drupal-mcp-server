"""AI-powered tools for Drupal."""

from typing import Any

from fastmcp import FastMCP


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    ai = deps.get("ai_service")

    @mcp.tool()
    async def ai_analyze_content_quality(content: str) -> dict[str, Any]:
        """Analyze content quality using AI."""
        if not ai:
            return {"error": "AI service not available"}
        try:
            prompt = f"Analyze this content for quality issues: {content[:2000]}"
            result = await ai.complete(prompt)
            return {"analysis": result, "content_length": len(content)}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def ai_suggest_field_mappings(source_fields: list[str], target_bundle: str) -> dict[str, Any]:
        """Suggest field mappings using AI."""
        if not ai:
            return {"error": "AI service not available"}
        try:
            prompt = f"For Drupal migration to {target_bundle}, map these source fields: {source_fields}"
            result = await ai.complete(prompt)
            return {"mappings": result, "target": target_bundle}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def ai_generate_migration_plan(source_type: str, target_version: str = "10") -> dict[str, Any]:
        """Generate migration plan using AI."""
        if not ai:
            return {"error": "AI service not available"}
        try:
            prompt = f"Create a migration plan from {source_type} to Drupal {target_version}"
            result = await ai.complete(prompt)
            return {"plan": result, "source": source_type, "target": target_version}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def ai_translate_content(content: str, target_lang: str, source_lang: str = "en") -> dict[str, Any]:
        """Translate content using AI."""
        if not ai:
            return {"error": "AI service not available"}
        try:
            prompt = f"Translate from {source_lang} to {target_lang}: {content[:2000]}"
            result = await ai.complete(prompt)
            return {"translation": result, "target_lang": target_lang, "source_lang": source_lang}
        except Exception as e:
            return {"error": str(e)}
