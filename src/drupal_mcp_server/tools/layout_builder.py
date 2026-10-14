"""Layout Builder and Block management tools for Drupal.

Layout Builder has never exposed a JSON:API resource, so these tools talk to
the real API instead: `entity_view_display` holds the sections as the
third-party setting `layout_builder.sections`, read and written through
`LayoutBuilderEntityViewDisplay` methods, and per-entity overrides live in the
`layout_builder__layout` field via `OverridesSectionStorage`.

Everything below was mapped against a running Drupal 10 site, including three
details that are easy to get wrong and fail silently:

* `enableLayoutBuilder()` alone does not make overrides possible. The
  `layout_builder__layout` field is only created in `preSave()` when
  `isOverridable()` changes, so `setOverridable(true)` must be saved too.
* `SectionComponent` takes `(uuid, region, configuration)` - the plugin id
  belongs inside `configuration['id']`, not in the second argument.
* `appendComponent()` wants a `SectionComponent` object, not a plugin id.
"""

import base64
import json
from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict


def _b64(value: Any) -> str:
    """Encode a value for safe embedding in PHP.

    PHP string escaping is not JSON escaping: `\\uXXXX` has no meaning in a
    PHP double-quoted string, so a non-ASCII label would silently mangle.
    Base64 sidesteps quoting entirely.
    """
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _wrap(body: str) -> str:
    """Return PHP that runs `body` and prints its result as one JSON object.

    The body lives in a closure so `return` can exit early; a bare `return`
    at eval() top level is not dependable across Drush versions.
    """
    return "print json_encode((function () {\n" + body + "\n})());"


# Serialises a section storage into plain arrays for every tool below.
_PHP_SECTIONS = """function __secs($storage) {
  $out = [];
  foreach ($storage->getSections() as $i => $s) {
    $comps = [];
    foreach ($s->getComponents() as $c) {
      $comps[] = ['region' => $c->getRegion(), 'plugin' => $c->getPluginId(),
                  'weight' => $c->getWeight()];
    }
    $out[] = ['index' => $i, 'layout_id' => $s->getLayoutId(), 'components' => $comps];
  }
  return $out;
}"""


def _load_display(entity_type: str, bundle: str) -> str:
    """PHP that loads the display or returns a helpful error."""
    return (
        "$sid = base64_decode('" + _b64(entity_type) + "') . '.' . "
        "base64_decode('" + _b64(bundle) + "') . '.default';\n"
        "$d = \\Drupal::entityTypeManager()->getStorage('entity_view_display')->load($sid);\n"
        "if (!$d) {\n"
        "  return ['error' => 'No entity view display ' . $sid . '. Layout Builder "
        "configuration lives on the view display; create the display first.'];\n"
        "}\n"
    )


def _summary(entity_type: str, bundle: str) -> str:
    """PHP returning the current state of a display."""
    return _load_display(entity_type, bundle) + (
        "return ['display_id' => $sid,\n"
        "  'entity_type' => base64_decode('" + _b64(entity_type) + "'),\n"
        "  'bundle' => base64_decode('" + _b64(bundle) + "'),\n"
        "  'enabled' => $d->isLayoutBuilderEnabled(),\n"
        "  'overridable' => $d->isOverridable(),\n"
        "  'section_count' => count($d->getSections()),\n"
        "  'sections' => __secs($d)];\n"
    )


