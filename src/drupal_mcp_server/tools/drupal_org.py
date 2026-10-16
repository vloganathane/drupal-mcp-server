"""Drupal.org integration tools.

drupal.org decommissioned the ``/api-d7/project/...`` endpoints this package
originally targeted, so every tool here used to fail with an HTML 404 page.
Only a few endpoints are still live; each tool uses whichever one actually
answers and reports a precise error instead of dumping markup.
"""

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree

import httpx
from fastmcp import FastMCP

from ..config import get_settings
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


# --- Issue-queue search, popularity, and category helpers -------------------
# Keyword scoring adapted from drupal-scout-mcp (MIT, David Loor): drupal.org
# retired its fulltext filter (node.json answers 412 for search_api_fulltext),
# so relevance is computed client-side over recent issues instead.

_ISSUE_STOP_WORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of",
        "with", "by", "from", "is", "are", "was", "were", "been", "be", "have",
        "has", "had", "do", "does", "did", "will", "would", "should", "could",
        "may", "might", "can", "i", "my", "me", "getting", "get", "got",
        "not", "this", "that", "when", "how", "why", "just", "also", "than",
        "then", "them", "they", "you", "your", "we", "our", "into", "after",
        "before", "using", "used", "use", "one", "two",
    }
)

_ISSUE_STATUS = {
    "1": "Active",
    "2": "Needs work",
    "3": "Reviewed & tested by community",
    "4": "Reviewed & tested by maintainer",
    "5": "Fixed",
    "6": "Closed (won't fix)",
    "7": "Postponed",
    "8": "Duplicate",
}

_CATEGORY_CACHE: list[dict[str, str]] | None = None


def _issue_keywords(text: str) -> list[str]:
    """Tokenize a problem description, dropping stopwords and short words."""
    return [
        word
        for word in re.findall(r"\b\w+\b", text.lower())
        if word not in _ISSUE_STOP_WORDS and len(word) > 2
    ]


def _score_issue(title: str, body: str, keywords: list[str], phrase: str) -> int:
    """Score one issue against the problem description.

    A keyword in the title is worth 2, in the body 1; an exact phrase match in
    the title adds 10. Empty keyword lists score 0 so callers fall back to
    recency instead of matching everything.
    """
    title_l = title.lower()
    body_l = body.lower()
    score = 0
    for keyword in keywords:
        if keyword in title_l:
            score += 2
        elif keyword in body_l:
            score += 1
    if phrase and phrase.strip() and phrase.strip().lower() in title_l:
        score += 10
    return score


def _version_compatible(issue_version: str, drupal_major: str | None) -> bool:
    """True unless the issue's version field encodes a different Drupal major.

    drupal.org stores the project's own branch in ``field_issue_version``
    ("6.3.x-dev", "7.x-1.x", "10.3.x"). Only strings whose leading number is a
    plausible Drupal major (>= 7) can be compared; project-era branches like
    ``6.3.x-dev`` are not Drupal 6 claims, so they never filter anything out.
    """
    if not drupal_major or not issue_version:
        return True
    match = re.match(r"^(\d+)\.", issue_version)
    if not match:
        return True
    major = int(match.group(1))
    if major < 7:
        return True
    return str(major) == drupal_major


def _local_drupal_major(root: str | None) -> str | None:
    """Read the Drupal major version from a local codebase, if available."""
    if not root:
        return None
    try:
        content = (Path(root) / "core" / "lib" / "Drupal.php").read_text(
            encoding="utf-8", errors="ignore"
        )
    except OSError:
        return None
    match = re.search(r"const VERSION = '([^']+)'", content)
    return match.group(1).split(".")[0] if match else None


def _issue_body(issue: dict[str, Any]) -> str:
    """Flatten an issue node's body (dict or list shaped) to plain text."""
    body = issue.get("body")
    raw = ""
    if isinstance(body, dict):
        raw = str(body.get("value", ""))
    elif isinstance(body, list) and body and isinstance(body[0], dict):
        raw = str(body[0].get("value", ""))
    return _strip_html(raw, 600)


