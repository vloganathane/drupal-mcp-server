"""Revision management tools for Drupal.

Drupal's JSON:API can read one *specific* revision via ``?resourceVersion=id:<vid>``,
but it exposes no revision collection: ``.../revisions`` answers 405 Method Not
Allowed, and no core drush command enumerates them either. Only the REST module
offers that. So list/delete report the limitation instead of building a URL that
can never exist.
"""

from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict

# Server-managed attributes. Sending these back on a revert is rejected by
# Drupal as read-only; excluding them is also what makes a revert a revert
# rather than an attempt to rewrite the entity's identity.
_READ_ONLY = frozenset({
    "drupal_internal__nid", "drupal_internal__vid", "drupal_internal__uid",
    "drupal_internal__tid", "drupal_internal__cid", "drupal_internal__mid",
    "drupal_internal__fid", "drupal_internal__lid", "drupal_internal__pid",
    "uuid", "vid", "hash", "created", "changed", "login", "init", "access",
    "revision_timestamp", "revision_uid", "revision_log",
    "revision_translation_affected", "default_langcode",
    "content_translation_source", "content_translation_outdated",
    "path", "links", "comment_count", "comment_count_new",
    "last_comment_timestamp", "feed_nid", "feeds_item_guid", "feeds_item_url",
    "is_new", "has_new_content", "search_api_id", "search_api_relevance",
    "search_api_excerpt", "search_api_language",
})

_NO_COLLECTION = (
    "Drupal's JSON:API has no revision collection endpoint "
    "(.../revisions answers 405 Method Not Allowed) and no core drush command "
    "enumerates revisions. Enable the REST module to list or delete individual "
    "revisions, or use revision_get/revision_diff once you know a revision ID."
)


def _type(entity_type: str) -> str:
    """Normalise the forms callers use: 'node', 'node/article', 'node--article'."""
    cleaned = entity_type.strip().strip("/")
    return cleaned.replace("/", "--") if "/" in cleaned else cleaned


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def revision_list(
        entity_type: str,
        entity_id: str,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List revisions for an entity.

        Only the *current* revision is enumerable over JSON:API; the tool
        reports that honestly rather than inventing a collection URL.
        """
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id(_type(entity_type), entity_id)
            data = current.get("data", {}) if isinstance(current, dict) else {}
            attrs = data.get("attributes", {})
            return _ensure_dict({
                "entity_type": entity_type,
                "entity_id": entity_id,
                "current": {
                    "revision_id": attrs.get("drupal_internal__vid"),
                    "revision_timestamp": attrs.get("revision_timestamp"),
                    "type": data.get("type"),
                },
                "revisions": [],
                "limitation": _NO_COLLECTION,
            })
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def revision_get(
        entity_type: str,
        entity_id: str,
        revision_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a specific revision of an entity."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"include": include} if include else None
            result = await jsonapi.get_revision(
                _type(entity_type), entity_id, revision_id, params=params
            )
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def revision_revert(
        entity_type: str,
        entity_id: str,
        revision_id: str,
    ) -> dict[str, Any]:
        """Revert an entity to a specific revision.

        Applies the revision's field values to the current entity. A PATCH that
        Drupal rejects is atomic, so a failure leaves the entity untouched.
        """
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            normalized = _type(entity_type)
            current = await jsonapi.get_by_id(normalized, entity_id)
            revision = await jsonapi.get_revision(normalized, entity_id, revision_id)

            current_data = current.get("data", {}) if isinstance(current, dict) else {}
            revision_data = revision.get("data", {}) if isinstance(revision, dict) else {}

            cur_attrs = current_data.get("attributes", {})
            rev_attrs = revision_data.get("attributes", {})

            # Only fields that actually differ and are safe to write.
            changed = {
                key: value
                for key, value in rev_attrs.items()
                if key not in _READ_ONLY and cur_attrs.get(key) != value
            }

            if not changed:
                return _ensure_dict({
                    "entity_id": entity_id,
                    "revision_id": revision_id,
                    "reverted": True,
                    "fields_changed": [],
                    "detail": "Entity already matches this revision.",
                })

            await jsonapi.update_resource(normalized, entity_id, {
                "id": revision_data.get("id"),
                "type": revision_data.get("type"),
                "attributes": changed,
            })
            return _ensure_dict({
                "entity_id": entity_id,
                "revision_id": revision_id,
                "reverted": True,
                "fields_changed": sorted(changed),
            })
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def revision_delete(
        entity_type: str,
        entity_id: str,
        revision_id: str,
    ) -> dict[str, Any]:
        """Delete a specific revision of an entity."""
        return _ensure_dict({"error": _NO_COLLECTION})

    @mcp.tool()
    async def revision_diff(
        entity_type: str,
        entity_id: str,
        revision_id_1: str,
        revision_id_2: str,
    ) -> dict[str, Any]:
        """Diff two revisions of an entity."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            normalized = _type(entity_type)
            rev1 = await jsonapi.get_revision(normalized, entity_id, revision_id_1)
            rev2 = await jsonapi.get_revision(normalized, entity_id, revision_id_2)

            attrs1 = (rev1.get("data", {}) or {}).get("attributes", {})
            attrs2 = (rev2.get("data", {}) or {}).get("attributes", {})

            differences = [
                {"field": key, "from": attrs1.get(key), "to": attrs2.get(key)}
                for key in sorted(set(attrs1) | set(attrs2))
                if attrs1.get(key) != attrs2.get(key)
            ]
            return {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "revision_1": revision_id_1,
                "revision_2": revision_id_2,
                "differences": differences,
                "has_changes": bool(differences),
            }
        except Exception as e:
            return {"error": str(e)}
