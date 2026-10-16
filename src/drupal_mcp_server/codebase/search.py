"""Search over the local module index.

Ranking adapted from drupal-scout-mcp (MIT, © David Loor): an exact
machine-name or module-name match outranks a description match, which
outranks a code-body match (hooks, services, routes, classes).
"""

import re
from typing import Any

from .indexer import ModuleIndexer

_TERM_RE = re.compile(r"[a-z0-9]+")

_SCOPES: dict[str, tuple[str, ...]] = {
    "all": ("custom", "contrib", "core"),
    "custom": ("custom",),
    "contrib": ("contrib",),
}


def scope_types(scope: str) -> tuple[str, ...]:
    """Map a scope name to the module types it covers."""
    try:
        return _SCOPES[scope]
    except KeyError:
        raise ValueError(
            f"Unknown scope {scope!r}; expected one of {sorted(_SCOPES)}."
        ) from None


class ModuleSearcher:
    """Queries the index built by :class:`ModuleIndexer`."""

    def __init__(self, indexer: ModuleIndexer) -> None:
        self.indexer = indexer

    def all_modules(self) -> list[dict[str, Any]]:
        """Every indexed module, across all types."""
        modules: list[dict[str, Any]] = []
        for group in self.indexer.modules.values():
            modules.extend(group)
        return modules

    def search(self, query: str, limit: int = 10, scope: str = "all") -> list[dict[str, Any]]:
        """Rank modules by how well they match the query.

        Raises ``ValueError`` for an unknown scope; returns ``[]`` for an
        empty query or a non-positive limit.
        """
        types = scope_types(scope)
        terms = _TERM_RE.findall(query.lower())
        if not terms or limit < 1:
            return []
        full_query = query.lower().strip()

        scored: list[dict[str, Any]] = []
        for module_type in types:
            for module in self.indexer.modules.get(module_type, []):
                score, matches, reason = _score_module(module, terms, full_query)
                if score > 0:
                    scored.append(
                        {
                            "machine_name": module["machine_name"],
                            "name": module["name"],
                            "type": module["type"],
                            "description": module.get("description", ""),
                            "score": score,
                            "reason": reason,
                            "matches": matches,
                        }
                    )
        scored.sort(key=lambda item: (-float(item["score"]), str(item["machine_name"])))
        return scored[:limit]

    def search_modules(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Thin recommendation-oriented wrapper over :meth:`search`."""
        items: list[dict[str, Any]] = []
        for result in self.search(query, limit=limit):
            items.append(
                {
                    "machine_name": result["machine_name"],
                    "name": result["name"],
                    "type": result["type"],
                    "reason": result["reason"],
                    "description": result["description"],
                }
            )
        return items

    def unused_modules(self) -> list[dict[str, Any]]:
        """Custom/contrib modules nothing depends on and that define no hooks.

        A module counts as used when another module lists it as a
        dependency, or another module's service definition injects one of
        its ``@{module}.*`` services. Implementing hooks of its own also
        counts as usage. Core modules are never reported.
        """
        indexed = self.all_modules()
        referenced: set[str] = set()
        service_refs: set[str] = set()
        for module in indexed:
            referenced.update(str(dep) for dep in module.get("dependencies", []))
            for service in module.get("services", []):
                for argument in service.get("arguments", []):
                    text = str(argument)
                    if "." in text:
                        service_refs.add(text.split(".", 1)[0])

        unused: list[dict[str, Any]] = []
        for module in indexed:
            if module.get("type") == "core":
                continue
            machine = str(module["machine_name"])
            if machine in referenced or machine in service_refs or module.get("hooks"):
                continue
            unused.append(
                {
                    "machine_name": machine,
                    "name": module["name"],
                    "type": module["type"],
                    "description": module.get("description", ""),
                    "package": module.get("package", "Other"),
                    "path": module.get("path", ""),
                    "reason": "no hook implementations and not referenced by other modules",
                }
            )
        unused.sort(key=lambda item: str(item["machine_name"]))
        return unused

    def redundancy_check(self, query: str) -> dict[str, Any]:
        """Existing functionality in the codebase that covers a query."""
        results = self.search(query, limit=5)
        top = results[0] if results else None
        if top is None:
            recommendation = "No existing functionality found; building something new is reasonable."
        elif top["type"] == "custom":
            recommendation = (
                f"Similar functionality exists in custom module {top['machine_name']!r}; "
                "consider extending it instead of duplicating it."
            )
        else:
            recommendation = (
                f"Existing module {top['name']} ({top['machine_name']}, {top['type']}) "
                "covers this; consider enabling or extending it before building."
            )
        return {"query": query, "matches": results, "recommendation": recommendation}

    def find_hooks(self, hook_name: str) -> list[dict[str, Any]]:
        """Which modules implement a hook, with file and line.

        ``hook_name`` may be given with or without the ``hook_`` prefix
        (``form_alter`` and ``hook_form_alter`` are both accepted).
        """
        suffix = hook_name[5:] if hook_name.startswith("hook_") else hook_name
        implementations: list[dict[str, Any]] = []
        for module in self.all_modules():
            for hook in module.get("hooks", []):
                if hook.get("suffix") == suffix or hook.get("name") == suffix:
                    implementations.append(
                        {
                            "machine_name": module["machine_name"],
                            "name": module["name"],
                            "type": module["type"],
                            "hook": f"hook_{suffix}",
                            "function": hook.get("name", ""),
                            "file": hook.get("file", ""),
                            "line": hook.get("line", 0),
                        }
                    )
        return implementations


def _score_module(
    module: dict[str, Any], terms: list[str], full_query: str
) -> tuple[float, dict[str, list[str]], str]:
    """Score one module against the query terms.

    Returns ``(score, matches, reason)``. Weights mirror the upstream
    drupal-scout prioritizer (exact name > name > description > code),
    with exact whole-query matches on the machine or human name given a
    large bonus so they always rank first.
    """
    machine = str(module["machine_name"]).lower()
    name = str(module["name"]).lower()
    description = str(module.get("description", "")).lower()
    keywords = {str(word).lower() for word in module.get("keywords", [])}

    score = 0.0
    machine_exact = False
    name_exact = False
    machine_contains = False
    name_contains = False
    description_hit = False
    code_hit = False
    matches: dict[str, list[str]] = {"hooks": [], "services": [], "routes": [], "classes": []}

    if full_query == machine:
        score += 200
        machine_exact = True
    elif full_query == name:
        score += 150
        name_exact = True

    for term in terms:
        if term == machine:
            score += 100
            machine_exact = True
        elif term in machine:
            score += 20
            machine_contains = True
        if term == name:
            score += 80
            name_exact = True
        elif term in name:
            score += 15
            name_contains = True
        if term in description:
            score += 5
            description_hit = True
        if term in keywords:
            score += 3

        for service in module.get("services", []):
            service_id = str(service.get("id", ""))
            if term in service_id.lower():
                score += 2
                code_hit = True
                _collect(matches["services"], service_id)
        for route in module.get("routes", []):
            route_name = str(route.get("name", ""))
            route_path = str(route.get("path", ""))
            if term in route_name.lower() or term in route_path.lower():
                score += 1
                code_hit = True
                _collect(matches["routes"], route_name)
        for hook in module.get("hooks", []):
            hook_function = str(hook.get("name", ""))
            if term in hook_function.lower():
                score += 1
                code_hit = True
                _collect(matches["hooks"], hook_function)
        for cls in module.get("classes", []):
            class_name = str(cls.get("name", ""))
            if term in class_name.lower():
                score += 1
                code_hit = True
                _collect(matches["classes"], class_name)

    for values in matches.values():
        del values[5:]

    if machine_exact:
        reason = "machine name matches the query"
    elif name_exact:
        reason = "module name matches the query"
    elif machine_contains:
        reason = "machine name contains a query term"
    elif name_contains:
        reason = "module name contains a query term"
    elif description_hit:
        reason = "description matches the query"
    elif code_hit:
        reason = "code (hooks, services, routes, classes) matches the query"
    else:
        reason = "keyword match"
    return score, matches, reason


def _collect(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)
