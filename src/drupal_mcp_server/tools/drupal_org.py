"""Drupal.org integration tools.

drupal.org decommissioned the ``/api-d7/project/...`` endpoints this package
originally targeted, so every tool here used to fail with an HTML 404 page.
Only a few endpoints are still live; each tool uses whichever one actually
answers and reports a precise error instead of dumping markup.
"""

import re
from typing import Any
from xml.etree import ElementTree

import httpx
from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict

DRUPAL_ORG = "https://www.drupal.org"
DRUPAL_ORG_API = f"{DRUPAL_ORG}/api-d7"
RELEASE_HISTORY_API = "https://updates.drupal.org/release-history"

_TIMEOUT = 30.0
_SNIPPET = 300


async def _fetch(url: str, accept: str = "application/json") -> httpx.Response:
    """GET a drupal.org URL, following redirects, with readable errors."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url, headers={"Accept": accept})
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc}") from exc
    if response.status_code >= 400:
        raise RuntimeError(
            f"drupal.org returned HTTP {response.status_code} for {url}. "
            "This endpoint may have been retired."
        )
    return response


def _strip_html(html: str, limit: int = 400) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _project_summary(node: dict[str, Any]) -> dict[str, Any]:
    """Trim a raw drupal.org node down to the fields worth returning."""
    out: dict[str, Any] = {
        key: node[key]
        for key in ("nid", "title", "type", "status", "created", "changed")
        if key in node
    }
    for key in (
        "field_project_machine_name",
        "field_project_type",
        "field_project_homepage",
        "field_project_license",
        "field_project_has_releases",
        "field_project_ecosystem",
        "field_security_advisory_coverage",
        "field_release_version_format",
        "field_replaced_by",
        "field_project_documentation",
        "field_project_changelog",
    ):
        value = node.get(key)
        if value not in (None, "", [], {}):
            out[key] = value
    body = node.get("body")
    if isinstance(body, dict) and body.get("value"):
        out["summary"] = _strip_html(str(body["value"]))
    return out


async def _resolve_project(machine_name: str) -> dict[str, Any]:
    """Look up a project node by machine name.

    The machine-name lookup endpoint is gone, so resolve the project page to a
    node ID and read that node's JSON, which is still served.
    """
    name = machine_name.strip().strip("/")
    if not name:
        raise RuntimeError("A project machine name is required.")

    page = await _fetch(f"{DRUPAL_ORG}/project/{name}", accept="text/html")
    match = re.search(r"drupal\.org/node/(\d+)", page.text)
    if not match:
        raise RuntimeError(
            f"No Drupal.org project named {name!r} was found. "
            "Check the machine name on https://www.drupal.org/project."
        )

    node = await _fetch(f"{DRUPAL_ORG_API}/node/{match.group(1)}.json")
    return node.json()  # type: ignore[no-any-return]


def _parse_release_history(
    xml_text: str, machine_name: str, core: str
) -> dict[str, Any]:
    """Turn updates.drupal.org's XML (success or <error>) into a dict."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise RuntimeError(
            f"Release history for {machine_name!r} was not valid XML: {exc}"
        ) from exc

    if root.tag == "error":
        raise RuntimeError(
            f"drupal.org has no release history for {machine_name!r} against "
            f"core {core!r}: {root.text or 'unknown reason'}"
        )

    releases = []
    for release in root.iter("release"):
        releases.append({
            tag: (release.findtext(tag) or None)
            for tag in ("version", "created", "core", "status", "supported", "security", "name")
            if release.find(tag) is not None
        })
    return {"project": machine_name, "core": core, "releases": releases}


async def _release_history(machine_name: str, core: str) -> dict[str, Any]:
    """Read updates.drupal.org; it returns XML, and often an <error> document."""
    url = f"{RELEASE_HISTORY_API}/{machine_name}/{core}"
    response = await _fetch(url, accept="application/xml")
    return _parse_release_history(response.text, machine_name, core)


def _parse_search_results(html: str) -> list[dict[str, str]]:
    """Extract project hits from the apachesolr results list.

    Nav links also point at /project/modules and /project/themes, so scoping to
    the results list is what keeps them out of the answer.
    """
    marker = html.find("apachesolr_search-results")
    if marker == -1:
        raise RuntimeError(
            "Drupal.org returned a search page without results; "
            "its markup may have changed."
        )
    region = html[marker:]
    results: list[dict[str, str]] = []
    for item in re.findall(r'<li class="search-result">(.*?)</li>', region, re.S):
        name = re.search(r"drupal\.org/project/([A-Za-z0-9_]+)", item)
        if not name:
            continue
        info = re.search(r"<p[^>]*>(.*?)</p>", item, re.S)
        label = _strip_html(info.group(1)) if info else ""
        results.append({
            "machine_name": name.group(1),
            "type": "theme" if "theme" in label.lower() else "module",
            "url": f"{DRUPAL_ORG}/project/{name.group(1)}",
            "snippet": _strip_html(re.sub(r"<h3.*?</h3>", "", item, flags=re.S), 200),
        })
    return results


