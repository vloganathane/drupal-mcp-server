"""GraphQL client for Drupal."""

from typing import Any

from .base import DrupalBaseClient

# Standard GraphQL introspection query; enough to render both JSON and SDL.
_INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types { ...FullType }
    directives {
      name
      description
      locations
      args { ...InputValue }
    }
  }
}
fragment FullType on __Type {
  kind
  name
  description
  fields(includeDeprecated: true) {
    name
    description
    args { ...InputValue }
    type { ...TypeRef }
    isDeprecated
    deprecationReason
  }
  inputFields { ...InputValue }
  interfaces { ...TypeRef }
  enumValues(includeDeprecated: true) {
    name
    description
    isDeprecated
    deprecationReason
  }
  possibleTypes { ...TypeRef }
}
fragment InputValue on __InputValue {
  name
  description
  type { ...TypeRef }
  defaultValue
}
fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType {
        kind
        name
      }
    }
  }
}
"""


def _type_ref(ref: dict[str, Any] | None) -> str:
    """Render a nested __Type reference as GraphQL SDL syntax."""
    if not ref:
        return "unknown"
    inner = ref.get("ofType")
    if inner:
        rendered = _type_ref(inner)
    else:
        rendered = ref.get("name") or "unknown"
    kind = ref.get("kind")
    if kind == "LIST":
        return f"[{rendered}]"
    if kind == "NON_NULL":
        return f"{rendered}!"
    return rendered


def _args(args: list[dict[str, Any]] | None) -> str:
    if not args:
        return ""
    return "(" + ", ".join(f"{a['name']}: {_type_ref(a.get('type'))}" for a in args) + ")"


def _render_type(t: dict[str, Any]) -> str | None:
    name = t.get("name")
    if not name or name.startswith("__"):
        return None
    kind = t.get("kind")

    if kind == "SCALAR":
        return f"scalar {name}"
    if kind == "UNION":
        members = [p["name"] for p in (t.get("possibleTypes") or [])]
        return f"union {name} = {' | '.join(members)}" if members else f"union {name}"
    if kind == "ENUM":
        values = [v["name"] for v in (t.get("enumValues") or [])]
        body = "\n".join(f"  {v}" for v in values)
        return f"enum {name} {{\n{body}\n}}"
    if kind in ("OBJECT", "INTERFACE"):
        keyword = "type" if kind == "OBJECT" else "interface"
        ifaces = [i["name"] for i in (t.get("interfaces") or [])]
        implements = f" implements {', '.join(ifaces)}" if ifaces else ""
        lines = []
        for f in t.get("fields") or []:
            lines.append(f"  {f['name']}{_args(f.get('args'))}: {_type_ref(f.get('type'))}")
        body = "\n".join(lines)
        return f"{keyword} {name}{implements} {{\n{body}\n}}"
    if kind == "INPUT_OBJECT":
        lines = [
            f"  {f['name']}: {_type_ref(f.get('type'))}"
            for f in (t.get("inputFields") or [])
        ]
        body = "\n".join(lines)
        return f"input {name} {{\n{body}\n}}"
    return None


class GraphQLClient(DrupalBaseClient):
    """Client for Drupal GraphQL endpoints."""

    def __init__(self, settings: Any, auth_manager: Any = None):
        super().__init__(settings, auth_manager)
        self._gql_path = settings.DRUPAL_GRAPHQL_PATH.strip("/")

    async def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        return await self.post(self._gql_path, json_body=payload)

    async def get_schema(self) -> dict[str, Any] | list[Any]:
        """Fetch the schema via GraphQL introspection, as JSON.

        Drupal's GraphQL module exposes no schema endpoint, so introspection is
        the only portable way to read it.
        """
        return await self.execute(_INTROSPECTION_QUERY)

    async def get_schema_sdl(self) -> str:
        """Fetch the schema and render it as SDL text."""
        document = await self.get_schema()
        schema = (
            document.get("data", {}).get("__schema")
            if isinstance(document, dict)
            else None
        )
        if not schema:
            raise ValueError(
                "Introspection did not return a __schema; "
                "is the GraphQL module enabled on this site?"
            )

        blocks = []
        for t in schema.get("types") or []:
            rendered = _render_type(t)
            if rendered:
                blocks.append(rendered)

        entry: list[tuple[str, str]] = []
        for role, label in (
            ("queryType", "query"),
            ("mutationType", "mutation"),
            ("subscriptionType", "subscription"),
        ):
            node = schema.get(role)
            if node and node.get("name"):
                entry.append((label, node["name"]))

        header = ""
        if entry:
            lines = "\n".join(f"  {label}: {name}" for label, name in entry)
            header = f"schema {{\n{lines}\n}}\n\n"
        return header + "\n\n".join(blocks) + "\n"
