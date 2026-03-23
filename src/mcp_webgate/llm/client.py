"""Async OpenAI-compatible chat completion client (httpx, no SDK dependency)."""

from __future__ import annotations

import httpx

from ..config import LLMConfig


class LLMClient:
    """Async client for any OpenAI-compatible /v1/chat/completions endpoint.

    Covers: OpenAI, Ollama, LM Studio, vLLM, Together AI, Groq, and any provider
    that speaks the OpenAI chat completions protocol.
    """

    def __init__(self, cfg: LLMConfig) -> None:
        self._cfg = cfg

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.0,
    ) -> str:
        """Send a chat completion request and return the response text.

        Raises:
            RuntimeError: if LLM is not enabled in config.
            httpx.HTTPStatusError: on non-2xx response.
        """
        if not self._cfg.enabled:
            raise RuntimeError("LLM client is not enabled (set llm.enabled = true in config)")

        payload = {
            "model": self._cfg.model,
            "messages": messages,
            "temperature": temperature,
        }

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._cfg.api_key:
            headers["Authorization"] = f"Bearer {self._cfg.api_key}"

        url = self._cfg.base_url.rstrip("/") + "/chat/completions"

        async with httpx.AsyncClient(timeout=self._cfg.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        return data["choices"][0]["message"]["content"]
