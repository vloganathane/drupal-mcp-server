"""AI service for AI-powered Drupal operations.
Importer/Caller: server.py (FastMCP server creation) uses AIService
Affected API: Internal services module, provides complete() method for AI-enhanced tools
Data Schemas: None (service wrapper)
User Instruction: "Implement the actual MCP server (the tools, resources, and FastMCP app)"
"""
from typing import Any

import httpx


class AIService:
    """Service for AI-enhanced Drupal operations using configured providers."""

    def __init__(self, settings: Any):
        self.settings = settings

    async def complete(self, prompt: str, timeout: int | None = None) -> str:
        """Complete a prompt using the configured AI provider."""
        provider = self.settings.DEFAULT_AI_PROVIDER
        timeout_val = timeout or self.settings.AI_TIMEOUT
        if provider == "ollama":
            return await self._ollama_complete(prompt, timeout_val)
        elif provider == "openai":
            return await self._openai_complete(prompt, timeout_val)
        elif provider == "anthropic":
            return await self._anthropic_complete(prompt, timeout_val)
        elif provider == "nvidia_nim":
            return await self._nvidia_nim_complete(prompt, timeout_val)
        return f"[Mock AI response] {provider}: {prompt}"

    async def _ollama_complete(self, prompt: str, timeout: int) -> str:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self.settings.OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": self.settings.OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return str(data.get("response", ""))
        except Exception:
            return f"[AI Mock] {prompt}"

    async def _openai_complete(self, prompt: str, timeout: int) -> str:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.OPENAI_API_KEY}"},
                    json={
                        "model": self.settings.OPENAI_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return str(data["choices"][0]["message"]["content"])
        except Exception:
            return f"[AI Mock] {prompt}"

    async def _anthropic_complete(self, prompt: str, timeout: int) -> str:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": self.settings.ANTHROPIC_API_KEY},
                    json={
                        "model": self.settings.ANTHROPIC_MODEL,
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return str(data["content"][0]["text"])
        except Exception:
            return f"[AI Mock] {prompt}"

    async def _nvidia_nim_complete(self, prompt: str, timeout: int) -> str:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self.settings.NVIDIA_NIM_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.NVIDIA_NIM_API_KEY}"},
                    json={
                        "model": self.settings.NVIDIA_NIM_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return str(data["choices"][0]["message"]["content"])
        except Exception:
            return f"[AI Mock] {prompt}"