def _total_usage(node: dict[str, Any]) -> int:
    """Sum a project's usage counts across release lines."""
    usage = node.get("project_usage") or {}
    if not isinstance(usage, dict):
        return 0
    return sum(
        int(value)
        for key, value in usage.items()
        if key != "total" and str(value).isdigit()
    )


async def _node_list(params: dict[str, str], *, max_pages: int = 1) -> list[dict[str, Any]]:
    """Fetch up to ``max_pages`` pages of an api-d7 node.json query."""
    items: list[dict[str, Any]] = []
    for page in range(max_pages):
        query = urlencode({**params, "page": str(page)})
        response = await _fetch(f"{DRUPAL_ORG_API}/node.json?{query}")
        batch = (response.json() or {}).get("list", [])
        items.extend(batch)
        if len(batch) < 50:
            break
    return items


async def _project_nid(machine_name: str) -> str | None:
    """Resolve a project's node id: exact machine-name lookup, then any
    project type via its page (covers themes and distributions)."""
    name = machine_name.strip().strip("/")
    if not name:
        return None
    query = urlencode({"type": "project_module", "field_project_machine_name": name})
    response = await _fetch(f"{DRUPAL_ORG_API}/node.json?{query}")
    found = (response.json() or {}).get("list", [])
    if found:
        return str(found[0].get("nid"))
    try:
        return str((await _resolve_project(name))["nid"])
    except Exception:  # noqa: BLE001 - the caller turns None into an error message
        return None


async def _category_terms() -> list[dict[str, str]]:
    """All drupal.org project categories (vocabulary 3), cached per process."""
    global _CATEGORY_CACHE
    if _CATEGORY_CACHE is None:
        query = urlencode({"vocabulary": "3"})
        response = await _fetch(f"{DRUPAL_ORG_API}/taxonomy_term.json?{query}")
        _CATEGORY_CACHE = [
            {"tid": str(term.get("tid")), "name": str(term.get("name", ""))}
            for term in (response.json() or {}).get("list", [])
        ]
    return _CATEGORY_CACHE


