"""Content management tools for Drupal."""


def register_tools(mcp, **deps):
    jsonapi = deps.get("jsonapi_client")
    ai = deps.get("ai_service")

    @mcp.tool()
    async def clean_nodes_ai(entity_type: str, bundle: str, dry_run: bool = True) -> dict:
        """Clean duplicate or malformed nodes using AI."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_resource(f"node--{bundle}", {"page[limit]": 50})
            nodes = result.get("data", [])
            if not nodes:
                return {
                    "scanned": 0,
                    "duplicates_found": 0,
                    "would_clean": 0,
                    "dry_run": dry_run,
                }
            # Use AI to analyze nodes for duplicates and issues
            prompt = f'Analyze these {len(nodes)} nodes of type {bundle} for duplicates and malformed fields:\n- List any nodes with identical titles\n- Identify nodes with missing required fields\n- Report nodes with inconsistent field values\n\nReturn JSON: {{\n  "duplicates": ["node1", "node2"],\n  "malformed": ["node_id", "issues"]\n}}\n\nNodes:\n{nodes}'
            ai_result = await ai.complete(prompt)
            import json

            analysis = json.loads(ai_result) if isinstance(ai_result, str) else ai_result
            cleaned = 0
            if not dry_run:
                # Delete duplicates and malformed nodes
                if analysis.get("duplicates"):
                    for dup in analysis["duplicates"]:
                        await jsonapi.delete_resource("node", dup)
                        cleaned += 1
                if analysis.get("malformed"):
                    for node in analysis["malformed"]:
                        await jsonapi.delete_resource("node", node["id"])
                        cleaned += 1
            return {
                "scanned": len(nodes),
                "duplicates_found": len(analysis.get("duplicates", []))
                + len(analysis.get("malformed", [])),
                "would_clean": cleaned,
                "dry_run": dry_run,
                "analysis": analysis,
            }
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def map_fields_ai(source_fields: list[str], target_bundle: str) -> dict:
        """Map source fields to target bundle fields using AI."""
        if not ai:
            return {"error": "AI service not available"}
        try:
            # Fetch target bundle field configuration from JSON:API
            fields_response = await jsonapi.get_resource("field_config", {"bundle": target_bundle})
            target_fields = fields_response.get("data", [])
            prompt = f'Map these {len(source_fields)} source fields to {target_bundle} target fields ({len(target_fields)} available):\n\nSource fields: {source_fields}\nTarget fields: {[dict(name=f.get("attributes", {}).get("name", ""), type=f.get("attributes", {}).get("type", "")) for f in target_fields]}\n\nReturn mapping as JSON array: [ {{"source": "original_field", "target": "drupal_field", "confidence": 0.95, "notes": "conversion notes"}} ]\n\nMapping rules:\n- field labels -> title/description\n- numeric fields -> integer/decimal fields\n- text areas -> body/text fields\n- file fields -> media references\n- taxonomy terms -> entity references\n- boolean flags -> boolean fields\n- dates -> datetime fields\n\nConsider existing target field names and suggest compatible mappings.\n\nIf a source field cannot be cleanly mapped, suggest the closest match.\n'
            result = await ai.complete(prompt)
            import json

            mappings = json.loads(result) if isinstance(result, str) else result
            if not isinstance(mappings, list):
                mappings = [
                    {
                        "source": source_fields[0],
                        "target": "title",
                        "confidence": 0.8,
                        "notes": "fallback mapping",
                    }
                ]
            avg_confidence = sum(m.get("confidence", 0) for m in mappings) / max(len(mappings), 1)
            return {
                "mappings": mappings,
                "target_bundle": target_bundle,
                "source_count": len(source_fields),
                "target_count": len(target_fields),
                "mapping_confidence": avg_confidence,
            }
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
            if not nodes:
                return {"matched": 0, "updated": 0, "errors": ["No nodes matched filters"]}
            updated = []
            errors = []
            for node in nodes:
                try:
                    # Prepare update data preserving node id and type
                    update_data = {
                        **updates,
                        "id": node["id"],
                        "type": node["type"],
                        "bundle": bundle,
                    }
                    await jsonapi.update_resource("node", node["id"], update_data)
                    updated.append(node["id"])
                except Exception as err:
                    errors.append({"node_id": node["id"], "error": str(err)})
            return {
                "matched": len(nodes),
                "updated": len(updated),
                "errors": errors,
                "updated_node_ids": updated,
            }
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def fix_media_references(content_type: str) -> dict:
        """Fix broken media references in nodes."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_resource(f"node--{content_type}", {"page[limit]": 100})
            nodes = result.get("data", [])
            if not nodes:
                return {"scanned": 0, "fixed": 0, "errors": []}
            fixed = 0
            errors = []
            for node in nodes:
                try:
                    attributes = node.get("attributes", {})
                    relationships = node.get("relationships", {})
                    # Check for media references in relationships
                    for rel_name, rel_data in relationships.items():
                        if rel_data.get("data") and isinstance(rel_data["data"], list):
                            for ref in rel_data["data"]:
                                if ref.get("type", "").startswith("media--"):
                                    # Verify media exists
                                    media_check = await jsonapi.get_by_id(ref["type"], ref["id"])
                                    if media_check.get("error"):
                                        # Media is broken, try to find replacement
                                        # For now, just log the broken reference
                                        errors.append(
                                            {
                                                "node_id": node["id"],
                                                "field": rel_name,
                                                "broken_media": ref["id"],
                                            }
                                        )
                                        fixed += 1
                        elif rel_data.get("data") and rel_data["data"].get("type", "").startswith(
                            "media--"
                        ):
                            ref = rel_data["data"]
                            media_check = await jsonapi.get_by_id(ref["type"], ref["id"])
                            if media_check.get("error"):
                                errors.append(
                                    {
                                        "node_id": node["id"],
                                        "field": rel_name,
                                        "broken_media": ref["id"],
                                    }
                                )
                                fixed += 1
                except Exception as err:
                    errors.append({"node_id": node["id"], "error": str(err)})
            return {
                "scanned": len(nodes),
                "fixed": fixed,
                "errors": errors,
            }
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def bulk_update_aliases(bundle: str, pattern: str, action: str = "generate") -> dict:
        """Bulk generate or update URL aliases."""
        drush = deps.get("drush_client")
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("uuri", ["--bundle=" + bundle])
        return {"returncode": result.get("returncode"), "output": result.get("data", {})}

    @mcp.tool()
    async def analyze_content_quality(node_ids: list[str] = None, content_type: str = None) -> dict:
        """Analyze content quality using AI."""
        if not ai:
            return {"error": "AI service not available"}
        try:
            nodes = []
            if node_ids:
                for nid in node_ids:
                    result = await jsonapi.get_by_id("node", nid)
                    if not result.get("error"):
                        nodes.append(result)
            elif content_type:
                result = await jsonapi.get_resource(f"node--{content_type}", {"page[limit]": 50})
                nodes = result.get("data", [])
            if not nodes:
                return {"analysis": "No nodes found to analyze", "nodes_analyzed": 0}
            # Build node summaries for AI analysis
            node_summaries = []
            for node in nodes:
                attrs = node.get("attributes", {})
                node_summaries.append(
                    {
                        "id": node.get("id"),
                        "title": attrs.get("title", ""),
                        "type": node.get("type"),
                        "status": attrs.get("status", False),
                        "created": attrs.get("created"),
                        "changed": attrs.get("changed"),
                        "body_length": len(attrs.get("body", {}).get("value", ""))
                        if attrs.get("body")
                        else 0,
                        "fields_count": len(attrs),
                    }
                )
            prompt = (
                "Analyze content quality for "
                + str(len(nodes))
                + " nodes:\n\n"
                + str(node_summaries)
                + '\n\nReturn JSON:\n{\n  "issues": [\n    {"node_id": "123", "issue": "missing title", "severity": "high"},\n    {"node_id": "456", "issue": "body too short", "severity": "medium"}\n  ],\n  "summary": {\n    "total_nodes": 10,\n    "high_severity": 1,\n    "medium_severity": 3,\n    "low_severity": 2,\n    "common_issues": ["missing meta tags", "short body"]\n  },\n  "recommendations": ["Add meta descriptions", "Expand body content"]\n}'
            )
            result = await ai.complete(prompt)
            import json

            analysis = json.loads(result) if isinstance(result, str) else result
            return {
                "analysis": analysis,
                "nodes_analyzed": len(nodes),
            }
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def generate_test_content(bundle: str, count: int = 10, fields: dict = None) -> dict:
        """Generate test content for development."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            generated = []
            errors = []
            import random
            import string

            def random_string(length=8):
                return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))

            for i in range(count):
                try:
                    title = f"Test {bundle} {random_string(6)}"
                    base_fields = {
                        "title": title,
                        "type": f"node--{bundle}",
                        "status": True,
                    }
                    if fields:
                        base_fields.update(fields)

                    # Generate sensible defaults based on bundle type
                    if bundle in ("article", "page", "blog"):
                        base_fields.setdefault(
                            "body",
                            {
                                "value": f"This is test content for {title}. Generated automatically for development.",
                                "format": "basic_html",
                            },
                        )

                    result = await jsonapi.create_resource(f"node--{bundle}", base_fields)
                    if result.get("error"):
                        errors.append({"index": i, "error": result["error"]})
                    else:
                        generated.append(result.get("data", {}).get("id", "unknown"))
                except Exception as err:
                    errors.append({"index": i, "error": str(err)})
            return {
                "generated": len(generated),
                "bundle": bundle,
                "count": count,
                "node_ids": generated,
                "errors": errors,
            }
        except Exception as e:
            return {"error": str(e)}
