"""Bulk entity exports that write CSV or Excel files to disk.

Exports write the rows to a file and return only its path and statistics:
a 5,000-node inventory is a few hundred kilobytes on disk, and no model
context should ever have to carry it. Data comes from JSON:API (correct
with newlines and Unicode in every value), usage counts from validated
read-only SQL, and paths are confined to the Drupal root, the system
temp directory, or the user's home directory.
"""

import json
from typing import Any

from fastmcp import FastMCP

from ..config import get_settings
from ..validation import validate_identifier, validate_single_select
from ._utils import (
    cap_value,
    flag_label,
    jsonapi_attrs,
    jsonapi_bundle,
    jsonapi_collect,
    jsonapi_rel_ids,
    safe_export_path,
    sql_output,
    sql_rows,
    write_file,
)

_NODE_COLUMNS = [
    "nid",
    "uuid",
    "type",
    "title",
    "status",
    "created",
    "changed",
    "langcode",
    "author_uid",
    "author_name",
    "path",
]
_USER_COLUMNS = ["uid", "name", "mail", "status", "roles", "created", "access", "login", "langcode"]
_MEDIA_COLUMNS = ["mid", "bundle", "name", "status", "created", "changed", "owner", "filename", "uri"]
_TERM_COLUMNS = [
    "tid",
    "vocabulary",
    "name",
    "description",
    "weight",
    "status",
    "usage_count",
    "used_in",
    "safe_to_delete",
]


async def _bundles(jsonapi: Any, type_resource: str) -> list[str]:
    """Bundle machine names from a config-entity collection (node_type etc.).

    Config collections serve UUID ids and human labels, so the machine
    name comes from the ``drupal_internal__*`` id field: ``type`` for
    node types, ``vid`` for vocabularies, ``id`` for media types.
    """
    doc = await jsonapi.get_resource(type_resource)
    rows = doc.get("data") if isinstance(doc, dict) else None
    names: list[str] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            attrs = jsonapi_attrs(row)
            for key in ("drupal_internal__type", "drupal_internal__vid", "drupal_internal__id"):
                value = attrs.get(key)
                if isinstance(value, str) and value and validate_identifier(value, "bundle") is None:
                    names.append(value)
                    break
    return sorted(set(names))


async def _taxonomy_usage(
    drush: Any, jsonapi: Any
) -> tuple[dict[str, int] | None, dict[str, list[str]] | None, str | None]:
    """Reference counts per term, per field, across the whole site.

    Finds every field storage whose target is taxonomy_term, then runs one
    ``GROUP BY target_id`` count per data table. Identifiers come from
    field configuration and are validated before touching SQL. When usage
    cannot be computed at all (no Drush, no storage listing) the counts
    come back None so the tool never presents "0 references" as fact; a
    table that cannot be counted (deleted field, no data table) is
    reported in the note, which also withholds the safe-to-delete verdict.
    """
    if not drush:
        return None, None, "Drush client not available; usage columns are empty."
    doc = await jsonapi.get_resource(
        "field_storage_config",
        {"fields[field_storage_config]": "field_name,entity_type,settings"},
    )
    rows = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        return None, None, "Could not list field storages; usage columns are empty."
    counts: dict[str, int] = {}
    used_in: dict[str, list[str]] = {}
    skipped: list[str] = []
    for storage in rows:
        if not isinstance(storage, dict):
            continue
        attrs = jsonapi_attrs(storage)
        settings = attrs.get("settings")
        target_type = settings.get("target_type") if isinstance(settings, dict) else None
        if target_type != "taxonomy_term":
            continue
        entity_type = str(attrs.get("entity_type") or "")
        field_name = str(attrs.get("field_name") or "")
        if validate_identifier(entity_type, "entity_type") or validate_identifier(field_name, "field_name"):
            skipped.append(f"{entity_type}.{field_name}")
            continue
        label = f"{entity_type}.{field_name}"
        sql = f"SELECT target_id, COUNT(*) AS uses FROM {entity_type}__{field_name} GROUP BY target_id"
        if validate_single_select(sql):
            skipped.append(label)
            continue
        try:
            result = await drush.run("sql:query", sql)
        except Exception:
            skipped.append(label)
            continue
        text, error = sql_output(result)
        if error:
            skipped.append(label)
            continue
        for row in sql_rows(text, ["target_id", "uses"]):
            term_id = str(row.get("target_id") or "")
            if not term_id:
                continue
            try:
                uses = int(str(row.get("uses") or 0))
            except ValueError:
                continue
            counts[term_id] = counts.get(term_id, 0) + uses
            used_in.setdefault(term_id, []).append(label)
    note = None
    if skipped:
        note = (
            "Not counted (field table missing or unreadable): "
            + ", ".join(sorted(set(skipped)))
            + "; usage totals exclude them."
        )
    return counts, used_in, note


