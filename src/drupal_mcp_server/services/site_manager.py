"""DDEV/Lando site management service."""
import asyncio
import os
from typing import Any


class SiteManager:
    """Manages local development environments (DDEV, Lando)."""

    def __init__(self, settings: Any):
        self._ddev = settings.DDEV_BINARY

    async def _run(self, cmd: list[str], cwd: str | None = None) -> dict[str, Any]:
        # A missing directory would raise FileNotFoundError out of
        # create_subprocess_exec; answer like every other tool failure.
        if cwd is not None and not os.path.isdir(cwd):
            return {
                "returncode": 2,
                "stdout": "",
                "stderr": (
                    f"Project directory not found: {cwd!r}. project_name is a "
                    "directory — pass the path containing .ddev (for example "
                    "'/path/to/site'), not a registered project name."
                ),
                "command": " ".join(cmd),
            }
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

    async def ddev_start(self, cwd: str | None = None) -> dict[str, Any]:
        return await self._run([self._ddev, "start"], cwd=cwd)

    async def ddev_stop(self, cwd: str | None = None) -> dict[str, Any]:
        return await self._run([self._ddev, "stop"], cwd=cwd)

    async def ddev_exec(self, command: str, cwd: str | None = None) -> dict[str, Any]:
        return await self._run([self._ddev, "exec", command], cwd=cwd)

    async def lando_start(self, cwd: str | None = None) -> dict[str, Any]:
        return await self._run(["lando", "start"], cwd=cwd)

    async def lando_stop(self, cwd: str | None = None) -> dict[str, Any]:
        return await self._run(["lando", "stop"], cwd=cwd)

    async def lando_exec(self, command: str, cwd: str | None = None) -> dict[str, Any]:
        return await self._run(["lando", "exec", command], cwd=cwd)
