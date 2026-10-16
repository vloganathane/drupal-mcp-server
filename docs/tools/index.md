# Tools Reference

Selected tools from the 392-tool catalog, documented with their parameters,
return values, and errors. The complete list lives in the
[README's Tools section](https://github.com/vloganathane/drupal-mcp-server#tools-392-total).

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