def _drupal_root() -> str | None:
    """Configured Drupal root, or None when the server does not know one."""
    try:
        return get_settings().DRUPAL_ROOT
    except Exception:
        return None


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")
    drush = deps.get("drush_client")

    @mcp.tool()
    async def export_nodes(
        content_type: str | None = None,
        include_unpublished: bool = False,
        include_fields: bool = False,
        limit: int = 0,
        output_path: str | None = None,
        format: str = "csv",
    ) -> dict[str, Any]:
        """Export a node inventory to a CSV or Excel file on disk.

        Writes one row per node (id, type, title, status, dates, author,
        path) and returns only the file path and statistics, so a
        5,000-node audit never has to travel through the conversation.
        The data comes from JSON:API, so titles and bodies with newlines
        or accents survive intact.

        content_type limits the export to one bundle (for example
        "article"); unpublished nodes are left out unless asked for. With
        include_fields a final fields column carries the node's remaining
        field values as JSON, each string capped at 5000 characters. limit
        caps the rows written (0 = no cap, 100000 maximum). format is
        "csv" (UTF-8 with BOM, opens cleanly in Excel) or "xlsx". The file
        may be written only inside the Drupal root, the system temp
        directory, or your home directory; without output_path it lands in
        {Drupal root}/exports/ or /tmp/drupal-mcp-exports/ with a
        timestamped name.
        """
        if not jsonapi:
            return {"error": "JSON:API client not available"}
        if format not in ("csv", "xlsx"):
            return {"error": f"format must be 'csv' or 'xlsx' (got {format!r})"}
        if content_type is not None:
            error = validate_identifier(content_type, "content_type")
            if error:
                return {"error": error}
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0 or limit > 100000:
            return {"error": "limit must be an integer between 0 and 100000 (0 = no cap)"}

        if content_type:
            bundles = [content_type]
        else:
            bundles = await _bundles(jsonapi, "node_type")
            if not bundles:
                return {"error": "No content types found on this site"}
        params: dict[str, Any] = {"include": "uid"}

        included: dict[str, dict[str, Any]] = {}
        rows: list[list[Any]] = []
        skipped = 0
        truncated = False
        for bundle in bundles:
            if limit and len(rows) >= limit:
                truncated = True
                break
            remaining = max(limit - len(rows), 0) if limit else 0
            items, page_included, hit_cap = await jsonapi_collect(
                jsonapi, f"node--{bundle}", params, remaining
            )
            truncated = truncated or hit_cap
            included.update(page_included)
            for item in items:
                row = _node_row(item, included, include_fields)
                if row is None:
                    skipped += 1
                    continue
                if not include_unpublished and not jsonapi_attrs(item).get("status"):
                    continue
                rows.append(row)
        if limit and len(rows) > limit:
            rows = rows[:limit]
            truncated = True

        filters = {
            "content_type": content_type,
            "include_unpublished": include_unpublished,
            "include_fields": include_fields,
            "limit": limit,
        }
        if not rows:
            return {
                "rows": 0,
                "note": "No nodes matched; no file was written.",
                "filters": filters,
                "skipped_without_id": skipped,
            }

        columns = list(_NODE_COLUMNS)
        if include_fields:
            columns.append("fields")
        return _finish_export(
            output_path, f"nodes_{content_type or 'all'}", format, columns, rows, drupal_root=_drupal_root()
        ) | {
            "filters": filters,
            "truncated": truncated,
            "skipped_without_id": skipped,
            **(
                {"note": "Row limit or the 100000-row page cap stopped the export; it may be incomplete."}
                if truncated
                else {}
            ),
        }

    @mcp.tool()
    async def export_users(
        limit: int = 0,
        output_path: str | None = None,
        format: str = "csv",
    ) -> dict[str, Any]:
        """Export the site's user accounts to a CSV or Excel file on disk.

        One row per user: id, name, email, active/blocked status, role
        labels, registration/last-login dates. Blocked accounts are always
        included (their status column says so) - an audit needs them. The
        file lands in {Drupal root}/exports/ or /tmp/drupal-mcp-exports/
        unless output_path says otherwise (confined to the Drupal root,
        the temp directory, or your home). Drupal's uid-0 anonymous
        pseudo-account carries no id attributes and is skipped rather
        than exported as a row of nulls (see skipped_without_id).
        """
        if not jsonapi:
            return {"error": "JSON:API client not available"}
        if format not in ("csv", "xlsx"):
            return {"error": f"format must be 'csv' or 'xlsx' (got {format!r})"}
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0 or limit > 100000:
            return {"error": "limit must be an integer between 0 and 100000 (0 = no cap)"}

        items, included, truncated = await jsonapi_collect(
            jsonapi, "user--user", {"include": "roles"}, limit
        )
        rows: list[list[Any]] = []
        skipped = 0
        for item in items:
            row = _user_row(item, included)
            if row is None:
                skipped += 1
                continue
            rows.append(row)
        if limit and len(rows) > limit:
            rows = rows[:limit]
            truncated = True

        if not rows:
            return {
                "rows": 0,
                "note": "No users found; no file was written.",
                "filters": {"limit": limit},
                "skipped_without_id": skipped,
            }
        return _finish_export(
            output_path, "users", format, _USER_COLUMNS, rows, drupal_root=_drupal_root()
        ) | {
            "filters": {"limit": limit},
            "truncated": truncated,
            "skipped_without_id": skipped,
            **(
                {"note": "Row limit or the 100000-row page cap stopped the export; it may be incomplete."}
                if truncated
                else {}
            ),
        }

    @mcp.tool()
    async def export_media(
        media_type: str | None = None,
        limit: int = 0,
        output_path: str | None = None,
        format: str = "csv",
    ) -> dict[str, Any]:
        """Export the media library to a CSV or Excel file on disk.

        One row per media item: id, bundle, name, status, dates, owner,
        and the managed file's filename and URI when there is one (found
        through relationships, so renamed file fields still work).
        media_type limits the export to a bundle such as "image". Empty
        sites write nothing and say so.
        """
        if not jsonapi:
            return {"error": "JSON:API client not available"}
        if format not in ("csv", "xlsx"):
            return {"error": f"format must be 'csv' or 'xlsx' (got {format!r})"}
        if media_type is not None:
            error = validate_identifier(media_type, "media_type")
            if error:
                return {"error": error}
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0 or limit > 100000:
            return {"error": "limit must be an integer between 0 and 100000 (0 = no cap)"}

        if media_type:
            bundles = [media_type]
        else:
            bundles = await _bundles(jsonapi, "media_type")
            if not bundles:
                return {"error": "No media types found on this site"}

        included: dict[str, dict[str, Any]] = {}
        rows: list[list[Any]] = []
        skipped = 0
        truncated = False
        for bundle in bundles:
            if limit and len(rows) >= limit:
                truncated = True
                break
            remaining = max(limit - len(rows), 0) if limit else 0
            items, page_included, hit_cap = await jsonapi_collect(
                jsonapi, f"media--{bundle}", {"include": "field_media_file,uid"}, remaining
            )
            truncated = truncated or hit_cap
            included.update(page_included)
            for item in items:
                row = _media_row(item, included)
                if row is None:
                    skipped += 1
                    continue
                rows.append(row)
        if limit and len(rows) > limit:
            rows = rows[:limit]
            truncated = True

        filters = {"media_type": media_type, "limit": limit}
        if not rows:
            return {
                "rows": 0,
                "note": "No media found; no file was written.",
                "filters": filters,
                "skipped_without_id": skipped,
            }
        return _finish_export(
            output_path, f"media_{media_type or 'all'}", format, _MEDIA_COLUMNS, rows,
            drupal_root=_drupal_root(),
        ) | {
            "filters": filters,
            "truncated": truncated,
            "skipped_without_id": skipped,
            **(
                {"note": "Row limit or the 100000-row page cap stopped the export; it may be incomplete."}
                if truncated
                else {}
            ),
        }

    @mcp.tool()
    async def export_taxonomy(
        vocabulary: str | None = None,
        include_usage: bool = True,
        limit: int = 0,
        output_path: str | None = None,
        format: str = "csv",
    ) -> dict[str, Any]:
        """Export taxonomy terms to a CSV or Excel file on disk.

        One row per term: id, vocabulary, name, description, weight,
        status, and - with include_usage (the default) - how many entities
        reference the term, through which fields, and a safe_to_delete
        verdict ("yes" only when nothing references it, and withheld
        entirely whenever some field could not be counted). Usage comes
        from one COUNT query per field storage targeting taxonomy terms,
        so a 5,000-term vocabulary costs a handful of queries, not 5,000.

        vocabulary limits the export to one vocabulary machine name (for
        example "tags"). When Drush is unavailable the export still
        succeeds and says the usage columns are empty.
        """
        if not jsonapi:
            return {"error": "JSON:API client not available"}
        if format not in ("csv", "xlsx"):
            return {"error": f"format must be 'csv' or 'xlsx' (got {format!r})"}
        if vocabulary is not None:
            error = validate_identifier(vocabulary, "vocabulary")
            if error:
                return {"error": error}
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0 or limit > 100000:
            return {"error": "limit must be an integer between 0 and 100000 (0 = no cap)"}

        if vocabulary:
            term_types = [f"taxonomy_term--{vocabulary}"]
        else:
            vocabularies = await _bundles(jsonapi, "taxonomy_vocabulary")
            # No vocabularies means no terms, so there is nothing to page.
            # Never fall back to the bare taxonomy_term collection here: it
            # merges bundles behind one shared offset, which skips rows.
            term_types = [f"taxonomy_term--{name}" for name in vocabularies]

        usage_counts: dict[str, int] | None = None
        used_in: dict[str, list[str]] | None = None
        usage_note: str | None = None
        if include_usage:
            usage_counts, used_in, usage_note = await _taxonomy_usage(drush, jsonapi)
        # A safe-to-delete "yes" is only honest when every reference field
        # was actually counted: any gap (note present) withholds it.
        verdict_ok = include_usage and usage_note is None

        filters = {"vocabulary": vocabulary, "include_usage": include_usage, "limit": limit}
        if not term_types:
            return {
                "rows": 0,
                "note": "No vocabularies found; no file was written.",
                "filters": filters,
                **({"usage_note": usage_note} if usage_note else {}),
            }

        included: dict[str, dict[str, Any]] = {}
        rows: list[list[Any]] = []
        skipped = 0
        truncated = False
        for item_type in term_types:
            if limit and len(rows) >= limit:
                truncated = True
                break
            remaining = max(limit - len(rows), 0) if limit else 0
            items, page_included, hit_cap = await jsonapi_collect(jsonapi, item_type, {}, remaining)
            truncated = truncated or hit_cap
            included.update(page_included)
            for item in items:
                row = _term_row(item, usage_counts, used_in, verdict_ok)
                if row is None:
                    skipped += 1
                    continue
                rows.append(row)
        if limit and len(rows) > limit:
            rows = rows[:limit]
            truncated = True

        if not rows:
            return {
                "rows": 0,
                "note": "No terms matched; no file was written.",
                "filters": filters,
                "skipped_without_id": skipped,
                **({"usage_note": usage_note} if usage_note else {}),
            }
        result = _finish_export(
            output_path, f"taxonomy_{vocabulary or 'all'}", format, _TERM_COLUMNS, rows,
            drupal_root=_drupal_root(),
        ) | {
            "filters": filters,
            "truncated": truncated,
            "skipped_without_id": skipped,
            **(
                {"note": "Row limit or the 100000-row page cap stopped the export; it may be incomplete."}
                if truncated
                else {}
            ),
        }
        if usage_note:
            result["usage_note"] = usage_note
        return result


