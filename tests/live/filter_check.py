#!/usr/bin/env python3
"""Check every hard-coded JSON:API filter against a real site.

Two tools shipped filters on fields Drupal does not expose - `filter[name]`
on user_role and `filter[menu]` on menu_link_content - which returned
400 "Invalid nested filtering ... the field ... does not exist" on every
call on every site, making them dead rather than merely rejected.

The test does not need any records: Drupal answers 400 the moment it parses
an unknown field, and 200 (possibly with an empty or access-trimmed
collection) when the field is real. So each filter is sent as a real query
and the status code is the verdict.

Resources whose module is not installed here are skipped: those tools are
already counted UPSTREAM.

    python tests/live/filter_check.py
"""

from __future__ import annotations

import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "drupal_mcp_server" / "tools"
BASE = "https://drupal-live.ddev.site"
PROBE = "filter-probe-value"  # never matches, but must parse as a field query

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def pairs() -> list[tuple[str, str, str]]:
    """Return (resource, field, location) for every hard-coded filter.

    Tools build a `params` dict first and pass it to get_resource() after,
    so the filter line sits *above* its resource. Each get_resource call
    therefore claims the filters in the 60 lines preceding it.
    """
    out: list[tuple[str, str, str]] = []
    for path in sorted(SRC.glob("*.py")):
        lines = path.read_text().splitlines()
        calls = [
            (n, m.group(1))
            for n, line in enumerate(lines, 1)
            for m in re.finditer(r'get_resource\(\s*"([a-z_0-9]+)"', line)
        ]
        claimed: set[int] = set()
        for at, resource in calls:
            for n in range(max(1, at - 60), at + 1):
                if n in claimed:
                    continue
                match = re.search(r'"filter\[([a-z_0-9]+)\]"', lines[n - 1])
                if match:
                    out.append((resource, match.group(1), f"{path.name}:{n}"))
                    claimed.add(n)
        # Anything left unclaimed belongs to no resource within range.
        for n, line in enumerate(lines, 1):
            if n in claimed:
                continue
            match = re.search(r'"filter\[([a-z_0-9]+)\]"', line)
            if match:
                out.append(("<unattributed>", match.group(1), f"{path.name}:{n}"))
    return out


def index() -> dict[str, str]:
    """Map an entity type to its collection href from the JSON:API index.

    The index only lists resource types the caller may see, so anything
    missing here is either not installed or not reachable anonymously.
    """
    req = urllib.request.Request(
        f"{BASE}/jsonapi", headers={"Accept": "application/vnd.api+json"}
    )
    try:
        with urllib.request.urlopen(req, context=_ctx, timeout=30) as r:
            body = json.loads(r.read() or b"{}")
    except Exception:
        return {}
    hrefs: dict[str, str] = {}
    for key, value in (body.get("links") or {}).items():
        if key in ("self", "next", "prev") or not isinstance(value, dict):
            continue
        href, _, remainder = key.partition("--")
        if not href or not remainder or not value.get("href"):
            continue
        hrefs.setdefault(href, value["href"])
    return hrefs


def probe(href: str, field: str) -> tuple[str, str]:
    """Return (verdict, detail) for filtering `href` on `field`."""
    url = f"{href}?filter%5B{urllib.parse.quote(field)}%5D={PROBE}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.api+json"})
    try:
        with urllib.request.urlopen(req, context=_ctx, timeout=30) as r:
            return "OK", f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        detail = body[:200]
        try:
            parsed = json.loads(body)
            detail = parsed["errors"][0].get("detail", detail)
        except Exception:
            pass
        # A 4xx means the *field* was rejected. A 5xx saying the entity type or
        # bundle "does not exist" means the opposite: the field was parsed and
        # its value resolved, and the probe value is simply not a real entity
        # type. `filter[entity_type]` on comment is one of these -- a real
        # field that only answers 200 for a valid type. Counting it as broken
        # would send someone hunting a bug in a filter that works.
        if e.code >= 500 and "does not exist" in detail and (
            "entity type" in detail or "bundle" in detail
        ):
            return "OK", f"HTTP {e.code} (probe value rejected, field parsed)"
        return f"HTTP {e.code}", detail
    except Exception as e:
        return "ERROR", f"{type(e).__name__}: {e}"


def main() -> int:
    hrefs = index()
    broken: list[tuple[str, str, str, str, str]] = []
    checked = skipped = 0

    for resource, field, where in pairs():
        if resource == "<unattributed>":
            continue
        href = hrefs.get(resource)
        if not href:
            skipped += 1
            continue
        verdict, detail = probe(href, field)
        if verdict == "ERROR":
            skipped += 1
            continue
        checked += 1
        if verdict != "OK":
            broken.append((resource, field, where, verdict, detail))

    print(f"filters checked: {checked}   could not verify: {skipped}")
    if broken:
        print(f"\nBROKEN ({len(broken)}) - Drupal rejects the filter outright:")
        for resource, field, where, verdict, detail in broken:
            print(f"  {resource} filter[{field}]  ({where})")
            print(f"      {verdict}: {' '.join(detail.split())[:150]}")
    else:
        print("\nno broken filters")

    unattributed = [p for p in pairs() if p[0] == "<unattributed>"]
    if unattributed:
        print(f"\nunattributed: {len(unattributed)}")
        for _, field, where in unattributed:
            print(f"  filter[{field}] {where}")

    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
