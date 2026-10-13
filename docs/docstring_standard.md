# Docstring Standard

All public functions must follow Google-style docstrings.

## Format

```python
async def function_name(param1: str, param2: int = 10) -> dict[str, Any]:
    """Short one-line description.

    Longer description if needed. Explain what the tool does, when to use it,
    and any important behavior.

    Args:
        param1: Description of param1
        param2: Description of param2 (default: 10)

    Returns:
        Description of return value structure

    Raises:
        ClientError: When the API call fails
        ValidationError: When input is invalid

    Example:
        >>> result = await function_name("test", 5)
        >>> print(result["data"]["id"])
    """
```

## Rules

1. **First line** — Imperative mood, under 80 chars, no trailing period
2. **Blank line** — After first line, before longer description
3. **Args** — Every parameter documented with type and description
4. **Returns** — Document the return structure, not just the type
5. **Raises** — List all exceptions that callers should handle
6. **Example** — Show realistic usage with expected output

## Tool-Specific Requirements

MCP tool functions must also include:

- **When to use** — What scenario this tool is designed for
- **Related tools** — Other tools commonly used with this one
- **Required permissions** — What auth scopes are needed

## Example: Complete Tool Docstring

```python
async def create_node(bundle: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Create a single node of the specified bundle with given fields.

    Use this tool to create content nodes (articles, pages, etc.) in Drupal.
    The node will be created as the authenticated user.

    Args:
        bundle: Content type bundle machine name (e.g., 'article', 'page', 'blog')
        fields: Field values as key-value pairs. Must include 'title'.
            Common fields: 'title', 'body', 'status', 'uid', 'created'
            Field format: {'body': {'value': '...', 'format': 'basic_html'}}

    Returns:
        Created node data with structure:
        {
            "data": {
                "id": "uuid",
                "type": "node--article",
                "attributes": {"title": "...", "status": true}
            }
        }

    Raises:
        ValidationError: If 'title' is missing from fields
        ClientError: If the JSON:API request fails (4xx)
        ServerError: If Drupal returns a server error (5xx)

    Example:
        >>> result = await create_node("article", {"title": "Hello World"})
        >>> print(result["data"]["id"])
        '550e8400-e29b-41d4-a716-446655440000'

    Related tools: get_node, update_node, delete_node, query_nodes
    Required permissions: drupal:write
    """
```
