"""Drush command client."""
import asyncio
import json
from typing import Any


class DrushClient:
    """Runs drush commands as subprocesses."""

    def __init__(self, settings: Any):
        self._drush = settings.DRUSH_PATH
        self._alias = settings.DRUSH_ALIAS
        self._timeout = 120  # seconds

    async def run(
        self, command: str, args: list[str] | None = None, cwd: str | None = None
    ) -> dict[str, Any]:
        cmd = [self._drush, self._alias, command, "--format=json"] + (args or [])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except TimeoutError:
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
