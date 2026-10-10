"""DDEV/Lando site management service."""
import asyncio
from typing import Any, Dict, List, Optional


class SiteManager:
    """Manages local development environments (DDEV, Lando)."""

    def __init__(self, settings: Any):
        self._ddev = settings.DDEV_BINARY

    async def _run(self, cmd: List[str], cwd: Optional[str] = None) -> Dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await proc.communicate()
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
            "command": " ".join(cmd),
        }

    async def ddev_start(self, cwd: Optional[str] = None) -> Dict[str, Any]:
        return await self._run([self._ddev, "start"], cwd=cwd)

    async def ddev_stop(self, cwd: Optional[str] = None) -> Dict[str, Any]:
        return await self._run([self._ddev, "stop"], cwd=cwd)

    async def ddev_exec(self, command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        return await self._run([self._ddev, "exec", command], cwd=cwd)
