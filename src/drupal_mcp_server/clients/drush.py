"""Drush command client."""

import asyncio
import json
import shlex
from typing import Any


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
        self._timeout = 120  # seconds

    def _command(self, command: str, args: list[str] | None, with_format: bool = True) -> list[str]:
        argv = list(self._drush)
        if self._alias:
            argv.append(self._alias)
        argv.append(command)
        args = list(args or [])
        # Many tools already pass --format=json themselves; adding it twice is
        # sloppy, and commands like `drush cron` reject the option outright.
        if with_format and not any(a.startswith("--format") for a in args):
            argv.append("--format=json")
        argv += args
        return argv

    async def run(
        self, command: str, args: list[str] | None = None, cwd: str | None = None
    ) -> dict[str, Any]:
        cmd = self._command(command, args)
        result = await self._exec(cmd, cwd)
        # `drush cron` and friends have no --format option. Retry once without
        # it rather than failing a command that would otherwise succeed.
        if result["returncode"] != 0 and "--format" in result.get("stderr", ""):
            retry = self._command(command, args, with_format=False)
            retried = await self._exec(retry, cwd)
            if retried["returncode"] == 0:
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
