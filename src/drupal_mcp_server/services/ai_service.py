"""Multi-provider AI service."""

from typing import Any

import httpx


class AIService:
    """Routes AI requests to configured provider."""

    def __init__(self, settings: Any):
        self.settings = settings
        self._provider = settings.DEFAULT_AI_PROVIDER
        self._enabled = settings.AI_ENABLED
        self._timeout = settings.AI_TIMEOUT

    async def complete(self, prompt: str, system: str | None = None) -> str:
        if not self._enabled:
            return ""
        if self._provider == "ollama":
            return await self._ollama(prompt, system)
        elif self._provider == "openai":
            return await self._openai(prompt, system)
        elif self._provider == "anthropic":
            return await self._anthropic(prompt, system)
        elif self._provider == "nvidia_nim":
            return await self._nvidia(prompt, system)
        raise ValueError(f"Unknown AI provider: {self._provider}")

    async def _ollama(self, prompt: str, system: str | None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self.settings.OLLAMA_BASE_URL}/api/chat",
                json={"model": self.settings.OLLAMA_MODEL, "messages": messages, "stream": False},
            )
        resp.raise_for_status()
        return resp.json()["message"]["content"]  # type: ignore[no-any-return]

    async def _openai(self, prompt: str, system: str | None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.OPENAI_API_KEY}"},
                json={"model": self.settings.OPENAI_MODEL, "messages": messages},
            )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]  # type: ignore[no-any-return]

    async def _anthropic(self, prompt: str, system: str | None) -> str:
        body: dict[str, Any] = {
            "model": self.settings.ANTHROPIC_MODEL,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json=body,
            )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]  # type: ignore[no-any-return]

    async def _nvidia(self, prompt: str, system: str | None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self.settings.NVIDIA_NIM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.NVIDIA_NIM_API_KEY}"},
                json={"model": self.settings.NVIDIA_NIM_MODEL, "messages": messages},
            )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]  # type: ignore[no-any-return]
