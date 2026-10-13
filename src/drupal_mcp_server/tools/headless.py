"""Headless/Decoupled tools for Drupal."""

import json
from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    jsonapi = deps.get("jsonapi_client")
    graphql = deps.get("graphql_client")

    @mcp.tool()
    async def jsonapi_schema_get(
        entity_type: str | None = None,
    ) -> dict[str, Any]:
        """Get JSON:API schema (OpenAPI/Swagger)."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            if entity_type:
                result = await jsonapi.get_resource("jsonapi", {})
                return _ensure_dict(result)
            else:
                result = await jsonapi.get_resource("jsonapi", {})
                return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def jsonapi_include_optimize(
        entity_type: str,
        includes: list[str],
    ) -> dict[str, Any]:
        """Get optimized include paths for entity type."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_by_id(entity_type, "_test", params={"include": ",".join(includes)})
            return _ensure_dict({"optimized_includes": includes, "test_result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def jsonapi_sparse_fieldsets(
        entity_type: str,
        fields: list[str],
    ) -> dict[str, Any]:
        """Get entity with sparse fieldsets (only requested fields)."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"fields[%s]" % entity_type: ",".join(fields)}
            result = await jsonapi.get_resource(entity_type, params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def graphql_schema_get(
        format: str = "json",
    ) -> dict[str, Any]:
        """Get GraphQL schema."""
        if not graphql:
            return {"error": "GraphQL not available"}
        try:
            if format == "json":
                result = await graphql.get_schema()
                return _ensure_dict(result)
            else:
                result = await graphql.get_schema_sdl()
                return _ensure_dict({"schema": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def graphql_query(
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query."""
        if not graphql:
            return {"error": "GraphQL not available"}
        try:
            result = await graphql.execute(query, variables)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def graphql_schema_extend(
        type_name: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Extend GraphQL schema with custom fields (requires schema customization module)."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            config = {
                "extend_type": type_name,
                "fields": fields,
            }
            import json
            result = await drush.run("config:set", ["graphql.schema.customization", json.dumps(config)])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def nextjs_helpers_generate(
        entity_types: list[str],
        output_dir: str = "./nextjs-helpers",
    ) -> dict[str, Any]:
        """Generate Next.js helper functions for Drupal entities."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            helpers = {}
            if jsonapi:
                for entity_type in entity_types:
                    schema = await jsonapi.get_resource("jsonapi", {})
                    helpers[entity_type] = {
                        "type": f"Drupal{entity_type.capitalize()}",
                        "api_url": f"/jsonapi/{entity_type}",
                    }
            
            import json
            os.makedirs(output_dir, exist_ok=True)
            with open(os.path.join(output_dir, "drupal-types.ts"), "w") as f:
                f.write("// Generated Drupal types\n")
                for k, v in helpers.items():
                    f.write(f"export interface {v['type']} {{\n  id: string;\n  type: string;\n  attributes: any;\n}}\n\n")
            
            with open(os.path.join(output_dir, "drupal-api.ts"), "w") as f:
                f.write("// Generated Drupal API helpers\n")
                f.write("const BASE_URL = process.env.DRUPAL_URL || 'http://localhost';\n\n")
                for k, v in helpers.items():
                    f.write(f"export async function get{k.capitalize()}(id: string) {{\n")
                    f.write(f"  const res = await fetch(`${{BASE_URL}}{v['api_url']}/${{id}}`);\n")
                    f.write("  return res.json();\n")
                    f.write("}\n\n")
            
            return _ensure_dict({"generated": list(helpers.keys()), "output_dir": output_dir})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def gatsby_helpers_generate(
        entity_types: list[str],
        output_dir: str = "./gatsby-helpers",
    ) -> dict[str, Any]:
        """Generate Gatsby source plugin config and helpers."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            gatsby_config = {
                "plugins": [
                    {
                        "resolve": "gatsby-source-drupal",
                        "options": {
                            "baseUrl": "http://localhost",
                            "apiBase": "jsonapi",
                            "entityTypes": entity_types,
                        }
                    }
                ]
            }
            
            import json
            os.makedirs(output_dir, exist_ok=True)
            with open(os.path.join(output_dir, "gatsby-config.js"), "w") as f:
                f.write("module.exports = " + json.dumps(gatsby_config, indent=2) + ";")
            
            return _ensure_dict({"generated": entity_types, "output_dir": output_dir})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def jsonapi_resources_list(
        page_limit: int = 100,
    ) -> dict[str, Any]:
        """List all available JSON:API resources."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_resource("jsonapi", {})
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def jsonapi_resource_types(
    ) -> dict[str, Any]:
        """Get all resource types available in JSON:API."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_resource("jsonapi", {})
            result = _ensure_dict(result)
            if result.get("error"):
                return result
            
            links = result.get("links", {})
            resources = [k for k in links.keys() if not k.startswith("http")]
            return _ensure_dict({"resource_types": resources})
        except Exception as e:
            return {"error": str(e)}
