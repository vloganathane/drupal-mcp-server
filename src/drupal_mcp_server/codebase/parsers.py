"""Parsers for Drupal module metadata and PHP source files.

Parsing approach adapted from drupal-scout-mcp (MIT, © David Loor). These
are deliberately regex-based heuristics rather than a full AST parser:
they extract enough structure (info.yml metadata, services, routes, hook
implementations, classes, function bodies) to power search and code
navigation over a local Drupal codebase.
"""

import re
from pathlib import Path
from typing import Any

import yaml

_PHP_EXTENSIONS = (".php", ".module", ".install", ".theme", ".inc", ".profile")

# A function definition, optionally preceded by visibility/modifier keywords.
_FUNCTION_RE = re.compile(
    r"^[ \t]*(?:(?:public|private|protected|static|abstract|final)\s+)*"
    r"function\s+([A-Za-z_]\w*)\s*\(",
    re.MULTILINE,
)
_NAMESPACE_RE = re.compile(r"namespace\s+([\w\\]+)\s*;")
_CLASS_RE = re.compile(r"class\s+(\w+)(?:\s+extends\s+([\w\\]+))?")
_TOKEN_RE = re.compile(r"[a-zA-Z0-9]{3,}")


def parse_info_file(file_path: Path) -> dict[str, Any]:
    """Parse a Drupal ``.info.yml`` file into normalized metadata.

    Dependencies accept both the short (``node``) and namespaced
    (``drupal:node``) forms, plus the config-managed dict form.
    """
    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return {
            "error": f"Could not parse {file_path.name}: {exc}",
            "name": "",
            "description": "",
            "dependencies": [],
            "keywords": [],
        }
    data: dict[str, Any] = raw if isinstance(raw, dict) else {}

    name = str(data.get("name") or "")
    description = str(data.get("description") or "")
    package = str(data.get("package") or "Other")
    return {
        "name": name,
        "description": description,
        "type": str(data.get("type") or "module"),
        "core_version_requirement": str(data.get("core_version_requirement") or ""),
        "package": package,
        "version": str(data.get("version") or ""),
        "dependencies": _parse_dependencies(data.get("dependencies")),
        "keywords": _info_keywords(name, description, package),
    }


def _parse_dependencies(raw: Any) -> list[str]:
    """Normalize dependency entries to bare module machine names."""
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        if isinstance(item, str):
            # 'drupal:node' -> 'node'; 'views:views' -> 'views'.
            names.append(item.split(":")[-1])
        elif isinstance(item, dict):
            module = item.get("module")
            if isinstance(module, str):
                names.append(module)
    return names


def _info_keywords(name: str, description: str, package: str) -> list[str]:
    """Tokenize name, description and package into search keywords."""
    keywords: list[str] = []
    for text in (name, description, package):
        for word in _TOKEN_RE.findall(text):
            lowered = word.lower()
            if lowered not in keywords:
                keywords.append(lowered)
    return keywords


def parse_services_file(file_path: Path) -> dict[str, Any]:
    """Parse a Drupal ``.services.yml`` file into a service list."""
    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return {"error": f"Could not parse {file_path.name}: {exc}", "services": []}
    data: dict[str, Any] = raw if isinstance(raw, dict) else {}

    services: list[dict[str, Any]] = []
    definitions = data.get("services")
    if isinstance(definitions, dict):
        for service_id, definition in definitions.items():
            if not isinstance(definition, dict):
                continue
            services.append(
                {
                    "id": str(service_id),
                    "class": str(definition.get("class") or ""),
                    "arguments": _service_arguments(definition.get("arguments")),
                    "tags": _service_tags(definition.get("tags")),
                    "keywords": _service_keywords(str(service_id), definition),
                }
            )
    return {"services": services}


def _service_arguments(raw: Any) -> list[str]:
    """Keep only ``@service`` arguments, with the ``@``/``?`` markers stripped."""
    if not isinstance(raw, list):
        return []
    arguments: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.startswith("@"):
            arguments.append(item.lstrip("@?"))
    return arguments


def _service_tags(raw: Any) -> list[str]:
    tags: list[str] = []
    if isinstance(raw, list):
        for tag in raw:
            if isinstance(tag, str):
                tags.append(tag)
            elif isinstance(tag, dict) and isinstance(tag.get("name"), str):
                tags.append(str(tag["name"]))
    return tags


def _service_keywords(service_id: str, definition: dict[str, Any]) -> list[str]:
    keywords: list[str] = []
    for part in re.split(r"[._]", service_id):
        keywords.append(part.lower())
    class_name = str(definition.get("class") or "")
    if class_name:
        keywords.append(class_name.split("\\")[-1].lower())
    keywords.extend(_service_tags(definition.get("tags")))
    return _dedupe(keywords)


