"""Site status, update, and health tools.

These answer the questions an agent asks first -- what is wrong with this
site, what needs updating, can this server even talk to it -- without a
browser login to /admin/reports. Every check is read-only.
"""

import json
from typing import Any

from fastmcp import FastMCP

from ._utils import drush_result, run_composer

_SEVERITIES = ("error", "warning", "info", "ok")

_DRUSH_HINT = (
    "Drush could not be run. Check DRUSH_PATH (for containers set it to "
    "'ddev drush' or 'lando drush' and start the server from the project "
    "root), or install Drush in the project with 'composer require drush/drush'."
)


def _requirement_rows(data: Any) -> list[dict[str, Any]]:
    """Normalise `drush core:requirements --format=json` output to a list.

    The command returns a dict keyed by requirement id; older Drush returned
    a list. Either way each row keeps its id so callers can address one.
    """
    rows: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for req_id, row in data.items():
            if isinstance(row, dict):
                rows.append({"id": req_id, **row})
    elif isinstance(data, list):
        for index, row in enumerate(data):
            if isinstance(row, dict):
                rows.append({"id": row.get("id", str(index)), **row})
    return rows


def _dev_dependencies(root: str | None) -> set[str] | None:
    """Package names in composer.json's require-dev, or None if unreadable.

    `composer outdated` lists dev packages with no flag to exclude them and
    marks none of them as dev, so the only way to answer "production
    updates only" is to read require-dev from composer.json itself.
    """
    import os

    for candidate in (root, "."):
        if not candidate:
            continue
        path = os.path.join(candidate, "composer.json")
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        require_dev = data.get("require-dev")
        if isinstance(require_dev, dict):
            return set(require_dev)
    return None


