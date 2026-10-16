# Tools Reference

Selected tools from the 412-tool catalog, documented with their parameters,
return values, and errors. The complete list lives in the
[README's Tools section](https://github.com/vloganathane/drupal-mcp-server#tools-412-total).

## Content Management

### create_node

Create a single node of the specified bundle with given fields.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `bundle` | string | Yes | Content type bundle (e.g., 'article', 'page') |
| `fields` | dict | Yes | Field values. Must include 'title' |

**Returns:** Created node data with id, type, and attributes

**Errors:**
- `ValidationError` — If 'title' is missing
- `ClientError` — If the API request fails

---

### query_nodes

Query nodes with filters, sorts, includes, and pagination.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `bundle` | string | No | — | Filter by content type |
| `filters` | dict | No | — | Field filters |
| `sorts` | list[string] | No | — | Sort order |
| `include` | string | No | "" | Relationship includes |
| `page_limit` | integer | No | 50 | Items per page (1-500) |
| `page_offset` | integer | No | 0 | Offset from start |

**Returns:** Paginated list of nodes

---

## User Management

### create_user

Create a user account.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `mail` | string | Yes | Email address |
| `name` | string | Yes | Username |
| `pass_` | string | No | Password |
| `status` | boolean | No | Active status (default: true) |
| `roles` | list[string] | No | Role machine names |

**Returns:** Created user data

---

## DevOps

### drush_command

Execute any Drush command.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `command` | string | Yes | Drush command name |
| `args` | list[string] | No | Command arguments |
| `options` | dict | No | Key-value options |

**Returns:** Command output with return code, data, stderr

**Example:**
```json
{
  "command": "cache-rebuild",
  "args": [],
  "options": {}
}
```

---

## Status & Health

### health_check

Run four read-only probes — Drush and site status, the database
connection, the JSON:API index, and the modules the other tools assume —
and get the concrete fix for each failure. Call this first when other
tools return opaque connection errors.

**Parameters:** none

**Returns:** `ok` overall, per-probe results (`drush`, `database`,
`jsonapi`, `modules`), and a `problems` list of `{check, problem, hint}`

### status_report

The site's own status report (what `/admin/reports/status` shows), with
each requirement's title, severity, description, and value. Errors and
warnings are returned by default. A failure here is usually the site's
requirements checker breaking — the drush error is returned verbatim.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `severity_filter` | string | No | One of `error`, `warning`, `info`, `ok` |
| `include_ok` | bool | No | Return the whole report, not just problems |

**Returns:** `requirements` rows, `counts` per severity, `total`

### database_updates

Pending database updates — read-only, runs nothing. Answers "did the
modules I just updated leave schema behind?".

**Parameters:** none

**Returns:** `pending` update rows, `count`, and a `hint` to back up and
run `drush updatedb` when any are pending

### available_updates

Packages with newer versions available, from `composer outdated`, grouped
into core, contrib, and other. Dev dependencies are excluded unless
`include_dev` is set (composer marks none of them itself, so they are
filtered via composer.json's require-dev). With `security_only`, the list
is intersected with `composer audit` and the advisories are attached.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `include_dev` | bool | No | Keep dev dependencies in the report |
| `security_only` | bool | No | Only outdated packages with a security advisory |

**Returns:** `core`, `contrib`, `other` package rows, `total`,
`dev_filtered`, `security_only`

### config_status

Compare active configuration with the exported sync directory —
read-only, nothing is exported or imported. An empty sync directory shows
everything as "Only in DB", which the tool calls out.

**Parameters:** none

**Returns:** `counts` and `objects` per state (`Same`, `Only in DB`,
`Different`, …), `total`

---

## Site Insight

### find_entity_references

Which bundles use reference fields targeting an entity type — "where are
tags used?" answered from field configuration. Filter by referencing
`bundle` or `field_name`. This reports where references can live, not
which rows point where; for the data, use `db_query`.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `entity_type` | string | Yes | Target type, e.g. `taxonomy_term`, `media` |
| `bundle` | string | No | Only fields on this bundle |
| `field_name` | string | No | Only this field |
| `limit` | int | No | Rows to return (1–500, default 50) |

**Returns:** `reference_fields` rows, `by_source_entity_type` counts

### search_entities

Case-insensitive substring search across node titles, user names and
emails, taxonomy term names, comment subjects, media names, and file
names — one read-only LIKE query per type, with the term escaped. Pass
`entity_types` to search fewer tables on large sites; node bodies are
not searched (use search_api for that).

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `query` | string | Yes | 1–64 characters |
| `entity_types` | list[string] | No | Subset of node, user, taxonomy_term, comment, media, file |
| `limit` | int | No | Max rows per type (1–100, default 20) |

**Returns:** `results` grouped by type, `matches`, `total`, and `skipped`
for tables that do not exist on the site

### find_entity_by_path

Resolve a URL path or alias (`/about`, `/node/123`, or a full URL) to its
entity. Internal routes are read directly; anything else goes through the
path alias table, then the resolved target is parsed the same way.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | Yes | Path, alias, or full URL (max 512 chars) |

**Returns:** `found`, the resolved `internal_path`, `entity_type`,
`entity_id`, the full `entity` resource, and the `alias` row when one was
used

---

## Exports

Bulk inventories written to a file: the tool returns only the path,
row/column counts, file size, and a three-row preview, so a 5,000-node
export never travels through the conversation. Data comes from JSON:API
pagination (newlines and accents survive intact), and the destination is
confined to the Drupal root, the system temp directory, or your home
directory — never anywhere else. Entries with no internal id — Drupal's
uid-0 anonymous user is the usual one — are skipped and counted in the
response's `skipped_without_id` field.

### export_nodes

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `content_type` | string | No | — | Limit to one bundle (e.g. 'article') |
| `include_unpublished` | boolean | No | False | Also export unpublished nodes |
| `include_fields` | boolean | No | False | Add a `fields` column of remaining values as JSON (capped at 5000 chars per value) |
| `limit` | integer | No | 0 | Rows to write (0 = no cap, max 100000) |
| `output_path` | string | No | — | Destination `.csv`/`.xlsx`; defaults to `{Drupal root}/exports/` or `/tmp/drupal-mcp-exports/` |
| `format` | string | No | `csv` | `csv` (UTF-8 with BOM) or `xlsx` |

**Returns:** `file_path`, `rows`, `columns`, `file_size_kb`, `preview`
(first 3 rows), `filters`, `truncated` (row/page cap stopped the export)

**Errors:**
- `error` — invalid bundle/format/limit, a path outside the safe roots,
  or no JSON:API client

### export_users / export_media / export_taxonomy

Same contract per entity: `export_users` includes blocked accounts (their
status column says so) plus role labels; `export_media` adds bundle,
owner, and the managed file's filename/URI, with a `media_type` filter;
`export_taxonomy` adds `usage_count`, the `used_in` fields, and a
`safe_to_delete` verdict computed from one COUNT query per field storage
targeting taxonomy terms (`vocabulary` filter, `include_usage=false` to
skip the counts). All four accept `format="xlsx"` for an Excel workbook.

## Theme Analysis

Read-only theming inspection, the counterpart of the theme_dev tools that
create things. Theme metadata comes from `drush pm:list` plus a YAML parse
of the theme's own `info.yml`, block placements from the `block--block`
JSON:API collection, and template walks resolve every path inside
DRUPAL_ROOT first — symlinks and `..` segments that leave the docroot are
rejected before any read. Tools that inspect files say so in their error
when DRUPAL_ROOT is not configured.

### theme_active

**Parameters:** (none)

**Returns:** `default`, `admin` (from `system.theme`), `enabled` (name,
label, package, path, version per theme), `enabled_count`,
`disabled_count`

**Errors:**
- `error` — Drush not available, or the theme list came back empty

### theme_info / theme_regions

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `theme_name` | string | Yes | — | Theme machine name (e.g. 'olivero') |

**Returns:** `theme_info` merges `pm:list` (status, version, path) with the
parsed info.yml: `label`, `description`, `core_version_requirement`,
`hidden`, `regions` (in declaration order), `libraries`, `dependencies`,
and `base_theme` — the chain of parents followed upward as far as the
site allows, each with `found: false` when a parent is not installed.
`theme_regions` returns each region with `block_count` and its `blocks`
(id, label, plugin, weight, status), `total_blocks`, and
`blocks_in_unknown_regions` (placements whose region the info.yml no
longer defines — they will not render).

**Errors:**
- `error` — invalid machine name, theme not installed (with `available`),
  its directory or info.yml missing under DRUPAL_ROOT, or no JSON:API
  client (`theme_regions` needs one for placements)

### theme_blocks

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `theme_name` | string | No | — | Only this theme's placements |
| `region` | string | No | — | Only this region (e.g. 'sidebar') |
| `search` | string | No | — | 1–64 chars; case-insensitive substring of label or plugin |

**Returns:** `blocks` (id, theme, region, label, plugin, weight, status,
`visibility_rules` count), `total`, `filters` — sorted by theme, region,
weight, label

**Errors:**
- `error` — invalid identifier, empty/oversized `search`, or no JSON:API
  client

### theme_templates / theme_template_overrides

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `theme_name` | string | Yes | — | Theme machine name |
| `pattern` | string | No | — | `theme_templates` only: 1–64 char case-insensitive substring of the template name (e.g. 'node--', 'views') |

**Returns:** `theme_templates` gives `count` and `templates`
(docroot-relative `path` + `bytes`) plus `truncated` when the walk hit
its file cap. `theme_template_overrides` indexes every Twig file in the
docroot once (excluding the theme itself) and splits the theme's
templates into `overrides` (same-named core/module files it shadows, with
their `sources`) and `theme_only` (theme originals), alongside
`docroot_templates_scanned`.

**Errors:**
- `error` — invalid machine name, bad pattern, theme not installed, its
  directory missing, or DRUPAL_ROOT not configured

### template_suggestions

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `entity_type` | string | Yes | — | e.g. 'node', 'block', 'taxonomy_term', 'user', 'field', 'page' |
| `bundle` | string | No | — | e.g. 'article'; unknown entity types still get the generic chain |

**Returns:** `suggestions` most-specific first (bracketed parts are
placeholders Drupal fills in — `node--article--123.html.twig` beats
`node--article.html.twig`), each with a `description` and
`in_checked_theme`: whether the default theme already ships that file,
so you know which name creating one would take effect. `checked_in` names
the theme that was checked; when DRUPAL_ROOT is unset the check is
skipped and a `note` says so instead of guessing.

**Errors:**
- `error` — invalid `entity_type` or `bundle`

### view_template_info

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `view_name` | string | Yes | — | View machine name (from `views_list`) |
| `display_id` | string | No | — | Display machine name; without it every display gets a suggestion |

**Returns:** `label` and `displays` from the JSON:API view collection
(the view's `drupal_internal__id` is the machine name, and the embedded
`display` dict is the real one — Views config names differ between
Drupal generations, `view.*` on older sites and `views.view.*` on
Drupal 11.4+, so the entity collection is the stable source), then
`suggestions` (`views-view--NAME--DISPLAY` → `views-view--NAME` →
`views-view`, marked `in_checked_theme` against the default theme when
DRUPAL_ROOT allows) and `checked_in`.

**Errors:**
- `error` — invalid identifier, no JSON:API client, view not found (with
  the `available` views the site has), or an unknown `display_id` (with
  the `displays` the view has)
