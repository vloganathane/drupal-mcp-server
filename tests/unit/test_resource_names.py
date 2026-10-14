"""Every JSON:API resource name our tools ask for must be a real entity type.

`views_list` requested `views_view`, which has not been the entity type since
Drupal 8 -- it is `view`. Views was installed and healthy, but every views tool
404'd, and the sweep read that as "module not installed" and as ordinary lookup
misses. A wrong resource name is indistinguishable from a missing module unless
something checks the name itself, which is what this does.

The table below is Drupal's own entity type ids, so a tool that invents one
fails here rather than in a live run against a site nobody has set up.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "drupal_mcp_server"

_CALL = re.compile(
    r"(get_resource|get_by_id|create_resource|update_resource|delete_resource)"
    r"\(\s*(?:resource_type\s*=\s*)?[\"']([A-Za-z0-9_.-]+)[\"']"
)

# Entity type ids that exist in Drupal core or in the contrib projects the
# tools support. A config entity's bundle is the entity type itself, so the
# resource is addressed as `entity--entity`; only the first half is checked.
KNOWN_ENTITY_TYPES = {
    # core
    "action",
    "base_field_override",
    "block",
    "block_content",
    "block_content_type",
    "comment",
    "contact_form",
    "contact_message",
    "content_moderation_state",
    "date_format",
    "editor",
    "entity_form_display",
    "entity_form_mode",
    "entity_view_display",
    "entity_view_mode",
    "field_config",
    "field_storage_config",
    "file",
    "filter_format",
    "image_style",
    "configurable_language",
    "media",
    "media_type",
    "menu",
    "menu_link_content",
    "node",
    "node_type",
    "path_alias",
    "taxonomy_term",
    "taxonomy_vocabulary",
    "user",
    "user_role",
    "view",
    "workflow",
    # contrib
    "commerce_order",
    "commerce_payment_gateway",
    "commerce_product",
    "commerce_promotion",
    "commerce_shipping_method",
    "commerce_store",
    "facets_facet",
    "facets_facet_source",
    "feeds_feed",
    "metatag_defaults",
    "paragraph",
    "paragraphs_type",
    "pathauto_pattern",
    "redirect",
    "search_api_index",
    "search_api_server",
    "webform",
    "webform_submission",
}

# Not entity types, but legitimately passed to the client. `jsonapi` is the
# index document, addressed by get_index().
NON_ENTITY_RESOURCES = {"jsonapi"}


def _resource_names() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            for match in _CALL.finditer(line):
                name = match.group(2)
                if "--" in name:
                    name = name.split("--", 1)[0]
                found.setdefault(name, []).append(f"{path.name}:{lineno}")
    return found


def test_the_scanner_actually_finds_the_call_sites():
    """Guards the guard: an empty match set would pass trivially."""
    names = _resource_names()
    assert len(names) > 20, "the resource-name scanner matched almost nothing"
    assert "node" in names


def test_every_resource_name_is_a_real_entity_type():
    unknown = {
        name: sites
        for name, sites in _resource_names().items()
        if name not in KNOWN_ENTITY_TYPES and name not in NON_ENTITY_RESOURCES
    }
    assert not unknown, (
        "tools request JSON:API resources that do not exist in Drupal, so they "
        "404 on a perfectly healthy site and read as 'module not installed':\n"
        + "\n".join(f"  {n}  ({', '.join(s)})" for n, s in sorted(unknown.items()))
    )