def _node_row(
    item: dict[str, Any], included: dict[str, dict[str, Any]], include_fields: bool
) -> list[Any] | None:
    attrs = jsonapi_attrs(item)
    nid = attrs.get("drupal_internal__nid")
    if nid is None:
        return None
    author_ids = jsonapi_rel_ids(item, "uid")
    author_attrs = jsonapi_attrs(included[author_ids[0]]) if author_ids and author_ids[0] in included else {}
    path = attrs.get("path")
    alias = path.get("alias") if isinstance(path, dict) else None
    row: list[Any] = [
        nid,
        item.get("id"),
        jsonapi_bundle(item),
        attrs.get("title"),
        flag_label(attrs.get("status"), "published", "unpublished"),
        attrs.get("created"),
        attrs.get("changed"),
        attrs.get("langcode"),
        author_attrs.get("drupal_internal__uid"),
        author_attrs.get("name"),
        alias or (f"/node/{nid}" if nid is not None else None),
    ]
    if include_fields:
        consumed = {
            "drupal_internal__nid",
            "drupal_internal__vid",
            "title",
            "status",
            "created",
            "changed",
            "langcode",
            "path",
        }
        extra = {key: cap_value(value) for key, value in attrs.items() if key not in consumed}
        row.append(json.dumps(extra, ensure_ascii=False, default=str))
    return row


