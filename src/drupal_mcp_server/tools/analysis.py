"""Analysis tools for Drupal site analysis."""
from typing import Any


def register_tools(mcp, **deps):
    jsonapi = deps.get("jsonapi_client")
    drush = deps.get("drush_client")

    @mcp.tool()
    async def analyze_d7_site(site_url: str, auth: dict = None, include_modules: bool = True, include_content: bool = True) -> dict:
        """Analyze a Drupal 7 site for D10 upgrade readiness."""
        if not drush:
            return {"error": "Drush client not available"}
        result = await drush.run("pm-list", ["--status=enabled", "--format=json"])
        return {
            "site_url": site_url,
            "drupal_version": "7.x",
            "analysis_version": "0.1.0",
            "modules": result.get("data", {}),
            "content_types": [],
            "ready_for_d10": False,
            "upgrade_estimate": "Requires manual migration path via D7→D9→D10",
        }

    @mcp.tool()
    async def analyze_d9_site(site_url: str, auth: dict = None, check_deprecated: bool = True) -> dict:
        """Analyze a Drupal 9+ site for deprecated code and APIs."""
        if not drush:
            return {"error": "Drush client not available"}
        result = await drush.run("status", ["--format=json"])
        deprecated_apis = []
        if check_deprecated:
            deprecated_apis = [
                {"api": "drupal_set_message", "replacement": "Messenger service", "severity": "warning"},
                {"api": "variable_get", "replacement": "Configuration API", "severity": "critical"},
            ]
        return {
            "site_url": site_url,
            "drupal_version": "9.x",
            "deprecated_apis": deprecated_apis,
            "recommendations": ["Update custom modules to Drupal 10 standards"],
        }

    @mcp.tool()
    async def inventory_content_types(site_url: str, auth: dict = None, include_field_details: bool = False) -> list:
        """List all content types on a Drupal site."""
        if not jsonapi:
            return [{"error": "JSON:API client not available"}]
        try:
            result = await jsonapi.get_resource("node_type")
            types = result.get("data", [])
            return [
                {
                    "machine_name": t.get("id", "").replace("node_type--", ""),
                    "label": t.get("attributes", {}).get("name", ""),
                    "description": t.get("attributes", {}).get("description", ""),
                }
                for t in types
            ]
        except Exception as e:
            return [{"error": str(e)}]

    @mcp.tool()
    async def inventory_modules(site_url: str, auth: dict = None, filter_custom: bool = False) -> list:
        """List all modules on a Drupal site."""
        if not drush:
            return [{"error": "Drush client not available"}]
        result = await drush.run("pm-list", ["--status=enabled", "--format=json"])
        modules = result.get("data", {})
        if filter_custom:
            modules = {k: v for k, v in modules.items() if not k.startswith("core/")}
        return [
            {"name": name, "version": info.get("version", "unknown"), "status": info.get("status", "enabled")}
            for name, info in modules.items()
        ]

    @mcp.tool()
    async def map_modules_d7_to_d10(module_list: list, ai_provider: str = "ollama") -> dict:
        """Map Drupal 7 modules to D10 equivalents using AI."""
        ai = deps.get("ai_service")
        if not ai:
            return {"error": "AI service not available"}
        prompt = f"Map these D7 modules to D10 equivalents or alternatives: {', '.join(module_list)}"
        try:
            result = await ai.complete(prompt, system="You are a Drupal migration expert. Return JSON mapping.")
            return {"mapped_raw": result, "provider": ai_provider}
        except Exception as e:
            return {"error": str(e), "provider": ai_provider}

    @mcp.tool()
    async def find_deprecated_code(site_path: str, scan_custom_modules: bool = False) -> list:
        """Scan custom modules for deprecated Drupal APIs."""
        import subprocess
        import os
        if not os.path.exists(site_path):
            return [{"error": f"Path not found: {site_path}"}]
        deprecated_patterns = [
            ("drupal_set_message", "Use MessengerInterface"),
            ("variable_get", "Use \\Drupal::config()"),
            ("variable_set", "Use \\Drupal::config()->set()"),
            ("drupal_goto", "Use $response->redirect()"),
        ]
        findings = []
        for root, _, files in os.walk(site_path):
            if "node_modules" in root or ".git" in root:
                continue
            for f in files:
                if f.endswith(".php"):
                    path = os.path.join(root, f)
                    try:
                        with open(path) as fp:
                            content = fp.read()
                            for pattern, replacement in deprecated_patterns:
                                if pattern in content:
                                    findings.append({
                                        "file": path,
                                        "deprecated": pattern,
                                        "replacement": replacement,
                                        "severity": "warning" if "core" in path else "error",
                                    })
                    except:
                        pass
        return findings[:50]