def _build_section_php(array_expr: str, lock_php: str = "false") -> str:
    """PHP that turns a section spec into a Section and appends components.

    `array_expr` is a PHP expression yielding the spec array. Accepts either
    `{"layout_id": ..., "components": [...]}` or a bare list of component
    plugin ids, because callers spell it both ways.
    """
    return (
        "$spec = " + array_expr + ";\n"
        "if (!is_array($spec)) { return ['error' => 'section must be a JSON object']; }\n"
        "$layoutId = $spec['layout_id'] ?? $spec['layout'] ?? 'layout_onecol';\n"
        "try { $sec = new \\Drupal\\layout_builder\\Section($layoutId); }\n"
        "catch (\\Throwable $e) {\n"
        "  return ['error' => 'Unknown layout plugin ' . $layoutId . ': ' . $e->getMessage()];\n"
        "}\n"
        "$defaultRegion = $sec->getDefaultRegion();\n"
        "$items = $spec['components'] ?? [];\n"
        "if (is_string($items)) { $items = [$items]; }\n"
        "if (!is_array($items)) { $items = []; }\n"
        "$added = 0;\n"
        "foreach ($items as $item) {\n"
        "  if (is_string($item)) { $plugin = $item; $conf = []; $region = $defaultRegion; }\n"
        "  else {\n"
        "    $plugin = $item['plugin'] ?? $item['id'] ?? '';\n"
        "    $conf = $item['configuration'] ?? [];\n"
        "    $region = $item['region'] ?? $defaultRegion;\n"
        "  }\n"
        "  if ($plugin === '' || !is_array($conf)) { continue; }\n"
        "  $conf['id'] = $plugin;\n"
        "  $extra = " + lock_php + " ? ['lock' => ['id' => $plugin, 'editable' => TRUE]] : [];\n"
        "  $sec->appendComponent(new \\Drupal\\layout_builder\\SectionComponent(\n"
        "    \\Drupal::service('uuid')->generate(), $region, $conf, $extra));\n"
        "  $added++;\n"
        "}\n"
    )


