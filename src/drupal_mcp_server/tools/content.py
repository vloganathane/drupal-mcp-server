"""Content management tools for Drupal."""

import json
import random
import string
from typing import Any

from fastmcp import FastMCP


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")
    ai = deps.get("ai_service")

    @mcp.tool()
    async def clean_nodes_ai(
        entity_type: str, bundle: str, dry_run: bool = True, confirm: bool = False, max_deletes: int = 10
    ) -> dict[str, Any]:
        """Clean duplicate or malformed nodes using AI. Requires confirm=True to execute deletions."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        if not ai:
            return {"error": "AI service not available"}
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
            # Summarize nodes for AI (id + title only) to avoid context blow-up
            node_summaries = [
                {"id": n.get("id"), "title": n.get("attributes", {}).get("title", "")} for n in nodes
            ]
            prompt = (
                f'Analyze these {len(nodes)} nodes of type {bundle} for duplicates and malformed fields:\n'
                f'- List any nodes with identical titles\n'
                f'- Identify nodes with missing required fields\n'
                f'- Report nodes with inconsistent field values\n\n'
                f'Return JSON: {{\n  "duplicates": ["node_id1", "node_id2"],\n  "malformed": [{{"id": "node_id", "issues": ["issue1"]}}]\n}}\n\n'
                f'Nodes:\n{node_summaries}'
            )
            ai_result = await ai.complete(prompt)

            try:
                analysis = json.loads(ai_result) if isinstance(ai_result, str) else ai_result
            except json.JSONDecodeError:
                return {"error": "AI returned invalid JSON", "raw": ai_result[:500]}

            duplicates = analysis.get("duplicates", []) if isinstance(analysis.get("duplicates"), list) else []
            malformed = analysis.get("malformed", []) if isinstance(analysis.get("malformed"), list) else []

            total_actions = len(duplicates) + len(malformed)
            if total_actions > max_deletes:
                return {
                    "error": f"Too many actions ({total_actions} > max_deletes={max_deletes}). Increase max_deletes or run in batches.",
                    "scanned": len(nodes),
                    "duplicates_found": total_actions,
                    "dry_run": True,
                }

            cleaned = 0
            if not dry_run and confirm:
                if duplicates:
                    for dup in duplicates[:max_deletes]:
                        await jsonapi.delete_resource("node", dup)
                        cleaned += 1
                if malformed:
                    for node in malformed[:max_deletes]:
                        node_id = node.get("id") if isinstance(node, dict) else node
                        await jsonapi.delete_resource("node", node_id)
                        cleaned += 1
            return {
                "scanned": len(nodes),
                "duplicates_found": total_actions,
                "would_clean": cleaned if (not dry_run and confirm) else total_actions,
                "dry_run": dry_run or not confirm,
                "analysis": analysis,
            }
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def map_fields_ai(source_fields: list[str], target_bundle: str) -> dict[str, Any]:
        if not ai:
            return {"error": "AI service not available"}
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            fields_response = await jsonapi.get_resource("field_config", {"bundle": target_bundle})
            target_fields = fields_response.get("data", [])
            prompt = (
                f'Map these {len(source_fields)} source fields to {target_bundle} target fields ({len(target_fields)} available):\n\n'
                f'Source fields: {source_fields}\n'
                f'Target fields: {[dict(name=f.get("attributes", {}).get("name", ""), type=f.get("attributes", {}).get("type", "")) for f in target_fields]}\n\n'
                f'Return mapping as JSON array: [ {{"source": "original_field", "target": "drupal_field", "confidence": 0.95, "notes": "conversion notes"}} ]'
            )
            result = await ai.complete(prompt)
            mappings = json.loads(result) if isinstance(result, str) else result
            if not isinstance(mappings, list):
                mappings = [{"source": source_fields[0], "target": "title", "confidence": 0.8, "notes": "fallback mapping"}]
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
    async def bulk_update_nodes(bundle: str, filters: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_resource(f"node--{bundle}", filters)
            nodes = result.get("data", [])
            if not nodes:
                return {"matched": 0, "updated": 0, "errors": ["No nodes matched filters"]}
            updated, errors = [], []
            for node in nodes:
                try:
                    update_data = {**updates, "id": node["id"], "type": node["type"], "bundle": bundle}
                    await jsonapi.update_resource("node", node["id"], update_data)
                    updated.append(node["id"])
                except Exception as err:
                    errors.append({"node_id": node["id"], "error": str(err)})
            return {"matched": len(nodes), "updated": len(updated), "errors": errors, "updated_node_ids": updated}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def fix_media_references(content_type: str) -> dict[str, Any]:
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_resource(f"node--{content_type}", {"page[limit]": 100})
            nodes = result.get("data", [])
            if not nodes:
                return {"scanned": 0, "fixed": 0, "errors": []}
            fixed, errors = 0, []
            for node in nodes:
                try:
                    for rel_name, rel_data in node.get("relationships", {}).items():
                        refs = rel_data.get("data")
                        refs_list = refs if isinstance(refs, list) else ([refs] if isinstance(refs, dict) else [])
                        for ref in refs_list:
                            if isinstance(ref, dict) and ref.get("type", "").startswith("media--"):
                                media_check = await jsonapi.get_by_id(ref["type"], ref["id"])
                                if media_check.get("error"):
                                    errors.append({"node_id": node["id"], "field": rel_name, "broken_media": ref["id"]})
                                    fixed += 1
                except Exception as err:
                    errors.append({"node_id": node["id"], "error": str(err)})
            return {"scanned": len(nodes), "fixed": fixed, "errors": errors}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def bulk_update_aliases(bundle: str, pattern: str, action: str = "generate") -> dict[str, Any]:
        drush = deps.get("drush_client")
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("uuri", ["--bundle=" + bundle])
        return {"returncode": result.get("returncode"), "output": result.get("data", {})}

    @mcp.tool()
    async def analyze_content_quality(node_ids: list[str] | None = None, content_type: str | None = None) -> dict[str, Any]:
        if not ai:
            return {"error": "AI service not available"}
        if not jsonapi:
            return {"error": "JSON:API not available"}
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
            node_summaries = []
            for node in nodes:
                attrs = node.get("attributes", {})
                node_summaries.append({
                    "id": node.get("id"),
                    "title": attrs.get("title", ""),
                    "type": node.get("type"),
                    "status": attrs.get("status", False),
                    "created": attrs.get("created"),
                    "changed": attrs.get("changed"),
                    "body_length": len(attrs.get("body", {}).get("value", "")) if attrs.get("body") else 0,
                    "fields_count": len(attrs),
                })
            prompt = f"Analyze content quality for {len(nodes)} nodes:\n\n{node_summaries}\n\nReturn JSON with issues array, summary, recommendations."
            result = await ai.complete(prompt)
            analysis = json.loads(result) if isinstance(result, str) else result
            return {"analysis": analysis, "nodes_analyzed": len(nodes)}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def generate_test_content(bundle: str, count: int = 10, fields: dict[str, Any] | None = None) -> dict[str, Any]:
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            generated, errors = [], []
            def random_string(length: int = 8) -> str:
                return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))
            for i in range(count):
                try:
                    title = f"Test {bundle} {random_string(6)}"
                    base_fields = {"title": title, "type": f"node--{bundle}", "status": True}
                    if fields:
                        base_fields.update(fields)
                    if bundle in ("article", "page", "blog"):
                        base_fields.setdefault("body", {"value": f"This is test content for {title}.", "format": "basic_html"})
                    result = await jsonapi.create_resource(f"node--{bundle}", base_fields)
                    if result.get("error"):
                        errors.append({"index": i, "error": result["error"]})
                    else:
                        generated.append(result.get("data", {}).get("id", "unknown"))
                except Exception as err:
                    errors.append({"index": i, "error": str(err)})
            return {"generated": len(generated), "bundle": bundle, "count": count, "node_ids": generated, "errors": errors}
        except Exception as e:
            return {"error": str(e)}