async def _search(query: str) -> list[dict[str, str]]:
    """Search drupal.org and return project machine names.

    There is no JSON search API, so parse the project links out of the page.
    """
    response = await _fetch(f"{DRUPAL_ORG}/search/site/{query}", accept="text/html")
    return _parse_search_results(response.text)


def _parse_usage(html: str, machine_name: str, period: str) -> dict[str, Any]:
    """Extract the usage table from a project usage page."""
    table = re.search(r"<table.*?</table>", html, re.S)
    if not table:
        raise RuntimeError(f"Drupal.org publishes no usage statistics for {machine_name!r}.")

    headers = [h.strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", table.group(0), re.S)]
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(0), re.S)
    cells = None
    for row in rows:
        values = [v.strip() for v in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if values:
            cells = values
            break
    if not cells:
        raise RuntimeError(f"The usage table for {machine_name!r} had no data rows.")

    # Branch columns vary per project, so lengths may differ. "Total" is
    # reported on its own and must not appear as if it were a release branch.
    breakdown = {
        key: value
        for key, value in zip(headers[1:], cells[1:], strict=False)
        if key.lower() != "total"
    }
    return {
        "machine_name": machine_name,
        "period": period,
        "week_starting": cells[0],
        "total": cells[-1],
        "by_branch": breakdown,
    }


async def _usage(machine_name: str, period: str) -> dict[str, Any]:
    """Read the usage table from the project's usage page."""
    response = await _fetch(f"{DRUPAL_ORG}/project/usage/{machine_name}", accept="text/html")
    return _parse_usage(response.text, machine_name, period)


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    @mcp.tool()
    async def module_search(query: str, page: int = 0, page_size: int = 20) -> dict[str, Any]:
        """Search Drupal.org for modules by name or description."""
        try:
            results = [r for r in await _search(query) if r["type"] == "module"]
            start = max(page, 0) * page_size
            return _ensure_dict({
                "query": query,
                "count": len(results),
                "results": results[start:start + page_size],
            })
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def module_get(project_id: str) -> dict[str, Any]:
        """Get module details from Drupal.org by machine name."""
        try:
            return _ensure_dict(_project_summary(await _resolve_project(project_id)))
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def module_versions(project_id: str, core_version: str = "10.x") -> dict[str, Any]:
        """Get all available releases for a module."""
        try:
            return _ensure_dict(await _release_history(project_id, core_version))
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def module_dependencies(project_id: str, version: str | None = None) -> dict[str, Any]:
        """Get module dependencies.

        drupal.org has no endpoint that exposes per-release dependencies, so
        this reports that limitation rather than inventing an answer.
        """
        return _ensure_dict({
            "error": (
                "drupal.org no longer publishes per-release dependency data. "
                f"Use `composer show -a drupal/{project_id}` locally instead."
            )
        })

    @mcp.tool()
    async def theme_search(query: str, page: int = 0, page_size: int = 20) -> dict[str, Any]:
        """Search Drupal.org for themes by name or description."""
        try:
            results = [r for r in await _search(query) if r["type"] == "theme"]
            start = max(page, 0) * page_size
            return _ensure_dict({
                "query": query,
                "count": len(results),
                "results": results[start:start + page_size],
            })
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def theme_get(project_id: str) -> dict[str, Any]:
        """Get theme details from Drupal.org by machine name."""
        try:
            return _ensure_dict(_project_summary(await _resolve_project(project_id)))
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def release_history(project_id: str, core_version: str = "10.x") -> dict[str, Any]:
        """Get release history for a project."""
        try:
            return _ensure_dict(await _release_history(project_id, core_version))
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def project_usage(project_id: str, period: str = "month") -> dict[str, Any]:
        """Get download/usage statistics for a project."""
        try:
            return _ensure_dict(await _usage(project_id, period))
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def module_compatibility(project_id: str, core_version: str = "10.x") -> dict[str, Any]:
        """Check whether a project has releases for a given core version."""
        try:
            history = await _release_history(project_id, core_version)
        except Exception as e:
            return {"error": str(e)}
        releases = history.get("releases") or []
        return _ensure_dict({
            "project": project_id,
            "core_version": core_version,
            "compatible": bool(releases),
            "release_count": len(releases),
        })
