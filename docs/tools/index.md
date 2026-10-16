# Tools Reference

Selected tools from the 400-tool catalog, documented with their parameters,
return values, and errors. The complete list lives in the
[README's Tools section](https://github.com/vloganathane/drupal-mcp-server#tools-400-total).

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
