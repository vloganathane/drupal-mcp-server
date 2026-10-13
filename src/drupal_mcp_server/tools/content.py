"""Content management tools for Drupal."""

import base64
import json
import mimetypes
import os
import random
import string
from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict
from ._utils import validate_pagination


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")
    ai = deps.get("ai_service")

    @mcp.tool()
    async def create_node(bundle: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Create a single node of the specified bundle with given fields."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Ensure required fields
            if "type" not in fields:
                fields["type"] = f"node--{bundle}"
            if "title" not in fields:
                return {"error": "title is required"}
            
            result = await jsonapi.create_resource(f"node--{bundle}", fields)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def get_node(nid: str, include: str = "") -> dict[str, Any]:
        """Get a single node by ID with optional relationship includes."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("node", nid, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def update_node(nid: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Update a single node by ID with given fields."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Get current node to preserve type/bundle
            current = await jsonapi.get_by_id("node", nid)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            node_type = current.get("data", {}).get("type", "node--article")

            update_data = {**fields, "id": nid, "type": node_type}
            result = await jsonapi.update_resource("node", nid, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def delete_node(nid: str) -> dict[str, Any]:
        """Delete a single node by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("node", nid)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def query_nodes(
        bundle: str | None = None,
        filters: dict[str, Any] | None = None,
        sorts: list[str] | None = None,
        include: str = "",
        fields: list[str] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """Query nodes with filters, sorts, includes, and pagination."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        pag_err = validate_pagination(page_limit, page_offset)
        if pag_err:
            return pag_err
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            if sorts:
                params["sort"] = ",".join(sorts)
            
            if include:
                params["include"] = include
            
            if fields:
                params["fields[node--article]"] = ",".join(fields)
            
            resource_type = f"node--{bundle}" if bundle else "node"
            result = await jsonapi.get_resource(resource_type, params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def upload_media(
        file_path: str,
        media_type: str = "image",
        name: str | None = None,
        alt: str = "",
        title: str = "",
    ) -> dict[str, Any]:
        """Upload a file to the media library."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Validate file path to prevent path traversal
            file_path = os.path.realpath(file_path)
            if not os.path.exists(file_path):
                return {"error": f"File not found: {file_path}"}
            if not os.path.isfile(file_path):
                return {"error": f"Not a file: {file_path}"}
            
            # Guess mime type
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/octet-stream"
            
            # Read file and encode as base64
            with open(file_path, "rb") as f:
                file_data = base64.b64encode(f.read()).decode("utf-8")
            
            filename = name or os.path.basename(file_path)
            
            # Create media entity
            media_data: dict[str, Any] = {
                "type": f"media--{media_type}",
                "name": filename,
            }
            
            # Handle different media types
            if media_type == "image":
                media_data["field_media_image"] = [{
                    "target_id": None,
                    "alt": alt,
                    "title": title or filename,
                    "file": {
                        "filename": filename,
                        "data": file_data,
                        "mime": mime_type,
                    }
                }]
            elif media_type == "audio":
                media_data["field_media_audio_file"] = [{
                    "filename": filename,
                    "data": file_data,
                    "mime": mime_type,
                }]
            elif media_type == "document":
                media_data["field_media_document"] = [{
                    "filename": filename,
                    "data": file_data,
                    "mime": mime_type,
                }]
            elif media_type == "video":
                media_data["field_media_video_file"] = [{
                    "filename": filename,
                    "data": file_data,
                    "mime": mime_type,
                }]
            else:
                # Generic file
                media_data["field_media_file"] = [{
                    "filename": filename,
                    "data": file_data,
                    "mime": mime_type,
                }]
            
            result = await jsonapi.create_resource(f"media--{media_type}", media_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def create_media(
        media_type: str,
        source_url: str,
        name: str,
        alt: str = "",
        title: str = "",
    ) -> dict[str, Any]:
        """Create media entity from a remote URL (image, video, document, etc.)."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # For remote URLs, we create media with the URL as source
            media_data: dict[str, Any] = {
                "type": f"media--{media_type}",
                "name": name,
            }
            
            # Handle different media types
            if media_type == "remote_video":
                media_data["field_media_oembed_video"] = source_url
            elif media_type == "audio":
                media_data["field_media_audio_file"] = [{
                    "uri": source_url,
                }]
            elif media_type == "document":
                media_data["field_media_document"] = [{
                    "uri": source_url,
                }]
            elif media_type == "image":
                media_data["field_media_image"] = [{
                    "target_id": None,
                    "alt": alt,
                    "title": title or name,
                    "file": {
                        "uri": source_url,
                    }
                }]
            elif media_type == "video":
                media_data["field_media_video_file"] = [{
                    "uri": source_url,
                }]
            else:
                # Generic remote file
                media_data["field_media_file"] = [{
                    "uri": source_url,
                }]
            
            result = await jsonapi.create_resource(f"media--{media_type}", media_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

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
            result = _ensure_dict(result)
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
        """Suggest AI-powered field mappings from a source field list to a target bundle.

        Reads the target bundle's available fields, then asks the AI provider to
        map each source field onto the closest target field.

        Args:
            source_fields: Field names from the source system (e.g. D7 fields).
            target_bundle: Bundle whose fields should be mapped onto.

        Returns:
            Mappings with source, target, confidence, and notes, plus aggregate
            ``mapping_confidence`` and source/target counts.
        """
        if not ai:
            return {"error": "AI service not available"}
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            fields_response = await jsonapi.get_resource("field_config", {"bundle": target_bundle})
            fields_response = _ensure_dict(fields_response)
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
        """Apply the same field updates to every node matching a set of filters.

        Args:
            bundle: Content type bundle to operate on (e.g. ``article``).
            filters: JSON:API query filters selecting the target nodes.
            updates: Field values applied to each matched node.

        Returns:
            Matched/updated counts, per-node errors, and the updated node IDs.
        """
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_resource(f"node--{bundle}", filters)
            result = _ensure_dict(result)
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
        """Find broken media references across a content type.

        Scans nodes of the given type and checks every media relationship,
        reporting references whose target media entity no longer resolves.

        Args:
            content_type: Bundle to scan (e.g. ``article``).

        Returns:
            Scanned node count, number of broken references found, and details
            of each failure (node ID and field name).
        """
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_resource(f"node--{content_type}", {"page[limit]": 100})
            result = _ensure_dict(result)
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
                                media_check = _ensure_dict(media_check)
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
        """Regenerate URL aliases for a content type via Drush uuri.

        Args:
            bundle: Bundle whose nodes should have aliases regenerated.
            pattern: URL pattern to apply (e.g. ``/blog/[node:title]``).
            action: Operation to perform; currently only ``generate``.

        Returns:
            Drush return code and parsed output.
        """
        drush = deps.get("drush_client")
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("uuri", ["--bundle=" + bundle])
        return {"returncode": result.get("returncode"), "output": result.get("data", {})}

    @mcp.tool()
    async def analyze_content_quality(node_ids: list[str] | None = None, content_type: str | None = None) -> dict[str, Any]:
        """Analyze content quality with AI for specific nodes or an entire type.

        Args:
            node_ids: Specific node IDs to analyze. Mutually exclusive with content_type.
            content_type: Bundle to analyze (up to 50 nodes).

        Returns:
            AI analysis with issues, summary, and recommendations, plus the
            number of nodes analyzed.
        """
        if not ai:
            return {"error": "AI service not available"}
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            nodes = []
            if node_ids:
                for nid in node_ids:
                    result = await jsonapi.get_by_id("node", nid)
                    result = _ensure_dict(result)
                    if not result.get("error"):
                        nodes.append(result)
            elif content_type:
                result = await jsonapi.get_resource(f"node--{content_type}", {"page[limit]": 50})
                result = _ensure_dict(result)
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
        """Generate sample nodes for a bundle to populate a development site.

        Args:
            bundle: Bundle to generate nodes for (e.g. ``article``).
            count: Number of nodes to create.
            fields: Optional field values applied to every generated node.

        Returns:
            Generated node count, the created node IDs, and any per-node errors.
        """
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
                    result = _ensure_dict(result)
                    if result.get("error"):
                        errors.append({"index": i, "error": result["error"]})
                    else:
                        generated.append(result.get("data", {}).get("id", "unknown"))
                except Exception as err:
                    errors.append({"index": i, "error": str(err)})
            return {"generated": len(generated), "bundle": bundle, "count": count, "node_ids": generated, "errors": errors}
        except Exception as e:
            return {"error": str(e)}
