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
# updates.drupal.org froze at Drupal 8: it answers <error> for every 9.x+
# project. Composer metadata is the live source for those, and the only one
# that carries dependencies and core constraints.
COMPOSER_API = "https://packages.drupal.org/files/packages/8/p2"

_TIMEOUT = 30.0
_SNIPPET = 300
# Composer's `minified: composer/2.0` sentinel: a property is removed.
_UNSET = "__unset"


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


async def _fetch_optional(url: str, accept: str = "application/json") -> httpx.Response | None:
    """Like _fetch, but a 404 means "no such project" rather than an error."""
    try:
        return await _fetch(url, accept)
    except RuntimeError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise


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


class NoCompatibleReleases(RuntimeError):
    """The project exists but publishes nothing for the requested core.

    A distinct type so callers can answer "not compatible" instead of
    reporting a failure.
    """


def _expand_minified(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Undo Composer's ``minified: composer/2.0`` package delta encoding.

    Each entry after the first carries only what changed: an omitted key keeps
    the previous release's value, and ``__unset`` removes it. 15 of pathauto's
    24 entries omit ``require`` this way, so reading entries directly would
    quietly drop most dependency lists.
    """
    expanded: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for entry in entries:
        merged = dict(current)
        for key, value in entry.items():
            if value == _UNSET:
                merged.pop(key, None)
            else:
                merged[key] = value
        current = merged
        expanded.append(dict(current))
    return expanded


def _core_majors(constraint: str | None) -> list[int]:
    """Pull the Drupal major versions out of a ``drupal/core`` constraint.

    ``^10.2 || ^11`` -> [10, 11]. A wildcard has no numbers, which reads as
    "no stated limit" rather than "compatible with nothing".
    """
    if not isinstance(constraint, str) or not constraint.strip():
        return []
    if constraint.strip() == "*":
        return []
    return sorted({int(major) for major in re.findall(r"(?<![\w.])(\d+)", constraint)})


def _parse_composer_packages(
    entries: list[dict[str, Any]], machine_name: str, core: str
) -> dict[str, Any]:
    """Turn packages.drupal.org metadata into the release-history shape."""
    target = _core_majors(core) if core not in ("", "all", "*") else []
    releases: list[dict[str, Any]] = []
    compatible_count = 0

    for entry in _expand_minified(entries):
        extra = entry.get("extra") or {}
        drupal_extra = (extra.get("drupal") or {}) if isinstance(extra, dict) else {}
        requirement = entry.get("require") or {}
        constraint = requirement.get("drupal/core")
        majors = _core_majors(constraint)

        if target and majors and not (set(target) & set(majors)):
            # Publishes releases, just not for the requested core version.
            continue
        if not target or not majors or (set(target) & set(majors)):
            compatible_count += 1

        security = drupal_extra.get("security-coverage") or {}
        releases.append({
            "version": drupal_extra.get("version") or entry.get("version"),
            "composer_version": entry.get("version"),
            "created": drupal_extra.get("datestamp"),
            "core": constraint,
            "type": entry.get("type"),
            "security": security.get("status"),
            "dependencies": {
                name: spec
                for name, spec in requirement.items()
                if name != "drupal/core"
            },
            "zip": (entry.get("dist") or {}).get("url"),
        })

    if not releases:
        raise NoCompatibleReleases(
            f"drupal.org has no releases for {machine_name!r} compatible with "
            f"core {core!r}. The project publishes {len(entries)} releases."
        )

    return {
        "project": machine_name,
        "core": core,
        "source": "packages.drupal.org",
        "compatible_release_count": compatible_count,
        "releases": releases,
    }


async def _composer_entries(machine_name: str) -> list[dict[str, Any]]:
    """Fetch and de-minify a project's Composer metadata, newest first."""
    response = await _fetch_optional(
        f"{COMPOSER_API}/drupal/{machine_name}.json", accept="application/json"
    )
    if response is None:
        raise RuntimeError(
            f"drupal.org has no Composer package for drupal/{machine_name}. "
            "Check the machine name on https://www.drupal.org/project."
        )
    packages = response.json().get("packages") or {}
    entries = packages.get(f"drupal/{machine_name}")
    if not entries:
        raise RuntimeError(
            f"Composer metadata for drupal/{machine_name} lists no releases. "
            "Check the machine name on https://www.drupal.org/project."
        )
    return _expand_minified(entries)


async def _composer_releases(machine_name: str, core: str) -> dict[str, Any]:
    """Read Composer metadata from packages.drupal.org."""
    entries = await _composer_entries(machine_name)
    return _parse_composer_packages(entries, machine_name, core)


async def _releases(machine_name: str, core: str) -> dict[str, Any]:
    """Best available release data for a project.

    updates.drupal.org still answers 6.x/7.x/8.x correctly but returns an
    ``<error>`` document for everything since, so it is only trusted when it
    actually lists releases; otherwise fall through to Composer metadata.
    """
    xml_error: str | None = None
    try:
        history = await _release_history(machine_name, core)
    except RuntimeError as exc:
        xml_error = str(exc)
    else:
        if history.get("releases"):
            history["source"] = "updates.drupal.org"
            return history

    try:
        return await _composer_releases(machine_name, core)
    except NoCompatibleReleases:
        # The project exists; it simply publishes nothing for this core.
        raise
    except RuntimeError as exc:
        if xml_error:
            raise RuntimeError(xml_error) from exc
        raise


def _drupal_version(entry: dict[str, Any]) -> str | None:
    """The Drupal-style version (``8.x-1.15``) rather than Composer's."""
    extra = entry.get("extra") or {}
    drupal = (extra.get("drupal") or {}) if isinstance(extra, dict) else {}
    return drupal.get("version") or entry.get("version")


def _find_release(entries: list[dict[str, Any]], version: str) -> dict[str, Any]:
    """Locate one release by any of the identifiers people actually use."""
    wanted = version.strip()
    keys = (
        lambda e: e.get("version"),
        _drupal_version,
        lambda e: (e.get("dist") or {}).get("reference"),
    )
    for key in keys:
        for entry in entries:
            if key(entry) == wanted:
                return entry
    known = [_drupal_version(entry) or entry.get("version") for entry in entries]
    preview = ", ".join(str(v) for v in known[:12])
    raise RuntimeError(
        f"No release {wanted!r} for this project. Known releases: {preview}"
        + (" ..." if len(known) > 12 else "")
    )



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
            return _ensure_dict(await _releases(project_id, core_version))
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def module_dependencies(project_id: str, version: str | None = None) -> dict[str, Any]:
        """Get the packages a module release requires.

        Read from Composer metadata on packages.drupal.org, which is where
        Drupal publishes dependency data today. Omit ``version`` for the
        newest release.
        """
        try:
            entries = await _composer_entries(project_id)
            release = entries[0] if not version else _find_release(entries, version)
        except Exception as e:
            return {"error": str(e)}

        requirement = release.get("require") or {}
        return _ensure_dict({
            "project": project_id,
            "version": _drupal_version(release),
            "composer_version": release.get("version"),
            "drupal_core": requirement.get("drupal/core"),
            "dependencies": {
                name: spec
                for name, spec in requirement.items()
                if name != "drupal/core"
            },
            "source": "packages.drupal.org",
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
            return _ensure_dict(await _releases(project_id, core_version))
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
            history = await _releases(project_id, core_version)
        except NoCompatibleReleases as e:
            return _ensure_dict({
                "project": project_id,
                "core_version": core_version,
                "compatible": False,
                "release_count": 0,
                "detail": str(e),
            })
        except Exception as e:
            return {"error": str(e)}

        releases = history.get("releases") or []
        matched = history.get("compatible_release_count", len(releases))
        sample = [r.get("core") for r in releases[:5] if r.get("core")]
        return _ensure_dict({
            "project": project_id,
            "core_version": core_version,
            "compatible": bool(releases),
            "release_count": len(releases),
            "compatible_release_count": matched,
            "source": history.get("source"),
            "core_constraints": sample,
        })