async def _eval(drush: Any, php: str) -> dict[str, Any]:
    """Run PHP through Drush and return the JSON it printed.

    A failed run has no `error` key - just `returncode` and `stderr` - which
    is how ten tools used to report a broken command as though it worked.
    """
    if not drush:
        return {"error": "Drush not available"}
    result = await drush.run("php:eval", [php])
    if result.get("returncode") not in (None, 0):
        detail = " ".join(str(result.get("stderr") or "").split())
        return {"error": detail or "php:eval failed"}
    data = result.get("data")
    if isinstance(data, dict) and set(data) == {"output"}:
        # Printed something that was not JSON - report it rather than return
        # an empty success.
        return {"error": str(data["output"])}
    return _ensure_dict(data) if isinstance(data, dict) else _ensure_dict(result)


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def block_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all blocks."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("block", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def block_get(
        block_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single block by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("block", block_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def block_create(
        id: str,
        label: str,
        plugin: str,
        region: str | None = None,
        settings: dict[str, Any] | None = None,
        visibility: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new block."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            block_data: dict[str, Any] = {
                "type": "block",
                "id": id,
                "label": label,
                "plugin": plugin,
            }
            if region:
                block_data["region"] = region
            if settings:
                block_data["settings"] = settings
            if visibility:
                block_data["visibility"] = visibility
            
            result = await jsonapi.create_resource("block", block_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def block_update(
        block_id: str,
        label: str | None = None,
        region: str | None = None,
        settings: dict[str, Any] | None = None,
        visibility: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a block."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("block", block_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": block_id, "type": "block"}
            if label is not None:
                update_data["label"] = label
            if region is not None:
                update_data["region"] = region
            if settings is not None:
                update_data["settings"] = settings
            if visibility is not None:
                update_data["visibility"] = visibility
            
            result = await jsonapi.update_resource("block", block_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def block_delete(
        block_id: str,
    ) -> dict[str, Any]:
        """Delete a block."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("block", block_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def block_place(
        block_id: str,
        region: str,
        weight: int = 0,
    ) -> dict[str, Any]:
        """Place a block in a region with weight."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("block", block_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data = {
                "id": block_id,
                "type": "block",
                "region": region,
                "weight": weight,
            }
            
            result = await jsonapi.update_resource("block", block_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def layout_builder_list(
        entity_type: str = "node",
        bundle: str | None = None,
    ) -> dict[str, Any]:
        """Report which entity view displays have Layout Builder enabled.

        Layouts themselves are not readable over JSON:API (see the other
        layout_builder_* tools), but the display config that switches Layout
        Builder on for a bundle is, so this returns that instead of a 404.
        """
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params: dict[str, Any] = {"filter[targetEntityType]": entity_type}
            if bundle:
                params["filter[bundle]"] = bundle
            result = await jsonapi.get_resource("entity_view_display", params)
        except Exception as e:
            return {"error": str(e)}

        rows = (result.get("data") or []) if isinstance(result, dict) else []
        displays = []
        for row in rows:
            attrs = row.get("attributes", {}) if isinstance(row, dict) else {}
            config = attrs.get("config", {}) or {}
            displays.append({
                "id": attrs.get("id") or row.get("id"),
                "entity_type": attrs.get("targetEntityType") or attrs.get("entity_type"),
                "bundle": attrs.get("bundle"),
                "view_mode": attrs.get("mode"),
                "layout_builder_enabled": bool(
                    config.get("layout_builder__enabled")
                    or attrs.get("layout_builder__enabled")
                ),
                "section_count": len(
                    config.get("layout_builder__sections")
                    or attrs.get("layout_builder__sections")
                    or []
                ),
            })
        return _ensure_dict({
            "entity_type": entity_type,
            "bundle": bundle,
            "displays": displays,
            "note": (
                "These are entity view displays. Layout Builder stores its "
                "sections inside them, so the section bodies are not exposed "
                "separately over JSON:API."
            ),
        })

    @mcp.tool()
    async def layout_builder_get(
        entity_type: str,
        bundle: str,
    ) -> dict[str, Any]:
        """Read the Layout Builder layout for an entity type and bundle.

        Returns whether Layout Builder is enabled and overridable for the
        bundle, plus every section with its layout plugin, region and
        components. This reads the real view display rather than the
        JSON:API resource that does not exist.
        """
        return await _eval(drush, _wrap(_PHP_SECTIONS + _summary(entity_type, bundle)))

    @mcp.tool()
    async def layout_builder_create(
        entity_type: str,
        bundle: str,
        layout: dict[str, Any],
        lock: bool = False,
    ) -> dict[str, Any]:
        """Replace the Layout Builder layout for a bundle.

        `layout` may be a list of section specs, `{"sections": [...]}`, or a
        single `{"layout_id": ..., "components": [...]}`. Layout Builder is
        switched on if it was off. `lock` marks each component as locked
        against per-entity editing; Layout Builder has no display-level lock,
        so this is a component lock.
        """
        return await _eval(
            drush,
            _wrap(
                _PHP_SECTIONS
                + _load_display(entity_type, bundle)
                + "$layout = json_decode(base64_decode('" + _b64(json.dumps(layout)) + "'), true);\n"
                + "$items = is_array($layout) && isset($layout['sections']) ? $layout['sections'] : $layout;\n"
                + "if (is_array($items) && isset($items['layout_id'])) { $items = [$items]; }\n"
                + "if (!is_array($items)) { $items = []; }\n"
                + "$d->removeAllSections();\n"
                + "$written = 0;\n"
                + "foreach ($items as $item) {\n"
                + "  if (!is_array($item)) { continue; }\n"
                + _build_section_php("$item", "LOCKFLAG")
                + "  $d->appendSection($sec);\n"
                + "  $written += $added;\n"
                + "}\n"
                + "if (!$d->isLayoutBuilderEnabled()) { $d->enableLayoutBuilder(); }\n"
                + "$d->save();\n"
                + "return ['display_id' => $sid, 'enabled' => $d->isLayoutBuilderEnabled(),\n"
                + "  'overridable' => $d->isOverridable(), 'sections_written' => $written,\n"
                + "  'section_count' => count($d->getSections()), 'sections' => __secs($d)];\n"
            ).replace("LOCKFLAG", "true" if lock else "false"),
        )

    @mcp.tool()
    async def layout_builder_update(
        entity_type: str,
        bundle: str,
        layout: dict[str, Any] | None = None,
        lock: bool | None = None,
    ) -> dict[str, Any]:
        """Update the Layout Builder layout for a bundle.

        With `layout` given it replaces every section, exactly like
        `layout_builder_create`. With `layout` omitted it only applies
        `lock`, or just reports the current state when both are omitted.
        """
        if layout is None:
            return await _eval(
                drush,
                _wrap(
                    _PHP_SECTIONS
                    + _summary(entity_type, bundle)
                ),
            )
        return await _eval(
            drush,
            _wrap(
                _PHP_SECTIONS
                + _load_display(entity_type, bundle)
                + "$layout = json_decode(base64_decode('" + _b64(json.dumps(layout)) + "'), true);\n"
                + "$items = is_array($layout) && isset($layout['sections']) ? $layout['sections'] : $layout;\n"
                + "if (is_array($items) && isset($items['layout_id'])) { $items = [$items]; }\n"
                + "if (!is_array($items)) { $items = []; }\n"
                + "$d->removeAllSections();\n"
                + "$written = 0;\n"
                + "foreach ($items as $item) {\n"
                + "  if (!is_array($item)) { continue; }\n"
                + _build_section_php("$item", "LOCKFLAG")
                + "  $d->appendSection($sec);\n"
                + "  $written += $added;\n"
                + "}\n"
                + "if (!$d->isLayoutBuilderEnabled()) { $d->enableLayoutBuilder(); }\n"
                + "$d->save();\n"
                + "return ['display_id' => $sid, 'enabled' => $d->isLayoutBuilderEnabled(),\n"
                + "  'overridable' => $d->isOverridable(), 'sections_written' => $written,\n"
                + "  'section_count' => count($d->getSections()), 'sections' => __secs($d)];\n"
            ).replace("LOCKFLAG", "true" if lock else "false"),
        )

    @mcp.tool()
    async def layout_builder_sections_list(
        entity_type: str,
        bundle: str,
    ) -> dict[str, Any]:
        """List the sections in a bundle's Layout Builder layout.

        Each section reports its layout plugin, and the components in it
        report region, plugin id and weight.
        """
        return await _eval(drush, _wrap(_PHP_SECTIONS + _summary(entity_type, bundle)))

    @mcp.tool()
    async def layout_builder_section_add(
        entity_type: str,
        bundle: str,
        section: dict[str, Any],
    ) -> dict[str, Any]:
        """Append a section to a bundle's Layout Builder layout.

        `section` takes `layout_id` (default `layout_onecol`) and
        `components`, which may be plugin ids or objects with `plugin`,
        `region` and `configuration`. Layout Builder is switched on if it was
        off. Returns the full section list afterwards.
        """
        spec = json.dumps(section)
        php = (
            _PHP_SECTIONS
            + _load_display(entity_type, bundle)
            + _build_section_php(
                "json_decode(base64_decode('" + _b64(spec) + "'), true)", "false"
            )
            + "if (!$d->isLayoutBuilderEnabled()) { $d->enableLayoutBuilder(); }\n"
            + "$d->appendSection($sec);\n"
            + "$d->save();\n"
            + "return ['display_id' => $sid, 'enabled' => $d->isLayoutBuilderEnabled(),\n"
            + "  'components_added' => $added,\n"
            + "  'section_count' => count($d->getSections()), 'sections' => __secs($d)];\n"
        )
        return await _eval(drush, _wrap(php))

    @mcp.tool()
    async def block_plugin_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
    ) -> dict[str, Any]:
        """List available block plugins."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("ev", [
                "exec(\"print_r(array_keys(\\Drupal::service('plugin.manager.block')->getDefinitions()));\", \\$output); print_r(\\$output);"
            ])
            return _ensure_dict({"block_plugins": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def block_region_list(
        theme: str | None = None,
    ) -> dict[str, Any]:
        """List available regions for a theme."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("ev", [
                "exec(\"\\$theme = \\Drupal::service('theme.registry')->get('" + (theme or "bartik") + "'); print_r(array_keys(\\$theme->getRegions()));\", \\$output); print_r(\\$output);"
            ])
            return _ensure_dict({"regions": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def layout_builder_override_remove(
        entity_type: str,
        bundle: str,
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        """Remove a Layout Builder override so an entity falls back to the default.

        Pass `entity_id` (for a node, its nid) to revert that one entity.
        Omit it to list the entities of this bundle that currently carry an
        override, which is what you need before you can pick one.

        Reverting clears the entity's `layout_builder__layout` field through
        `OverridesSectionStorage`, which is where Drupal keeps overrides -
        they are not config and cannot be read from `entity_view_display`.
        """
        entity_type_b64 = _b64(entity_type)
        bundle_b64 = _b64(bundle)
        id_b64 = _b64(entity_id) if entity_id is not None else ""

        php = (
            _PHP_SECTIONS
            + _load_display(entity_type, bundle)
            + "$etid = base64_decode('" + entity_type_b64 + "');\n"
            + "$bundleName = base64_decode('" + bundle_b64 + "');\n"
            + "$entity_id = base64_decode('" + id_b64 + "');\n"
            + "$storage = \\Drupal::entityTypeManager()->getStorage($etid);\n"
            + "if ($entity_id !== '') {\n"
            + "  $entity = $storage->load($entity_id);\n"
            + "  if (!$entity) {\n"
            + "    return ['error' => 'No ' . $etid . ' with id ' . $entity_id];\n"
            + "  }\n"
            + "  try { $ov = $d->getOverridesSectionStorageForEntity($entity); }\n"
            + "  catch (\\Throwable $e) {\n"
            + "    return ['error' => $etid . ' does not support Layout Builder overrides: ' . $e->getMessage()];\n"
            + "  }\n"
            + "  if (!$ov->isOverridden()) {\n"
            + "    return ['entity_id' => $entity_id, 'reverted' => FALSE,\n"
            + "      'note' => 'This entity has no Layout Builder override to remove.'];\n"
            + "  }\n"
            + "  $before = count($ov->getSections());\n"
            + "  $ov->removeAllSections();\n"
            + "  $ov->save();\n"
            + "  $entity = $storage->load($entity_id);\n"
            + "  $again = $d->getOverridesSectionStorageForEntity($entity);\n"
            + "  return ['entity_id' => $entity_id, 'reverted' => !$again->isOverridden(),\n"
            + "    'sections_removed' => $before,\n"
            + "    'sections_remaining' => count($again->getSections())];\n"
            + "}\n"
            + "$bundle_key = \\Drupal::entityTypeManager()->getDefinition($etid)->getKey('bundle');\n"
            + "$ids = (array) $storage->getQuery()->accessCheck(TRUE)\n"
            + "  ->condition($bundle_key, $bundleName)->range(0, 25)->execute();\n"
            + "$overridden = [];\n"
            + "foreach ($ids as $id) {\n"
            + "  $e = $storage->load($id);\n"
            + "  if (!$e) { continue; }\n"
            + "  try { $ov = $d->getOverridesSectionStorageForEntity($e); }\n"
            + "  catch (\\Throwable $ex) { continue; }\n"
            + "  if ($ov->isOverridden()) { $overridden[] = $id; }\n"
            + "}\n"
            + "return ['entity_type' => $etid, 'bundle' => $bundleName,\n"
            + "  'scanned' => count($ids), 'overridden' => $overridden,\n"
            + "  'note' => 'Pass entity_id to remove one of these overrides.'];\n"
        )
        return await _eval(drush, _wrap(php))
