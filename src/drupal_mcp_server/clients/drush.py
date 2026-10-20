"""Drush command client."""

import asyncio
import json
import shlex
from typing import Any

# Commands with no --format option at all (verified on Drush 13): asking
# for one fails the bootstrap, and only the retry without it succeeds --
# costing every query twice.
_NO_FORMAT_COMMANDS = frozenset({"sql:query", "sqlq"})


class DrushClient:
    """Runs drush commands as subprocesses.

    ``DRUSH_PATH`` may contain arguments, so container-based setups work:
    set it to ``ddev drush`` (or ``lander drush``) and start the MCP server
    from the project directory.
    """

    def __init__(self, settings: Any):
        self._drush = shlex.split(str(getattr(settings, "DRUSH_PATH", "drush") or "drush"))
        if not self._drush:
            self._drush = ["drush"]
        self._alias = str(getattr(settings, "DRUSH_ALIAS", "") or "")
        # Not retried anywhere: drush commands mutate by default, and a
        # timed-out `user:create` that actually succeeded would be created
        # twice by a retry.
        self._timeout = int(getattr(settings, "DRUSH_TIMEOUT", 120))

    def _command(
        self, command: str, args: list[str], with_format: bool = True, alias: str | None = None
    ) -> list[str]:
        argv = list(self._drush)
        active = self._alias if alias is None else str(alias)
        if active:
            argv.append(active)
        argv.append(command)
        # Many tools already pass --format=json themselves; adding it twice is
        # sloppy, and commands like `drush cron` reject the option outright.
        # `sql:query` has no --format at all on Drush 13, so asking for it
        # costs a full failed bootstrap before the retry without one.
        if (
            with_format
            and command not in _NO_FORMAT_COMMANDS
            and not any(a.startswith("--format") for a in args)
        ):
            argv.append("--format=json")
        argv += args
        return argv

    @staticmethod
    def _flatten(parts: tuple[Any, ...]) -> list[str]:
        """Turn whatever a tool passes into a list of argv tokens.

        Call sites spell a command line every way there is: `run(*cmd)` with
        eight separate tokens, `run("config:set", [a, b, c])`, and
        `run("config:set", "a b c")`. Treating a string as a sequence turned
        the last form into one argument per character, so it never worked.
        """
        tokens: list[str] = []
        for part in parts:
            if part is None:
                continue
            if isinstance(part, str):
                tokens.extend(shlex.split(part) if part.split() else ([part] if part else []))
            elif isinstance(part, (list, tuple)):
                # Items in a list are already argv tokens and must be passed
                # through whole. Splitting each one destroyed anything holding
                # a space: `sql:query ["SHOW TABLES"]` became two arguments, so
                # drush answered "Too many arguments", and PHP handed to
                # php:eval was shredded before it ever reached Drupal.
                for item in part:
                    if item is None:
                        continue
                    tokens.append(str(item))
            else:
                tokens.append(str(part))
        return tokens

    async def run(
        self, *parts: Any, cwd: str | None = None, alias: str | None = None
    ) -> dict[str, Any]:
        """Run a drush command line.

        Accepts the command plus any number of argument tokens, in any
        combination of strings and lists::

            run("cron")
            run("status", ["--format=json"])
            run("config:set", "twig.config", "debug", "true")
            run(*("user:role:add", "authenticated", "1"))

        ``alias`` overrides DRUSH_ALIAS for this one call: sync_config and
        diff_config name a source and a target environment, and without it
        both halves ran against the site the server was started on --
        the environment parameters were echoed back but never applied.
        """
        if not parts:
            return {
                "returncode": 1,
                "data": {},
                "stderr": "No drush command was given.",
                "command": "",
            }
        command, rest = str(parts[0]), parts[1:]
        argv = self._flatten(rest)
        cmd = self._command(command, argv, alias=alias)
        result = await self._exec(cmd, cwd)
        # `drush cron` and friends have no --format option. Retry once without
        # it rather than failing a command that would otherwise succeed.
        if result["returncode"] != 0 and "--format" in result.get("stderr", ""):
            retried = await self._exec(
                self._command(command, argv, with_format=False, alias=alias), cwd
            )
            # Report the run that actually executed. Returning the original
            # made every failure read as "The --format option does not exist",
            # which buries the real reason.
            retried["format_flag_dropped"] = True
            return retried
        return result

    async def _exec(self, cmd: list[str], cwd: str | None) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
        except FileNotFoundError:
            # Without a distinct message every drush tool just reports
            # "No such file or directory", which reads like a product bug.
            return {
                "returncode": 127,
                "data": {},
                "stderr": (
                    f"Drush executable {cmd[0]!r} not found on PATH. "
                    "Set DRUSH_PATH to a working command (for example "
                    "'ddev drush') and start the MCP server from the project "
                    "directory."
                ),
                "command": " ".join(cmd),
            }
        except PermissionError:
            return {
                "returncode": 126,
                "data": {},
                "stderr": f"Drush executable {cmd[0]!r} is not executable.",
                "command": " ".join(cmd),
            }

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except TimeoutError:  # asyncio.TimeoutError is an alias on 3.11+
            proc.kill()
            return {
                "returncode": -1,
                "data": {},
                "stderr": f"Command timed out after {self._timeout}s",
                "command": " ".join(cmd),
            }
        try:
            data = json.loads(stdout.decode()) if stdout else {}
        except json.JSONDecodeError:
            data = {"output": stdout.decode()}
        return {
            "returncode": proc.returncode,
            "data": data,
            "stderr": stderr.decode(),
            "command": " ".join(cmd),
        }

    async def status(self) -> dict[str, Any]:
        return await self.run("status")
