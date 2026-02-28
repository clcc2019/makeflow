from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from utils.config import get_settings
from utils.logger import log


class LLMClient:
    """Unified LLM client supporting DeepSeek / OpenAI / Qwen / Gemini via OpenAI-compatible API."""

    def __init__(self, provider: str | None = None):
        settings = get_settings()
        llm_config = settings["llm"]
        self.provider = provider or llm_config["default_provider"]
        provider_cfg = llm_config["providers"][self.provider]

        self.model = provider_cfg["model"]
        self.client = OpenAI(
            api_key=provider_cfg["api_key"],
            base_url=provider_cfg.get("base_url"),
        )
        log.info(f"LLM client initialized: provider={self.provider}, model={self.model}")

    def chat(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: dict | None = None,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        try:
            resp = self.client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content or ""
            log.info(f"LLM response received: {len(content)} chars, provider={self.provider}")
            return content.strip()
        except Exception as e:
            log.error(f"LLM call failed: {e}")
            raise

    def chat_json(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict | list:
        """Chat and parse the response as JSON. Instructs the model to return JSON."""
        json_system = system + "\n\nYou MUST respond with valid JSON only. No markdown, no explanation."
        raw = self.chat(
            prompt=prompt,
            system=json_system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)
        return json.loads(cleaned)


def get_llm(provider: str | None = None) -> LLMClient:
    return LLMClient(provider=provider)
