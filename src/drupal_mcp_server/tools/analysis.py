"""Analysis tools for Drupal site analysis."""

import json
import os
import re
import urllib.parse
from typing import Any

from fastmcp import FastMCP

from ..validation import validate_identifier, validate_single_select

# Internal routes that resolve straight to an entity id.
_ROUTES = [
    (re.compile(r"^/node/(\d+)$"), "node"),
    (re.compile(r"^/taxonomy/term/(\d+)$"), "taxonomy_term"),
    (re.compile(r"^/user/(\d+)$"), "user"),
    (re.compile(r"^/media/(\d+)$"), "media"),
    (re.compile(r"^/comment/(\d+)$"), "comment"),
]

# Tables `search_entities` scans. These are the *_field_data tables Drupal
# itself queries for list views: they hold the values a user would search
# by (titles, names, subjects), not the field storage tables.
_SEARCHABLE: dict[str, dict[str, str]] = {
    "node": {
        "table": "node_field_data",
        "match": "title",
        "id": "nid",
        "extra": "type",
    },
    "user": {
        "table": "users_field_data",
        "match": "name",
        "id": "uid",
        "extra": "mail",
    },
    "taxonomy_term": {
        "table": "taxonomy_term_field_data",
        "match": "name",
        "id": "tid",
        "extra": "vid",
    },
    "comment": {
        "table": "comment_field_data",
        "match": "subject",
        "id": "cid",
        "extra": "entity_type",
    },
    "media": {
        "table": "media_field_data",
        "match": "name",
        "id": "mid",
        "extra": "bundle",
    },
    "file": {
        "table": "file_managed",
        "match": "filename",
        "id": "fid",
        "extra": "uid",
    },
}

def _sql_literal(value: str) -> str:
    """A single-quoted SQL string literal holding `value` exactly.

    Escapes the backslash first so the escapes below are not themselves
    escaped. Drush has no bound parameters for sql:query, so every value
    this module sends to SQL goes through here after validation.
    """
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _like_literal(value: str) -> str:
    """The literal wrapped for `LIKE '%...%'`, wildcards included verbatim.

    A query for "100%" must not match everything, so % and _ are escaped
    on top of the string escaping.
    """
    escaped = (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
        .replace("'", "\\'")
    )
    return f"'%{escaped}%'"


def _sql_output(result: dict[str, Any]) -> tuple[str, str | None]:
    """Raw stdout text and an error reason from a `sql:query` result.

    `sql:query` has no --format option at all, so the client cannot parse
    the rows itself: stdout arrives as raw text under ``{"output": ...}``
    (or an empty dict when the query returned nothing).
    """
    data = result.get("data")
    if isinstance(data, dict) and isinstance(data.get("output"), str):
        return data["output"], None
    if isinstance(data, str):
        return data, None
    if result.get("returncode"):
        return "", str(result.get("stderr", "")).strip() or "query failed"
    return "", None


def _sql_rows(output: str, columns: list[str]) -> list[dict[str, Any]]:
    """Parse `drush sql:query` output: tab-separated values, no header row.

    Values arrive as text, and NULL is printed as those four characters, so
    a NULL langcode reads back as None. A value containing a tab splits into
    extra fields, which are joined back into the last column rather than
    shifting the rest of the row.
    """
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) > len(columns):
            parts = parts[: len(columns) - 1] + [
                "\t".join(parts[len(columns) - 1 :])
            ]
        while len(parts) < len(columns):
            parts.append("")
        rows.append(
            {
                column: (None if value == "NULL" else value)
                for column, value in zip(columns, parts, strict=False)
            }
        )
    return rows