def _audit_advisories(data: Any) -> dict[str, list[dict[str, Any]]]:
    """Normalise `composer audit --format=json` advisories to name -> rows."""
    out: dict[str, list[dict[str, Any]]] = {}
    raw = data.get("advisories") if isinstance(data, dict) else None
    if isinstance(raw, dict):
        for name, rows in raw.items():
            if isinstance(rows, list):
                out[str(name)] = [r for r in rows if isinstance(r, dict)]
    return out


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def status_report(
        severity_filter: str | None = None, include_ok: bool = False
    ) -> dict[str, Any]:
        """Run the site's status report (what /admin/reports/status shows).

        Read-only. Returns each requirement with its title, severity
        ("error", "warning", "info", or "ok"), description, and value.
        By default errors and warnings are returned; use `include_ok` for
        the whole report or `severity_filter` for one level.

        A failure here is usually the site's own requirements checker
        breaking, not this tool: the drush error is returned verbatim.
        """
        if not drush:
            return {"error": "Drush not available"}
        if severity_filter is not None and severity_filter.lower() not in _SEVERITIES:
            return {
                "error": (
                    f"severity_filter must be one of {', '.join(_SEVERITIES)}"
                )
            }
        result = await drush.run("core:requirements", ["--format=json"])
        if result.get("returncode"):
            payload: dict[str, Any] = drush_result(result)
            payload["note"] = (
                "The site's requirements checker failed; run 'drush "
                "core:requirements' in the project to see why."
            )
            return payload

        rows = _requirement_rows(result.get("data"))
        counts: dict[str, int] = {level: 0 for level in _SEVERITIES}
        unknown = 0
        for row in rows:
            level = str(row.get("severity", "")).lower()
            if level in counts:
                counts[level] += 1
            else:
                unknown += 1
        if unknown:
            counts["unknown"] = unknown

        wanted = severity_filter.lower() if severity_filter else None
        kept: list[dict[str, Any]] = []
        for row in rows:
            level = str(row.get("severity", "")).lower()
            classified = level if level in _SEVERITIES else "unknown"
            if wanted:
                if classified == wanted:
                    kept.append(row)
            elif include_ok or classified in ("error", "warning", "unknown"):
                # An unrecognised severity is kept rather than hidden: the
                # site is saying something this tool cannot classify.
                kept.append(row)

        payload = {
            "requirements": kept,
            "returned": len(kept),
            "total": len(rows),
            "counts": counts,
        }
        if severity_filter:
            payload["filtered_by"] = severity_filter.lower()
        return payload

    @mcp.tool()
    async def database_updates() -> dict[str, Any]:
        """List pending database updates (read-only; runs nothing).

        Answers "did the modules I just updated leave schema behind?".
        Use `drush_command("updatedb")` (or the `drush_updb` tool) to apply
        them, after a database backup.
        """
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("updatedb:status", ["--format=json"])
        if result.get("returncode"):
            return drush_result(result)

        data = result.get("data")
        stderr = str(result.get("stderr", ""))
        pending: list[Any] | None = None
        note: str | None = None
        if isinstance(data, list):
            pending = data
        elif isinstance(data, dict):
            updates = data.get("updates")
            if isinstance(updates, list):
                pending = updates
            elif set(data) == {"output"} and isinstance(data["output"], str):
                # Drush printed text on stdout instead of JSON: parse the
                # sentence rather than the shape.
                text = data["output"].strip()
                if "No database updates required" in text:
                    pending = []
                    note = text
                else:
                    note = f"Could not parse the output: {text[:400]}"
            elif data:
                # A keyed map of update name -> description.
                pending = [
                    {"update": key, "description": value}
                    for key, value in data.items()
                ]
        elif isinstance(data, str):
            if "No database updates required" in data:
                pending = []
                note = data.strip()
            else:
                note = f"Could not parse the output: {data.strip()[:400]}"

        if pending is None and "No database updates required" in stderr:
            # Drush's [success] log lines go to stderr, so a clean site can
            # send nothing at all on stdout; the sentence is still the answer.
            pending = []
            note = next(
                (line.strip() for line in stderr.splitlines()
                 if "No database updates required" in line),
                "No database updates required.",
            )
        if pending is None and not stderr and not data:
            note = "Drush returned no output; updatedb:status may not exist on this site."

        payload: dict[str, Any] = {
            "pending": pending if pending is not None else [],
            "count": len(pending) if pending is not None else None,
        }
        if pending is None:
            payload["note"] = (
                note
                or "Drush returned no recognisable update list; the site may "
                "be too old for updatedb:status."
            )
            if stderr.strip():
                payload["stderr"] = stderr.strip()[:400]
            payload["output"] = drush_result(result)["output"]
        elif pending:
            payload["hint"] = (
                "Back up the database, then apply with 'drush updatedb' "
                "(the drush_updb tool)."
            )
        elif note:
            payload["note"] = note
        return payload

    @mcp.tool()
    async def available_updates(
        include_dev: bool = False, security_only: bool = False
    ) -> dict[str, Any]:
        """List packages with newer versions available, from composer.

        Read-only (`composer outdated`); needs the project's composer.json
        and network access. Packages are grouped into core, contrib, and
        other. Dev dependencies are excluded unless `include_dev` is set --
        filtered via composer.json's require-dev, because composer marks
        none of them itself.

        With `security_only`, the outdated list is cross-referenced against
        `composer audit`: only packages that are both outdated and covered
        by a security advisory are returned, with the advisories attached.
        (The `composer_audit` tool lists advisories regardless of updates.)
        """
        result = await run_composer(["outdated", "--format=json"], tail=None)
        if result.get("returncode"):
            return {
                "error": result.get("error") or "composer outdated failed",
                "command": result.get("command"),
            }
        try:
            document = json.loads(result["output"])
        except ValueError:
            return {
                "error": "composer outdated returned output that is not JSON",
                "command": result.get("command"),
                "output": str(result["output"])[:400],
            }

        installed = document.get("installed") if isinstance(document, dict) else None
        if not isinstance(installed, list):
            installed = []
        packages: list[dict[str, Any]] = []
        for entry in installed:
            if not isinstance(entry, dict):
                continue
            packages.append(
                {
                    "name": entry.get("name"),
                    "version": entry.get("version"),
                    "latest": entry.get("latest"),
                    "latest_status": entry.get("latest-status"),
                    "direct": bool(entry.get("direct-dependency")),
                    "abandoned": bool(entry.get("abandoned")),
                    "description": entry.get("description"),
                }
            )

        payload: dict[str, Any] = {}
        dev_filtered = False
        if not include_dev:
            dev = _dev_dependencies(None)
            if dev:
                packages = [p for p in packages if p["name"] not in dev]
                dev_filtered = True
            else:
                payload["note"] = (
                    "composer.json's require-dev could not be read, so dev "
                    "dependencies are included; pass include_dev=true to "
                    "acknowledge that."
                )

        advisories: dict[str, list[dict[str, Any]]] | None = None
        if security_only:
            audit = await run_composer(["audit", "--format=json"], tail=None)
            if audit.get("returncode") == 0:
                try:
                    advisories = _audit_advisories(json.loads(audit["output"]))
                except ValueError:
                    advisories = None
            if advisories is not None:
                kept = []
                for package in packages:
                    rows = advisories.get(str(package["name"]))
                    if rows:
                        package = {
                            **package,
                            "advisories": [
                                {
                                    "title": row.get("title"),
                                    "cve": row.get("cve"),
                                    "affected_versions": row.get(
                                        "affectedVersions"
                                    ),
                                    "link": row.get("link"),
                                }
                                for row in rows
                            ],
                        }
                        kept.append(package)
                packages = kept
            else:
                payload["security_note"] = (
                    "composer audit did not return advisories, so every "
                    "outdated package is listed without the security filter."
                )

        core = [p for p in packages if str(p["name"]).startswith("drupal/core")]
        contrib = [
            p
            for p in packages
            if str(p["name"]).startswith("drupal/")
            and not str(p["name"]).startswith("drupal/core")
        ]
        other = [
            p
            for p in packages
            if not str(p["name"]).startswith("drupal/")
        ]

        payload.update(
            {
                "total": len(packages),
                "core": core,
                "contrib": contrib,
                "other": other,
                "dev_filtered": dev_filtered,
                "security_only": security_only,
            }
        )
        return payload

    @mcp.tool()
    async def health_check() -> dict[str, Any]:
        """Check that this server can actually reach a working Drupal site.

        Runs four read-only probes: Drush and the site status, the database
        connection, the JSON:API index, and the modules the other tools
        assume (jsonapi required; dblog and basic_auth recommended).
        Each failure comes with the concrete fix. Run this first when other
        tools return opaque connection errors.
        """
        if not drush:
            return {
                "ok": False,
                "error": "Drush not available",
                "problems": [
                    {
                        "check": "drush",
                        "problem": "No Drush client is configured.",
                        "hint": _DRUSH_HINT,
                    }
                ],
            }
        problems: list[dict[str, str]] = []

        result: dict[str, Any]
        try:
            result = await drush.run("status", ["--format=json"])
        except Exception as exc:  # noqa: BLE001 - report any failure as data
            result = {"returncode": 1, "stderr": str(exc)}
        data = result.get("data") if not result.get("returncode") else None
        status = data if isinstance(data, dict) else {}

        drush_ok = bool(status.get("drupal-version"))
        drush_info: dict[str, Any] = {
            "ok": drush_ok,
            "drush_version": status.get("drush-version")
            or status.get("drush-package"),
            "drupal_version": status.get("drupal-version"),
            "php_version": status.get("php-version"),
            "bootstrap": status.get("bootstrap"),
        }
        if not drush_ok:
            reason = str(result.get("stderr", "")).strip() or "no output"
            drush_info["error"] = reason[:300]
            problems.append(
                {
                    "check": "drush",
                    "problem": "Drush could not bootstrap the site.",
                    "hint": _DRUSH_HINT,
                }
            )

        db_status = status.get("db-status", "")
        database = {"ok": db_status == "Connected", "status": db_status}
        if not database["ok"]:
            problems.append(
                {
                    "check": "database",
                    "problem": f"Database reports '{db_status or 'no status'}'.",
                    "hint": (
                        "Start the environment (ddev start / lando start) and "
                        "check the database settings in settings.php."
                    ),
                }
            )
        if status.get("bootstrap") not in (None, "", "Successful"):
            problems.append(
                {
                    "check": "bootstrap",
                    "problem": f"Bootstrap is '{status.get('bootstrap')}'.",
                    "hint": "Rebuild caches with 'drush cr'.",
                }
            )

        jsonapi_info: dict[str, Any]
        if jsonapi is None:
            jsonapi_info = {
                "ok": False,
                "error": "No JSON:API client configured",
            }
            problems.append(
                {
                    "check": "jsonapi",
                    "problem": "The server has no JSON:API client.",
                    "hint": "Set DRUPAL_BASE_URL and restart the MCP server.",
                }
            )
        else:
            try:
                index = await jsonapi.get_index()
                jsonapi_info = {
                    "ok": bool(index),
                    "resources": (
                        len(index)
                        if isinstance(index, (list, dict))
                        else None
                    ),
                }
            except Exception as exc:  # noqa: BLE001 - report as data
                jsonapi_info = {"ok": False, "error": str(exc)[:300]}
                problems.append(
                    {
                        "check": "jsonapi",
                        "problem": "The JSON:API index did not answer.",
                        "hint": (
                            "Enable it with 'drush en jsonapi -y', and check "
                            "DRUPAL_BASE_URL (set DRUPAL_VERIFY_SSL=false for "
                            "self-signed dev certificates)."
                        ),
                    }
                )

        modules: dict[str, Any] = {"jsonapi": None, "dblog": None, "basic_auth": None}
        try:
            pm = await drush.run("pm:list", ["--status=enabled", "--format=json"])
            listed = pm.get("data") if not pm.get("returncode") else None
            if isinstance(listed, dict):
                enabled = set(listed)
            elif isinstance(listed, list):
                enabled = {
                    str(item.get("name"))
                    for item in listed
                    if isinstance(item, dict)
                }
            else:
                enabled = set()
            for name in modules:
                modules[name] = name in enabled
            modules["enabled_count"] = len(enabled)
            if not enabled:
                modules["note"] = "Could not list enabled modules."
        except Exception as exc:  # noqa: BLE001 - report as data
            modules["error"] = str(exc)[:300]

        if modules.get("jsonapi") is False:
            problems.append(
                {
                    "check": "module:jsonapi",
                    "problem": "The jsonapi module is not enabled.",
                    "hint": "Enable it with 'drush en jsonapi -y'.",
                }
            )
        if modules.get("dblog") is False:
            problems.append(
                {
                    "check": "module:dblog",
                    "problem": (
                        "The dblog module is off, so watchdog logs are not "
                        "being recorded."
                    ),
                    "hint": "Enable it with 'drush en dblog -y'.",
                }
            )
        if modules.get("basic_auth") is False:
            problems.append(
                {
                    "check": "module:basic_auth",
                    "problem": (
                        "The basic_auth module is off, so DRUPAL_API_TOKEN "
                        "cannot authenticate."
                    ),
                    "hint": (
                        "Enable it with 'drush en basic_auth -y', or rely on "
                        "username/password session auth instead."
                    ),
                }
            )

        return {
            "ok": drush_ok and database["ok"] and jsonapi_info["ok"],
            "drush": drush_info,
            "database": database,
            "jsonapi": jsonapi_info,
            "modules": modules,
            "problems": problems,
        }
