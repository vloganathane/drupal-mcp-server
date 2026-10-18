#!/usr/bin/env python3
"""Generate docs/tools/all.md — the complete tool catalog page.

The page is generated, never hand-edited, so it cannot drift from the code:

    python scripts/generate_tool_docs.py           # regenerate the page
    python scripts/generate_tool_docs.py --check   # CI: fail on drift

Data sources, merged by tool name:

- src/drupal_mcp_server/tools/*.py   tool names, docstrings, signatures (AST)
- docs/tools/_tool_overrides.yaml    hand-maintained use cases and status
                                     notes — the only file to edit by hand
- tests/live/sweep-results-ddev.json live verdicts from the DDEV sweep
- tests/live/sweep-results-lando.json  live verdicts from the Lando sweep
- tests/unit/*.py                    which tools have unit-test coverage

The script parses files only; it never imports the package, so it runs in the
docs CI job without the server's dependencies installed.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "src" / "drupal_mcp_server" / "tools"
DOCS_TOOLS = ROOT / "docs" / "tools"
OVERRIDES = DOCS_TOOLS / "_tool_overrides.yaml"
OUTPUT = DOCS_TOOLS / "all.md"
UNIT_TESTS = ROOT / "tests" / "unit"

# Live results: the freshest full sweep per environment. A missing file simply
# omits that environment's column — the page never invents a verdict.
SWEEP_SOURCES = {
    "ddev": [DOCS_TOOLS.parents[1] / "tests" / "live" / "sweep-results-ddev.json"],
    "lando": [DOCS_TOOLS.parents[1] / "tests" / "live" / "sweep-results-lando.json"],
}
# The historical single-env sweep is a fallback for ddev only.
SWEEP_SOURCES["ddev"].append(ROOT / "tests" / "live" / "sweep-results.json")

# Sections in the order they appear on the page; modules not listed here fall
# into "Other" at the end, in filename order.
CATEGORIES: dict[str, list[str]] = {
    "Content & Entities": [
        "content", "users", "taxonomy", "comments", "revisions",
        "paragraphs", "media_enhanced",
    ],
    "Configuration & Structure": [
        "config", "fields", "menus", "views", "layout_builder",
        "pathauto", "redirects", "metatag",
    ],
    "Search, Feeds & Multilingual": ["search_api", "feeds", "multilingual"],
    "Workflow, Forms & Contact": ["moderation", "webform", "contact", "commerce"],
    "Site Status, Database & DevOps": [
        "status", "database", "devops", "scheduler", "performance",
    ],
    "Migration & Analysis": ["migration", "analysis", "ai"],
    "Codebase, Module & Theme Development": [
        "codebase", "module_dev", "theme_dev", "theme_analysis", "code_audit",
    ],
    "Security": ["security_audit"],
    "Headless & Integrations": ["headless", "drupal_org"],
    "Testing, Accessibility & Export": [
        "testing", "accessibility", "exports",
    ],
}

TITLE_OVERRIDES = {
    "drupal_org": "Drupal.org",
    "search_api": "Search API",
    "ai": "AI",
    "db": "Database",
}

# Verdict -> short badge. DEAD is a product bug and should never appear; if it
# does, it gets the loudest badge on the page.
VERDICT_BADGES = {
    "OK": "✅",
    "REJECTED": "⚠️",
    "BLOCKED": "🧩",
    "UPSTREAM": "🧩",
    "SKIPPED": "⏭️",
    "DEAD": "💀",
}

# Sensible placeholder values for the example column, keyed by parameter name,
# falling back to the annotation's type.
PARAM_HINTS = {
    "nid": "123", "id": "1", "uuid": "f...", "vid": "1", "fid": "1",
    "bundle": "article", "entity_type": "node", "langcode": "en",
    "path": "/about", "query": "keyword", "command": "status",
    "module": "mymodule", "theme_name": "olivero", "vocabulary": "tags",
    "webform_id": "contact", "view_name": "content", "roles": ["editor"],
    "fields": {"title": "Hello"}, "filters": {"status": "1"},
    "sorts": ["-created"], "format": "csv", "severity_filter": "warning",
}
TYPE_DEFAULTS = {"dict": "{}", "list": "[]", "bool": "true", "int": "1",
                 "float": "1.0", "str": '"value"'}


@dataclass
class Tool:
    name: str
    module: str
    summary: str
    example: str
    use_case: str = ""
    status_note: str = ""
    docs_link: str | None = None
    unit_tested: bool = False
    live: dict[str, str] = field(default_factory=dict)  # env -> verdict


def _title(module: str) -> str:
    return TITLE_OVERRIDES.get(module, module.replace("_", " ").title())


def _escape_cell(text: str) -> str:
    """Keep a value safe inside a markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _annotation(node: ast.expr | None) -> str:
    return ast.unparse(node) if node else "Any"