async def _fetch_all_field_configs(
    jsonapi: Any, type_name: str, fields: str, cap: int = 1000
) -> tuple[list[dict[str, Any]], bool]:
    """Every row of a field config collection, paged 50 at a time.

    ``type_name`` is the JSON:API type (``field_storage_config--field_storage_config``);
    the client maps it to the double path Drupal serves config entities at.
    The sparse fieldset is keyed by the short type name, as the spec requires.
    Returns the rows and whether the cap was hit. JSON:API offers no filter
    on nested ``settings``, so the caller filters client-side.
    """
    short = type_name.split("--", 1)[0]
    rows: list[dict[str, Any]] = []
    offset = 0
    while offset < cap:
        params = {
            "page[limit]": "50",
            "page[offset]": str(offset),
            f"fields[{short}]": fields,
        }
        result = await jsonapi.get_resource(type_name, params)
        data = result.get("data") if isinstance(result, dict) else result
        if not isinstance(data, list):
            break
        for item in data:
            if not isinstance(item, dict):
                continue
            # JSON:API nests the payload under "attributes"; the join keys
            # (drupal_internal__id, bundle, ...) live there, not on the item.
            attributes = item.get("attributes")
            rows.append(
                dict(attributes) if isinstance(attributes, dict) else dict(item)
            )
        if len(data) < 50:
            return rows, False
        offset += 50
    return rows, True


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")
    drush = deps.get("drush_client")

    @mcp.tool()
    async def analyze_d7_site(
        site_url: str, auth: dict[str, Any] | None = None, include_modules: bool = True, include_content: bool = True
    ) -> dict[str, Any]:
        """Analyze a Drupal 7 site for D10 upgrade readiness."""
        if not drush:
            return {"error": "Drush client not available"}

        # Get Drupal version
        status_result = await drush.run("status", ["--format=json"])
        status_data = status_result.get("data", {})

        # Get enabled modules
        modules_result = await drush.run("pm-list", ["--status=enabled", "--format=json"])
        modules_data = modules_result.get("data", {})

        # Categorize modules
        core_modules = {k: v for k, v in modules_data.items() if k.startswith("core/")}
        contrib_modules = {k: v for k, v in modules_data.items() if not k.startswith("core/") and not k.startswith("custom/")}
        custom_modules = {k: v for k, v in modules_data.items() if k.startswith("custom/")}

        # Get themes
        themes_result = await drush.run("pm-list", ["--type=theme", "--status=enabled", "--format=json"])
        themes_data = themes_result.get("data", {})

        # Get content types if requested
        content_types = []
        if include_content and jsonapi:
            try:
                ct_result = await jsonapi.get_resource("node_type")
                content_types = [
                    {
                        "machine_name": t.get("id", "").replace("node_type--", ""),
                        "label": t.get("attributes", {}).get("name", ""),
                        "description": t.get("attributes", {}).get("description", ""),
                    }
                    for t in ct_result.get("data", [])
                ]
            except Exception:
                content_types = [{"error": "Could not fetch content types via JSON:API"}]

        # Analyze D7 modules for D10 compatibility
        d7_only_modules = [
            "ctools", "entity", "rules", "features", "strongarm", "uuid",
            "views", "panels", "page_manager", "panelizer", "ds",
            "field_collection", "field_group", "entityreference",
            "references", "date", "link", "email", "phone",
            "addressfield", "geofield", "geolocation", "location",
            "imagefield", "filefield", "media", "media_youtube",
            "media_vimeo", "media_wysiwyg", "wysiwyg", "ckeditor",
            "token", "pathauto", "redirect", "globalredirect",
            "xmlsitemap", "metatag", "google_analytics", "webform",
            "contact", "simplenews", "mailchimp", "hubspot",
            "commerce", "commerce_cart", "commerce_checkout",
            "commerce_order", "commerce_product", "commerce_payment",
            "commerce_shipping", "commerce_tax", "commerce_discount",
            "rules_scheduler", "rules_admin", "rules_ui",
            "views_ui", "views_bulk_operations", "views_content_cache",
            "feeds", "feeds_ui", "feeds_tamper", "feeds_tamper_ui",
            "migrate", "migrate_ui", "migrate_d2d", "migrate_extras",
        ]

        contrib_module_names = list(contrib_modules.keys())
        d7_matched = [m for m in contrib_module_names if any(d7 in m for d7 in d7_only_modules)]

        # Check for known D7-to-D10 migration paths
        migration_paths = {
            "ctools": "Drupal core (Plugin API, Context API)",
            "entity": "Drupal core (Entity API)",
            "rules": "No direct equivalent; consider Rules module (D9+) or custom event subscribers",
            "features": "Config Export/Import (core), Config Split",
            "strongarm": "Config API (core)",
            "uuid": "Drupal core (UUID field)",
            "views": "Drupal core (Views)",
            "panels": "Layout Builder (core) or Panels (D9+)",
            "page_manager": "Layout Builder (core)",
            "panelizer": "Layout Builder (core)",
            "ds": "Layout Builder (core) or Display Suite (D9+)",
            "field_collection": "Paragraphs (recommended) or Field Collection (D9+)",
            "field_group": "Field Group (D9+)",
            "entityreference": "Entity Reference (core)",
            "references": "Entity Reference (core)",
            "date": "Datetime (core)",
            "link": "Link (core)",
            "email": "Email (core)",
            "phone": "Telephone (core)",
            "addressfield": "Address (contrib)",
            "geofield": "Geofield (D9+)",
            "geolocation": "Geolocation (D9+)",
            "location": "Location (D9+) or Address (contrib)",
            "imagefield": "Image (core)",
            "filefield": "File (core)",
            "media": "Media (core)",
            "token": "Token (D9+)",
            "pathauto": "Pathauto (D9+)",
            "redirect": "Redirect (D9+)",
            "globalredirect": "Redirect (D9+) + core redirect",
            "xmlsitemap": "XML Sitemap (D9+)",
            "metatag": "Metatag (D9+)",
            "google_analytics": "Google Analytics (D9+)",
            "webform": "Webform (D9+)",
            "commerce": "Drupal Commerce 2.x (D9+)",
        }

        # Generate module migration plan
        module_plan = []
        for mod in contrib_module_names:
            base_name = mod.replace("contrib/", "").replace("custom/", "")
            if base_name in migration_paths:
                module_plan.append({
                    "module": base_name,
                    "d7_status": "enabled",
                    "d10_equivalent": migration_paths[base_name],
                    "migration_complexity": "medium" if "custom" in migration_paths[base_name].lower() else "low",
                })
            else:
                module_plan.append({
                    "module": base_name,
                    "d7_status": "enabled",
                    "d10_equivalent": "Check Drupal.org for D10 version",
                    "migration_complexity": "unknown",
                })

        # Determine readiness
        blockers = len([m for m in module_plan if m["migration_complexity"] == "high"])
        warnings = len([m for m in module_plan if m["migration_complexity"] == "medium"])

        ready_for_d10 = blockers == 0

        return {
            "site_url": site_url,
            "drupal_version": "7.x",
            "analysis_version": "1.0.0",
            "drupal_core_version": status_data.get("Drupal version", "Unknown"),
            "php_version": status_data.get("PHP version", "Unknown"),
            "database": status_data.get("Database", "Unknown"),
            "modules": {
                "core_count": len(core_modules),
                "contrib_count": len(contrib_modules),
                "custom_count": len(custom_modules),
                "contrib_modules": list(contrib_modules.keys()),
                "custom_modules": list(custom_modules.keys()),
            },
            "themes": list(themes_data.keys()),
            "content_types": content_types if include_content else [],
            "module_migration_plan": module_plan,
            "d7_specific_modules_found": d7_matched,
            "ready_for_d10": ready_for_d10,
            "blockers": blockers,
            "warnings": warnings,
            "upgrade_estimate": f"Estimated {blockers * 8 + warnings * 4 + len(custom_modules) * 16} hours for migration",
            "recommendations": [
                "Audit custom modules for D10 compatibility",
                "Replace Features with Config Split + Config Export",
                "Migrate Panels/Panelizer to Layout Builder",
                "Replace Field Collection with Paragraphs",
                "Update Views to core Views (API changed)",
                "Migrate Rules to Event Subscribers or Rules (D9+)",
                "Test all contrib modules for D10 versions",
                "Plan content migration for custom content types",
            ],
        }

    @mcp.tool()
    async def analyze_d9_site(
        site_url: str, auth: dict[str, Any] | None = None, check_deprecated: bool = True
    ) -> dict[str, Any]:
        """Analyze a Drupal 9+ site for deprecated code and APIs."""
        if not drush:
            return {"error": "Drush client not available"}

        status_result = await drush.run("status", ["--format=json"])
        status_data = status_result.get("data", {})

        # Get modules
        modules_result = await drush.run("pm-list", ["--status=enabled", "--format=json"])
        modules_data = modules_result.get("data", {})

        deprecated_apis = []
        if check_deprecated:
            # Common D9 deprecated APIs that affect D10 upgrade
            deprecated_apis = [
                {
                    "api": "drupal_set_message",
                    "replacement": "Messenger service (\\Drupal::messenger())",
                    "severity": "warning",
                    "removed_in": "Drupal 10",
                },
                {
                    "api": "variable_get/set/del",
                    "replacement": "Config API (\\Drupal::config())",
                    "severity": "critical",
                    "removed_in": "Drupal 10",
                },
                {
                    "api": "drupal_goto",
                    "replacement": "$response->redirect() or RedirectResponse",
                    "severity": "critical",
                    "removed_in": "Drupal 10",
                },
                {
                    "api": "drupal_get_query_parameters",
                    "replacement": "Request::query->all()",
                    "severity": "warning",
                    "removed_in": "Drupal 10",
                },
                {
                    "api": "url()",
                    "replacement": "Url::fromRoute() or Url::fromUri()",
                    "severity": "warning",
                    "removed_in": "Drupal 10",
                },
                {
                    "api": "l()",
                    "replacement": "Link::fromTextAndUrl()",
                    "severity": "warning",
                    "removed_in": "Drupal 10",
                },
                {
                    "api": "drupal_add_css/js",
                    "replacement": "#attached library",
                    "severity": "critical",
                    "removed_in": "Drupal 10",
                },
                {
                    "api": "hook_menu()",
                    "replacement": "Routing system (MODULE.routing.yml)",
                    "severity": "critical",
                    "removed_in": "Drupal 10",
                },
                {
                    "api": "hook_permission()",
                    "replacement": "MODULE.permissions.yml",
                    "severity": "warning",
                    "removed_in": "Drupal 10",
                },
                {
                    "api": "hook_entity_info()",
                    "replacement": "EntityType annotations",
                    "severity": "critical",
                    "removed_in": "Drupal 10",
                },
            ]

        # Get custom modules for scanning
        custom_modules = {k: v for k, v in modules_data.items() if k.startswith("custom/")}

        return {
            "site_url": site_url,
            "drupal_version": status_data.get("Drupal version", "9.x"),
            "php_version": status_data.get("PHP version", "Unknown"),
            "database": status_data.get("Database", "Unknown"),
            "deprecated_apis": deprecated_apis,
            "enabled_modules": list(modules_data.keys()),
            "custom_modules": list(custom_modules.keys()),
            "custom_module_count": len(custom_modules),
            "recommendations": [
                "Run 'drupal-check' or 'phpstan' on custom modules",
                "Update deprecated service calls to use \\Drupal::service()",
                "Replace hook_menu with routing.yml",
                "Replace hook_permission with permissions.yml",
                "Replace hook_entity_info with EntityType annotations",
                "Use #attached libraries instead of drupal_add_css/js",
                "Run composer update to get D10-ready contrib modules",
                "Test with PHPUnit and SimpleTest",
            ],
        }

    @mcp.tool()
    async def inventory_content_types(
        site_url: str, auth: dict[str, Any] | None = None, include_field_details: bool = False
    ) -> list[dict[str, Any]]:
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
    async def inventory_modules(
        site_url: str, auth: dict[str, Any] | None = None, filter_custom: bool = False
    ) -> list[dict[str, Any]]:
        """List all modules on a Drupal site."""
        if not drush:
            return [{"error": "Drush client not available"}]
        result = await drush.run("pm-list", ["--status=enabled", "--format=json"])
        modules = result.get("data", {})
        if filter_custom:
            modules = {k: v for k, v in modules.items() if not k.startswith("core/")}
        return [
            {
                "name": name,
                "version": info.get("version", "unknown"),
                "status": info.get("status", "enabled"),
            }
            for name, info in modules.items()
        ]

    @mcp.tool()
    async def map_modules_d7_to_d10(module_list: list[str], ai_provider: str = "ollama") -> dict[str, Any]:
        """Map Drupal 7 modules to D10 equivalents using AI + known mappings."""
        ai = deps.get("ai_service")

        # Known D7 to D10 module mappings
        known_mappings = {
            "ctools": {"d10_equivalent": "Drupal core (Plugin API, Context API)", "status": "core", "notes": "Functionality moved to core"},
            "entity": {"d10_equivalent": "Drupal core (Entity API)", "status": "core", "notes": "Entity API in core since D8"},
            "rules": {"d10_equivalent": "Rules (D9+) or Event Subscribers", "status": "contrib", "notes": "Rules module ported to D9+, or use custom event subscribers"},
            "features": {"d10_equivalent": "Config Export/Import (core), Config Split", "status": "core", "notes": "Config management in core; Config Split for env-specific config"},
            "strongarm": {"d10_equivalent": "Config API (core)", "status": "core", "notes": "Variables now in config system"},
            "uuid": {"d10_equivalent": "Drupal core (UUID field)", "status": "core", "notes": "UUID field type in core"},
            "views": {"d10_equivalent": "Drupal core (Views)", "status": "core", "notes": "Views in core since D8"},
            "panels": {"d10_equivalent": "Layout Builder (core) or Panels (D9+)", "status": "core/contrib", "notes": "Layout Builder recommended; Panels available for D9+"},
            "page_manager": {"d10_equivalent": "Layout Builder (core)", "status": "core", "notes": "Page Manager functionality in Layout Builder"},
            "panelizer": {"d10_equivalent": "Layout Builder (core)", "status": "core", "notes": "Panelizer replaced by Layout Builder"},
            "ds": {"d10_equivalent": "Layout Builder (core) or Display Suite (D9+)", "status": "core/contrib", "notes": "Layout Builder preferred; DS available for D9+"},
            "field_collection": {"d10_equivalent": "Paragraphs (recommended) or Field Collection (D9+)", "status": "contrib", "notes": "Paragraphs is more flexible and maintained"},
            "field_group": {"d10_equivalent": "Field Group (D9+)", "status": "contrib", "notes": "Field Group ported to D9+"},
            "entityreference": {"d10_equivalent": "Entity Reference (core)", "status": "core", "notes": "Entity Reference in core since D8"},
            "references": {"d10_equivalent": "Entity Reference (core)", "status": "core", "notes": "References replaced by Entity Reference"},
            "date": {"d10_equivalent": "Datetime (core)", "status": "core", "notes": "Date field in core as Datetime"},
            "link": {"d10_equivalent": "Link (core)", "status": "core", "notes": "Link field in core"},
            "email": {"d10_equivalent": "Email (core)", "status": "core", "notes": "Email field in core"},
            "phone": {"d10_equivalent": "Telephone (core)", "status": "core", "notes": "Telephone field in core"},
            "addressfield": {"d10_equivalent": "Address (contrib)", "status": "contrib", "notes": "Address module for D9+"},
            "geofield": {"d10_equivalent": "Geofield (D9+)", "status": "contrib", "notes": "Geofield ported to D9+"},
            "geolocation": {"d10_equivalent": "Geolocation (D9+)", "status": "contrib", "notes": "Geolocation ported to D9+"},
            "location": {"d10_equivalent": "Location (D9+) or Address (contrib)", "status": "contrib", "notes": "Consider Address module instead"},
            "imagefield": {"d10_equivalent": "Image (core)", "status": "core", "notes": "Image field in core"},
            "filefield": {"d10_equivalent": "File (core)", "status": "core", "notes": "File field in core"},
            "media": {"d10_equivalent": "Media (core)", "status": "core", "notes": "Media in core since D8.4"},
            "token": {"d10_equivalent": "Token (D9+)", "status": "contrib", "notes": "Token module ported to D9+"},
            "pathauto": {"d10_equivalent": "Pathauto (D9+)", "status": "contrib", "notes": "Pathauto ported to D9+"},
            "redirect": {"d10_equivalent": "Redirect (D9+)", "status": "contrib", "notes": "Redirect module ported to D9+"},
            "globalredirect": {"d10_equivalent": "Redirect (D9+) + core redirect", "status": "core/contrib", "notes": "Global Redirect functionality in core Redirect + Redirect module"},
            "xmlsitemap": {"d10_equivalent": "XML Sitemap (D9+)", "status": "contrib", "notes": "XML Sitemap ported to D9+"},
            "metatag": {"d10_equivalent": "Metatag (D9+)", "status": "contrib", "notes": "Metatag ported to D9+"},
            "google_analytics": {"d10_equivalent": "Google Analytics (D9+)", "status": "contrib", "notes": "GA module ported to D9+"},
            "webform": {"d10_equivalent": "Webform (D9+)", "status": "contrib", "notes": "Webform ported to D9+"},
            "commerce": {"d10_equivalent": "Drupal Commerce 2.x (D9+)", "status": "contrib", "notes": "Commerce 2.x for D9+"},
            "feeds": {"d10_equivalent": "Feeds (D9+)", "status": "contrib", "notes": "Feeds ported to D9+"},
            "migrate": {"d10_equivalent": "Migrate (core)", "status": "core", "notes": "Migrate API in core since D8"},
        }

        results = []
        for module in module_list:
            if module in known_mappings:
                results.append({
                    "source_module": module,
                    "d10_equivalent": known_mappings[module]["d10_equivalent"],
                    "status": known_mappings[module]["status"],
                    "confidence": 0.95,
                    "notes": known_mappings[module]["notes"],
                    "source": "known_mapping",
                })
            else:
                # Use AI for unknown modules
                ai_result = None
                if ai:
                    try:
                        prompt = (
                            f"Map this D7 module to D10 equivalent or alternative: {module}\n"
                            f"Return JSON: {{\"d10_equivalent\": \"...\", \"status\": \"core|contrib|none\", \"notes\": \"...\"}}"
                        )
                        ai_result = await ai.complete(
                            prompt, system="You are a Drupal migration expert. Return valid JSON only."
                        )
                        parsed = json.loads(ai_result) if isinstance(ai_result, str) else ai_result
                        parsed["source_module"] = module
                        parsed["confidence"] = parsed.get("confidence", 0.7)
                        parsed["source"] = "ai"
                        results.append(parsed)
                    except Exception:
                        results.append({
                            "source_module": module,
                            "d10_equivalent": "Unknown - check Drupal.org",
                            "status": "unknown",
                            "confidence": 0.1,
                            "notes": "AI mapping failed",
                            "source": "fallback",
                        })
                else:
                    results.append({
                        "source_module": module,
                        "d10_equivalent": "Unknown - check Drupal.org",
                        "status": "unknown",
                        "confidence": 0.1,
                        "notes": "AI service not available",
                        "source": "fallback",
                    })

        return {
            "mappings": results,
            "total_mapped": len(results),
            "known_mappings_used": len([r for r in results if r["source"] == "known_mapping"]),
            "ai_mappings_used": len([r for r in results if r["source"] == "ai"]),
            "provider": ai_provider,
        }

    @mcp.tool()
    async def find_deprecated_code(
        site_path: str, scan_custom_modules: bool = False
    ) -> list[dict[str, str]]:
        """Scan custom modules for deprecated Drupal APIs."""

        if not os.path.exists(site_path):
            return [{"error": f"Path not found: {site_path}"}]
        deprecated_patterns = [
            ("drupal_set_message", "Use MessengerInterface"),
            ("variable_get", "Use \\Drupal::config()"),
            ("variable_set", "Use \\Drupal::config()->set()"),
            ("drupal_goto", "Use $response->redirect()"),
        ]
        findings: list[dict[str, str]] = []
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
                                    findings.append(
                                        {
                                            "file": path,
                                            "deprecated": pattern,
                                            "replacement": replacement,
                                            "severity": "warning" if "core" in path else "error",
                                        }
                                    )
                    except Exception:
                        pass
        return findings[:50]

    @mcp.tool()
    async def find_entity_references(
        entity_type: str,
        bundle: str | None = None,
        field_name: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Find which bundles use reference fields targeting an entity type.

        Answers "where are these used?" at the configuration level: for
        `entity_type` ("taxonomy_term", "node", "media", ...) it lists every
        field on every bundle whose storage targets that type, e.g. which
        content types have a tags or category field. Filter by the
        referencing `bundle` or by `field_name`.

        This reads field configuration, not content: it reports where
        references *can* live, not which individual rows currently point at
        which entity. For the data, query the field's table with `db_query`.
        """
        if not jsonapi:
            return {"error": "JSON:API client not available"}
        for label, value in (
            ("entity_type", entity_type),
            ("bundle", bundle),
            ("field_name", field_name),
        ):
            if value is not None:
                problem = validate_identifier(value, label)
                if problem:
                    return {"error": problem}
        if not isinstance(limit, int) or limit < 1 or limit > 500:
            return {"error": "limit must be an integer between 1 and 500"}

        storages, storages_truncated = await _fetch_all_field_configs(
            jsonapi,
            "field_storage_config--field_storage_config",
            "drupal_internal__id,field_name,entity_type,field_storage_config_type,settings",
        )
        configs, configs_truncated = await _fetch_all_field_configs(
            jsonapi,
            "field_config--field_config",
            "drupal_internal__id,field_name,bundle,entity_type",
        )

        matching: dict[str, dict[str, Any]] = {}
        for storage in storages:
            settings = storage.get("settings")
            if (
                isinstance(settings, dict)
                and settings.get("target_type") == entity_type
            ):
                storage_id = str(storage.get("drupal_internal__id", ""))
                matching[storage_id] = {
                    "field_name": storage.get("field_name"),
                    "source_entity_type": storage.get("entity_type"),
                    "field_type": storage.get("field_storage_config_type"),
                    "storage": storage_id,
                }

        references: list[dict[str, Any]] = []
        for config in configs:
            # A storage is keyed by entity type and field name; field_config
            # exposes no storage relationship, but its parts are enough to
            # rebuild that key.
            storage_key = (
                f"{config.get('entity_type')}.{config.get('field_name')}"
            )
            base = matching.get(storage_key)
            if base is None:
                continue
            if bundle is not None and config.get("bundle") != bundle:
                continue
            if field_name is not None and config.get("field_name") != field_name:
                continue
            references.append({**base, "bundle": config.get("bundle")})

        references.sort(
            key=lambda row: (
                str(row.get("source_entity_type")),
                str(row.get("bundle")),
                str(row.get("field_name")),
            )
        )
        by_source: dict[str, int] = {}
        for row in references:
            key = str(row.get("source_entity_type"))
            by_source[key] = by_source.get(key, 0) + 1

        payload: dict[str, Any] = {
            "target_entity_type": entity_type,
            "reference_fields": references[:limit],
            "returned": min(len(references), limit),
            "total": len(references),
            "by_source_entity_type": by_source,
        }
        if storages_truncated or configs_truncated:
            payload["truncated"] = (
                "More than 1000 field configs exist; some references may be "
                "missing from this scan."
            )
        return payload

    @mcp.tool()
    async def search_entities(
        query: str,
        entity_types: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Case-insensitive substring search across entity titles and names.

        Scans node titles, user names and emails, taxonomy term names,
        comment subjects, media names, and file names with one read-only
        LIKE query per type, returning matches grouped by entity type.

        Pass `entity_types` (e.g. ["node", "taxonomy_term"]) to search
        fewer tables: a LIKE scan reads every row, so keep it narrow on
        large sites. This does not search node bodies -- for full text use
        the site's own search or the search_api tools.
        """
        if not drush:
            return {"error": "Drush not available"}
        term = query.strip() if isinstance(query, str) else ""
        if not term or len(term) > 64:
            return {"error": "query must be 1 to 64 characters"}
        wanted = list(entity_types) if entity_types else list(_SEARCHABLE)
        unknown = [kind for kind in wanted if kind not in _SEARCHABLE]
        if unknown:
            return {
                "error": (
                    f"Unknown entity type(s): {', '.join(unknown)}. Supported: "
                    f"{', '.join(sorted(_SEARCHABLE))}"
                )
            }
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            return {"error": "limit must be an integer between 1 and 100"}

        literal = _like_literal(term)
        columns = ["etype", "id", "label", "extra"]

        def _select(kind: str, limit_clause: str) -> str:
            spec = _SEARCHABLE[kind]
            return (
                f"SELECT '{kind}' AS etype, CAST({spec['id']} AS CHAR) AS id, "
                f"{spec['match']} AS label, {spec['extra']} AS extra "
                f"FROM {spec['table']} WHERE {spec['match']} LIKE {literal} "
                f"{limit_clause}"
            )

        results: dict[str, list[dict[str, Any]]] = {}
        skipped: dict[str, str] = {}

        def _group(rows: list[dict[str, Any]]) -> None:
            for row in rows:
                kind = str(row.pop("etype", ""))
                if kind:
                    results.setdefault(kind, []).append(row)

        # One UNION query first: on a containerized site every drush call
        # pays a full bootstrap, so six separate queries cost a minute for
        # the same answer.
        union = " UNION ALL ".join(
            _select(kind, "") for kind in wanted
        ) + f" LIMIT {limit * len(wanted)}"
        problem = validate_single_select(union)
        if problem:
            # The table and column names are fixed and the term is escaped,
            # so this is the validator being paranoid, not a caller mistake;
            # surface it rather than run unvalidated.
            return {"error": f"internal query rejected by validator: {problem}"}
        try:
            result = await drush.run("sql:query", [union])
        except Exception as exc:  # noqa: BLE001 - reported as data
            result = {"returncode": 1, "stderr": str(exc)}
        text, error = _sql_output(result)
        if error is None:
            _group(_sql_rows(text, columns))
        else:
            # One missing table takes the whole UNION down (a site without
            # media or comments is common), so retry each type on its own
            # and skip only the ones that are actually absent.
            for kind in wanted:
                sql = _select(kind, f"LIMIT {limit}")
                if validate_single_select(sql):
                    continue
                try:
                    result = await drush.run("sql:query", [sql])
                except Exception as exc:  # noqa: BLE001 - a missing table is data
                    skipped[kind] = str(exc)[:200]
                    continue
                text, error = _sql_output(result)
                if error is not None:
                    skipped[kind] = error[:200]
                    continue
                _group(_sql_rows(text, columns))

        payload: dict[str, Any] = {
            "query": term,
            "results": results,
            "matches": {kind: len(rows) for kind, rows in results.items()},
            "total": sum(len(rows) for rows in results.values()),
        }
        if skipped:
            payload["skipped"] = skipped
        return payload

    @mcp.tool()
    async def find_entity_by_path(path: str) -> dict[str, Any]:
        """Resolve a URL path or alias ("/about", "/node/123") to its entity.

        Internal routes such as /node/123 are read directly. Anything else
        is looked up in the path alias table, and the resolved target is
        parsed the same way. A full URL is accepted; the query string and
        fragment are ignored. Returns the entity id and a short summary,
        or found: false when nothing resolves.
        """
        if not drush or not jsonapi:
            return {"error": "Drush and JSON:API clients are required"}
        raw = path.strip() if isinstance(path, str) else ""
        if not raw or len(raw) > 512:
            return {"error": "path must be 1 to 512 characters"}
        if raw.startswith("http://") or raw.startswith("https://"):
            target = urllib.parse.urlsplit(raw).path or "/"
        else:
            target = raw.split("?", 1)[0].split("#", 1)[0]
        if not target.startswith("/"):
            target = "/" + target
        target = target.rstrip("/") or "/"

        is_route = any(rx.match(target) for rx, _ in _ROUTES)
        alias: dict[str, Any] | None = None
        internal = target
        if target != "/" and not is_route:
            sql = (
                "SELECT id, alias, path, langcode FROM path_alias "
                f"WHERE alias = {_sql_literal(target)} LIMIT 1"
            )
            problem = validate_single_select(sql)
            if problem:
                return {"error": f"internal query rejected by validator: {problem}"}
            try:
                result = await drush.run("sql:query", [sql])
            except Exception as exc:  # noqa: BLE001 - reported below
                result = {"returncode": 1, "stderr": str(exc)}
            text, error = _sql_output(result)
            rows = (
                _sql_rows(text, ["id", "alias", "path", "langcode"])
                if error is None
                else []
            )
            if rows and rows[0].get("path"):
                row = rows[0]
                alias = {
                    "id": row.get("id"),
                    "alias": row.get("alias"),
                    "path": row.get("path"),
                    "langcode": row.get("langcode"),
                }
                internal = str(row["path"]).rstrip("/") or "/"

        route = next(
            ((kind, matched.group(1)) for rx, kind in _ROUTES
             if (matched := rx.match(internal))),
            None,
        )
        if route is None:
            return {
                "found": False,
                "requested": target,
                "internal_path": internal,
                "alias": alias,
                "note": "No route pattern or path alias resolves this to an entity.",
            }

        kind, entity_id = route
        # The entity comes back whole: Drupal ignores sparse fieldsets keyed
        # by the bare entity type on content entities, so asking for a
        # summary would fetch everything anyway.
        try:
            entity = await jsonapi.get_by_id(kind, entity_id)
        except Exception as exc:  # noqa: BLE001 - a stale alias is data
            return {
                "found": False,
                "requested": target,
                "internal_path": internal,
                "alias": alias,
                "error": str(exc)[:300],
            }
        payload: dict[str, Any] = {
            "found": True,
            "requested": target,
            "internal_path": internal,
            "entity_type": kind,
            "entity_id": entity_id,
            "entity": entity,
        }
        if alias:
            payload["alias"] = alias
        return payload