def parse_routing_file(file_path: Path) -> dict[str, Any]:
    """Parse a Drupal ``.routing.yml`` file into a route list."""
    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return {"error": f"Could not parse {file_path.name}: {exc}", "routes": []}
    data: dict[str, Any] = raw if isinstance(raw, dict) else {}

    routes: list[dict[str, Any]] = []
    for route_name, definition in data.items():
        if not isinstance(definition, dict):
            continue
        defaults = definition.get("defaults")
        defaults = defaults if isinstance(defaults, dict) else {}
        controller = ""
        for key in ("_controller", "_form", "_entity_form", "_entity_list"):
            if defaults.get(key):
                controller = str(defaults[key])
                break
        methods = definition.get("methods")
        path = str(definition.get("path") or "")
        routes.append(
            {
                "name": str(route_name),
                "path": path,
                "controller": controller,
                "methods": [str(m) for m in methods] if isinstance(methods, list) else [],
                "keywords": _route_keywords(str(route_name), path, controller),
            }
        )
    return {"routes": routes}


def _route_keywords(route_name: str, path: str, controller: str) -> list[str]:
    keywords = re.split(r"[._]", route_name)
    keywords.extend(segment for segment in path.split("/") if segment and not segment.startswith("{"))
    if controller:
        keywords.append(controller.split("::")[0].split("\\")[-1])
    return _dedupe([k.lower() for k in keywords if len(k) > 2])


def parse_php_file(file_path: Path, module_name: str | None = None) -> dict[str, Any]:
    """Extract namespace, classes, functions and hooks from a PHP file.

    Hooks are only identified when ``module_name`` is given: any function
    named ``{module_name}_*`` counts as a hook implementation, which is how
    Drupal names them (``mymod_form_alter`` for ``hook_form_alter()``).
    """
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return {"error": f"Could not read {file_path.name}: {exc}", "hooks": [], "classes": []}

    namespace_match = _NAMESPACE_RE.search(content)
    functions = _extract_functions(content)
    hooks: list[dict[str, Any]] = []
    if module_name:
        prefix = f"{module_name}_"
        for function in functions:
            name = str(function["name"])
            if name.startswith(prefix):
                hooks.append({"name": name, "suffix": name[len(prefix):], "line": function["line"]})
    return {
        "namespace": namespace_match.group(1) if namespace_match else "",
        "classes": _extract_classes(content),
        "functions": functions,
        "hooks": hooks,
    }


def _extract_functions(content: str) -> list[dict[str, Any]]:
    functions: list[dict[str, Any]] = []
    for match in _FUNCTION_RE.finditer(content):
        functions.append(
            {
                "name": match.group(1),
                "line": content.count("\n", 0, match.start()) + 1,
            }
        )
    return functions


def _extract_classes(content: str) -> list[dict[str, Any]]:
    classes: list[dict[str, Any]] = []
    for match in _CLASS_RE.finditer(content):
        classes.append({"name": match.group(1), "extends": match.group(2)})
    return classes


def extract_php_function(content: str, function_name: str) -> tuple[int, str] | None:
    """Extract one PHP function (or method) with its docblock.

    Returns ``(line, code)`` where ``line`` is the 1-based line of the
    ``function`` keyword and ``code`` includes any docblock directly above
    it, or ``None`` when the function is not present.
    """
    pattern = re.compile(
        rf"^[ \t]*(?:(?:public|private|protected|static|abstract|final)\s+)*"
        rf"function\s+{re.escape(function_name)}\s*\(",
        re.MULTILINE,
    )
    match = pattern.search(content)
    if match is None:
        return None

    open_brace = content.find("{", match.end())
    if open_brace == -1:
        # Abstract method or interface declaration: no body to extract.
        return None
    end = _matching_brace_end(content, open_brace)
    docblock_start = _docblock_start(content, match.start())
    code = content[docblock_start : end + 1].strip("\n")
    line = content.count("\n", 0, match.start()) + 1
    return line, code


def _matching_brace_end(content: str, open_brace: int) -> int:
    """Index of the ``}`` closing the brace at ``open_brace`` (naive scan)."""
    depth = 0
    for index in range(open_brace, len(content)):
        char = content[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return len(content) - 1


def _docblock_start(content: str, definition_start: int, max_lines: int = 30) -> int:
    """Start offset of the docblock directly above a function definition."""
    lines = content[:definition_start].splitlines(keepends=True)
    cursor = definition_start
    for line in reversed(lines[-max_lines:]):
        cursor -= len(line)
        stripped = line.strip()
        if stripped.startswith("/**"):
            return cursor
        if stripped and not stripped.startswith("*"):
            break
        if not stripped:
            break
    return definition_start


def _dedupe(words: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for word in words:
        if word and word not in seen:
            seen.add(word)
            result.append(word)
    return result