def _user_row(item: dict[str, Any], included: dict[str, dict[str, Any]]) -> list[Any] | None:
    attrs = jsonapi_attrs(item)
    uid = attrs.get("drupal_internal__uid")
    if uid is None:
        return None
    role_names: list[str] = []
    for role_id in jsonapi_rel_ids(item, "roles"):
        role = included.get(role_id)
        role_attrs = jsonapi_attrs(role) if role else {}
        label = role_attrs.get("label") or role_attrs.get("name") or (jsonapi_bundle(role) if role else None)
        role_names.append(str(label) if label else role_id)
    return [
        uid,
        attrs.get("name"),
        attrs.get("mail"),
        flag_label(attrs.get("status"), "active", "blocked"),
        ", ".join(role_names),
        attrs.get("created"),
        attrs.get("access"),
        attrs.get("login"),
        attrs.get("langcode"),
    ]


def _media_row(item: dict[str, Any], included: dict[str, dict[str, Any]]) -> list[Any] | None:
    attrs = jsonapi_attrs(item)
    mid = attrs.get("drupal_internal__mid")
    if mid is None:
        return None
    owner_ids = jsonapi_rel_ids(item, "uid")
    owner_attrs = jsonapi_attrs(included[owner_ids[0]]) if owner_ids and owner_ids[0] in included else {}
    filename: Any = None
    uri: Any = None
    relationships = item.get("relationships")
    if isinstance(relationships, dict):
        for relationship in relationships:
            if filename is not None:
                break
            for rel_id in jsonapi_rel_ids(item, relationship):
                resource = included.get(rel_id)
                if resource and str(resource.get("type", "")).startswith("file--"):
                    file_attrs = jsonapi_attrs(resource)
                    filename = file_attrs.get("filename")
                    uri = file_attrs.get("uri")
                    break
    return [
        mid,
        jsonapi_bundle(item),
        attrs.get("name"),
        flag_label(attrs.get("status"), "active", "disabled"),
        attrs.get("created"),
        attrs.get("changed"),
        owner_attrs.get("name"),
        filename,
        uri,
    ]