def _example_value(name: str, ann: str) -> str:
    if name in PARAM_HINTS:
        return json.dumps(PARAM_HINTS[name])
    base = ann.replace(" | None", "").replace("None", "").strip(" |")
    for key, value in TYPE_DEFAULTS.items():
        if key in base:
            return value
    return '"value"'


def _summary_from_docstring(doc: str | None) -> str:
    """First paragraph of a docstring, whitespace-normalised."""
    if not doc:
        return ""
    paragraph: list[str] = []
    for line in doc.strip().splitlines():
        if not line.strip():
            break
        paragraph.append(line.strip())
    return " ".join(paragraph)


def parse_tools() -> list[Tool]:
    tools: list[Tool] = []
    for path in sorted(TOOLS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module = path.stem
        tree = ast.parse(path.read_text(encoding="utf-8"))

        for node in _iter_functions(tree):
            if not _is_mcp_tool(node):
                continue
            args = node.args.args
            defaults = node.args.defaults
            required = args[: len(args) - len(defaults)]
            parts = [
                f'"{arg.arg}": {_example_value(arg.arg, _annotation(arg.annotation))}'
                for arg in required
            ]
            example = "{" + ", ".join(parts) + "}" if parts else "{}"
            tools.append(
                Tool(
                    name=node.name,
                    module=module,
                    summary=_summary_from_docstring(ast.get_docstring(node)),
                    example=example,
                )
            )
    return tools


def _iter_functions(tree: ast.AST):
    for child in ast.walk(tree):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield child


def _is_mcp_tool(node: ast.AST) -> bool:
    for dec in node.decorator_list:  # type: ignore[attr-defined]
        target = dec.func if isinstance(dec, ast.Call) else dec
        if getattr(target, "attr", None) == "tool":
            return True
    return False


def load_overrides() -> dict[str, dict[str, str]]:
    if not OVERRIDES.exists():
        return {}
    data = yaml.safe_load(OVERRIDES.read_text(encoding="utf-8")) or {}
    return data.get("tools") or {}


def load_sweeps(env: str) -> dict[str, str]:
    for candidate in SWEEP_SOURCES[env]:
        if candidate.exists():
            rows = json.loads(candidate.read_text(encoding="utf-8"))
            return {row["tool"]: row["verdict"] for row in rows}
    return {}


def load_unit_coverage(names: set[str]) -> set[str]:
    covered: set[str] = set()
    for path in sorted(UNIT_TESTS.glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        for name in names:
            if re.search(rf"\b{re.escape(name)}\b", text):
                covered.add(name)
    return covered


def load_doc_links() -> dict[str, str]:
    """Map tool name -> markdown file with a dedicated heading for it."""
    links: dict[str, str] = {}
    for path in sorted(DOCS_TOOLS.glob("*.md")):
        if path.name == "all.md":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^#{2,3} ([a-z][a-z0-9_]+)\s*$", line)
            if match:
                links[match.group(1)] = path.name
    return links


def status_cell(tool: Tool) -> str:
    badges: list[str] = []
    for env, verdict in tool.live.items():
        badge = VERDICT_BADGES.get(verdict, "❔")
        badges.append(f"{badge} {env}")
    badges.append("🧪 unit" if tool.unit_tested else "❔ not live-verified")
    text = " · ".join(badges)
    if tool.status_note:
        text += f" — _{escape_md(tool.status_note)}_"
    return text


def escape_md(text: str) -> str:
    return text.replace("_", "\\_").replace("*", "\\*")


def render(tools: list[Tool]) -> str:
    overrides = load_overrides()
    sweeps = {env: load_sweeps(env) for env in SWEEP_SOURCES}
    unit = load_unit_coverage({t.name for t in tools})
    doc_links = load_doc_links()

    for tool in tools:
        over = overrides.get(tool.name, {})
        tool.use_case = over.get("use_case", "")
        tool.status_note = over.get("status_note", "")
        tool.docs_link = doc_links.get(tool.name)
        tool.unit_tested = tool.name in unit
        for env, verdicts in sweeps.items():
            if tool.name in verdicts:
                tool.live[env] = verdicts[tool.name]

    by_module: dict[str, list[Tool]] = {}
    for tool in tools:
        by_module.setdefault(tool.module, []).append(tool)

    out: list[str] = []
    out.append("<!-- GENERATED FILE — do not edit by hand.")
    out.append("Regenerate with: python scripts/generate_tool_docs.py")
    out.append("To change a use case or status note, edit "
               "docs/tools/_tool_overrides.yaml. -->")
    out.append("")
    out.append("# All Tools")
    out.append("")
    out.append(
        f"Every tool the server registers ({len(tools)} across "
        f"{len(by_module)} modules), generated from the source code and the "
        "live-test harness. Tool names are the runtime names an MCP client "
        "sees."
    )
    out.append("")
    out.append("## How to read the status column")
    out.append("")
    out.append("| Badge | Meaning |")
    out.append("|-------|---------|")
    out.append("| ✅ ddev / ✅ lando | Live sweep on that environment returned "
               "usable data |")
    out.append("| ⚠️ ddev / ⚠️ lando | Live sweep: the tool answered, but the "
               "answer was a refusal or lookup miss (often fixture- or "
               "site-dependent, not necessarily a bug) |")
    out.append("| 🧩 | Blocked on that environment: needs a module, binary, or "
               "subsystem the test site does not have |")
    out.append("| ⏭️ | Skipped by the sweep on purpose: it starts/stops the "
               "environment the sweep runs against |")
    out.append("| 💀 | Dead — a product bug (currently none) |")
    out.append("| 🧪 unit | Has offline unit-test coverage |")
    out.append("| ❔ not live-verified | No live-sweep verdict recorded yet |")
    out.append("")
    out.append(
        "The live sweeps run against a provisioned local site "
        "(`tests/live/`); see that directory's README for what each verdict "
        "really measures. `REJECTED` counts are largely harness fixture "
        "artefacts — a tool asked for an id this site does not have — so read "
        "them as \"not disproven\" rather than \"broken\"."
    )
    out.append("")
    out.append("## Modules")
    out.append("")
    out.append("| Category | Module | Tools | Detailed docs |")
    out.append("|----------|--------|------:|---------------|")

    seen: set[str] = set()
    sections: list[tuple[str, str]] = []
    for category, modules in CATEGORIES.items():
        for module in modules:
            if module in by_module:
                sections.append((category, module))
                seen.add(module)
    for module in sorted(by_module):
        if module not in seen:
            sections.append(("Other", module))

    for category, module in sections:
        mod_tools = by_module[module]
        detailed = sum(1 for t in mod_tools if t.docs_link)
        docs_cell = f"{detailed} of {len(mod_tools)}" if detailed else "—"
        out.append(
            f"| {category} | [{module}](#{module}) | {len(mod_tools)} "
            f"| {docs_cell} |"
        )
    out.append("")

    for category, module in sections:
        mod_tools = by_module[module]
        out.append(f"## {module}")
        out.append("")
        out.append(f"{_title(module)} — {len(mod_tools)} tools.")
        out.append("")
        out.append("| Tool | Description & use case | Example | Status |")
        out.append("|------|------------------------|---------|--------|")
        for tool in mod_tools:
            name = tool.name
            if tool.docs_link:
                name = f"[`{name}`]({tool.docs_link}#{tool.name})"
            else:
                name = f"`{name}`"
            description = _escape_cell(tool.summary)
            if tool.use_case:
                description += f"<br>_{escape_md(_escape_cell(tool.use_case))}_"
            example = f"`{_escape_cell(tool.example)}`"
            out.append(
                f"| {name} | {description} | {example} | {status_cell(tool)} |"
            )
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="verify docs/tools/all.md matches the code; exit 1 on drift",
    )
    args = parser.parse_args()

    tools = parse_tools()
    if not tools:
        print("no tools found — is the working directory the repo root?",
              file=sys.stderr)
        return 2
    rendered = render(tools)

    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            print(
                f"{OUTPUT.relative_to(ROOT)} is out of date with the code.\n"
                "Regenerate it with: python scripts/generate_tool_docs.py",
                file=sys.stderr,
            )
            return 1
        print(f"{OUTPUT.relative_to(ROOT)} is up to date "
              f"({len(tools)} tools).")
        return 0

    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({len(tools)} tools)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