def _match_category(terms: list[dict[str, str]], category: str) -> dict[str, str] | None:
    """Find a category term by exact name, then by substring either way."""
    wanted = category.strip().lower()
    if not wanted:
        return None
    for term in terms:
        if term["name"].lower() == wanted:
            return term
    for term in terms:
        name = term["name"].lower()
        if wanted in name or name in wanted:
            return term
    return None


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

    @mcp.tool()
    async def module_issues_search(
        module_name: str,
        problem_description: str,
        limit: int = 10,
        drupal_version: str | None = None,
    ) -> dict[str, Any]:
        """Search a module's drupal.org issue queue for issues that match a problem.

        Describes the problem (e.g. "Azure AD attribute mapping fails") and the
        most recently updated issues are scored on keyword overlap with their
        titles and bodies; the best matches come back first, each with a link.
        Set drupal_version (e.g. "10") to hide issues filed against other major
        versions; when unset it is detected from DRUPAL_ROOT if configured.
        """
        limit = max(1, min(limit, 50))
        try:
            nid = await _project_nid(module_name)
            if not nid:
                return {"error": f"No drupal.org project named {module_name!r}."}
            major = drupal_version or _local_drupal_major(get_settings().DRUPAL_ROOT)
            issues = await _node_list(
                {
                    "type": "project_issue",
                    "field_project": nid,
                    "sort": "changed",
                    "direction": "DESC",
                },
                max_pages=2,
            )
            keywords = _issue_keywords(problem_description)
            kept = [
                issue
                for issue in issues
                if _version_compatible(str(issue.get("field_issue_version") or ""), major)
            ]
            # Some queues are versioned by the project (e.g. "5.x-dev"), never
            # by Drupal; a strict filter there would hide every issue, so fall
            # back to unfiltered results and say so.
            version_ignored = bool(issues and not kept and major)
            if version_ignored:
                kept = issues
            scored: list[dict[str, Any]] = []
            recent: list[dict[str, Any]] = []
            for issue in kept:
                entry = {
                    "title": issue.get("title", ""),
                    "url": issue.get("url", ""),
                    "status": _ISSUE_STATUS.get(
                        str(issue.get("field_issue_status") or ""),
                        str(issue.get("field_issue_status") or ""),
                    ),
                    "drupal_version": issue.get("field_issue_version"),
                    "comments": issue.get("comment_count", 0),
                    "changed": issue.get("changed"),
                    "relevance": _score_issue(
                        str(issue.get("title", "")),
                        _issue_body(issue),
                        keywords,
                        problem_description,
                    ),
                }
                if entry["relevance"] > 0:
                    scored.append(entry)
                elif len(recent) < limit:
                    recent.append(entry)
            scored.sort(key=lambda item: item["relevance"], reverse=True)
            results = scored[:limit]
            payload: dict[str, Any] = {
                "project": module_name,
                "nid": nid,
                "keywords": keywords,
                "drupal_version": major,
                "count": len(results),
                "results": results,
            }
            notes: list[str] = []
            if not results and recent:
                notes.append(
                    "No issue matched those keywords; showing the most recently "
                    "updated issues instead."
                )
                payload["results"] = recent
                payload["count"] = len(recent)
            if version_ignored:
                notes.append(
                    f"Every issue was hidden by the drupal_version={major!r} filter "
                    "(this queue versions branches by the project, not Drupal), "
                    "so the filter was ignored."
                )
            if notes:
                payload["note"] = " ".join(notes)
            return _ensure_dict(payload)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def module_popular(limit: int = 20, category: str | None = None) -> dict[str, Any]:
        """List the most-installed modules on Drupal.org, newest usage first.

        Optionally filter by a drupal.org category such as "E-commerce",
        "Security", "SEO", or "Media" (case-insensitive, substrings work). Usage
        is summed across every release line, so a module's full install base
        shows up in one number. Categories are listed in the error if the name
        does not match one.
        """
        limit = max(1, min(limit, 50))
        try:
            params: dict[str, str] = {"type": "project_module"}
            resolved: dict[str, str] | None = None
            if category:
                terms = await _category_terms()
                resolved = _match_category(terms, category)
                if not resolved:
                    return {
                        "error": f"No drupal.org category matches {category!r}.",
                        "available": [term["name"] for term in terms],
                    }
                params["taxonomy_vocabulary_3"] = resolved["tid"]
            nodes = await _node_list(params, max_pages=4)
            modules = [
                {
                    "machine_name": node.get("field_project_machine_name", ""),
                    "title": node.get("title", ""),
                    "url": node.get("url", ""),
                    "usage": _total_usage(node),
                    "description": _strip_html(
                        str((node.get("body") or {}).get("value", ""))
                        if isinstance(node.get("body"), dict)
                        else "",
                        200,
                    ),
                }
                for node in nodes
            ]
            modules = [module for module in modules if module["machine_name"]]
            modules.sort(key=lambda module: module["usage"], reverse=True)
            top = modules[:limit]
            return _ensure_dict({
                "category": resolved["name"] if resolved else None,
                "count": len(top),
                "searched": len(modules),
                "results": top,
            })
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def module_recommendation(need: str) -> dict[str, Any]:
        """Recommend modules for a need: what the local codebase already ships, plus drupal.org options.

        Combines the local codebase index (available when DRUPAL_ROOT is set)
        with drupal.org search, so the answer starts with modules you already
        have before suggesting downloads.
        """
        local: list[dict[str, Any]] = []
        searcher = deps.get("codebase_service")
        local_available = searcher is not None
        if searcher is not None:
            try:
                local = searcher.search_modules(need, limit=5)
            except Exception:  # noqa: BLE001 - local index issues must not sink the tool
                local = []
        org: list[dict[str, str]] = []
        org_error: str | None = None
        try:
            org = [r for r in await _search(need) if r["type"] == "module"][:5]
        except Exception as e:
            org_error = str(e)
        payload: dict[str, Any] = {
            "need": need,
            "local_indexed": local_available,
            "local_modules": local,
            "drupal_org_modules": org,
        }
        if org_error:
            payload["drupal_org_error"] = org_error
        if local:
            payload["note"] = (
                "Matching modules are already in this codebase - prefer "
                "extending or enabling those before adding a dependency."
            )
        elif not org:
            payload.setdefault("note", "No matches found locally or on drupal.org.")
        return _ensure_dict(payload)