def _term_row(
    item: dict[str, Any],
    usage_counts: dict[str, int] | None,
    used_in: dict[str, list[str]] | None,
    verdict_ok: bool,
) -> list[Any] | None:
    attrs = jsonapi_attrs(item)
    tid = attrs.get("drupal_internal__tid")
    if tid is None:
        return None
    if usage_counts is None or used_in is None:
        count: Any = ""
        fields: Any = ""
        safe: Any = ""
    else:
        count = usage_counts.get(str(tid), 0)
        fields = ", ".join(sorted(set(used_in.get(str(tid), []))))
        # Never claim "safe to delete" off partial knowledge: counts with a
        # note attached are missing some field's contributions.
        safe = "" if not verdict_ok else ("yes" if count == 0 else "no")
    return [
        tid,
        jsonapi_bundle(item),
        attrs.get("name"),
        attrs.get("description"),
        attrs.get("weight"),
        flag_label(attrs.get("status"), "active", "disabled"),
        count,
        fields,
        safe,
    ]


def _finish_export(
    output_path: str | None,
    default_stem: str,
    fmt: str,
    columns: list[str],
    rows: list[list[Any]],
    drupal_root: str | None,
) -> dict[str, Any]:
    path, error = safe_export_path(output_path, default_stem, fmt, drupal_root)
    if error:
        return {"error": error}
    assert path is not None
    return write_file(path, columns, rows, fmt)
