"""Drush command client."""
import asyncio
import json
from typing import Any, Dict, List, Optional


class DrushClient:
    """Runs drush commands as subprocesses."""

    def __init__(self, settings: Any):
        self._drush = settings.DRUSH_PATH
        self._alias = settings.DRUSH_ALIAS

    async def run(
        self, command: str, args: Optional[List[str]] = None, cwd: Optional[str] = None
    ) -> Dict[str, Any]:
        cmd = [self._drush, self._alias, command, "--format=json"] + (args or [])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await proc.communicate()
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

    async def status(self) -> Dict[str, Any]:
        return await self.run("status")
