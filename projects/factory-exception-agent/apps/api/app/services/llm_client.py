from __future__ import annotations

import json
import logging
import re

import httpx

from app.core.config import Settings


logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _strip_thinking_markup(content: str) -> str:
        if not content:
            return ""
        cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
        return cleaned.strip()

    @property
    def enabled(self) -> bool:
        return (
            not self.settings.mock_mode
            and self.settings.llm_provider in {"openai-compatible", "openai", "compatible"}
            and bool(self.settings.llm_api_key)
        )

    def render(self, system_prompt: str, user_prompt: str) -> str | None:
        if not self.enabled:
            return None

        url = self.settings.llm_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.settings.llm_model,
            "temperature": self.settings.llm_temperature,
            "max_tokens": self.settings.llm_max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if self.settings.llm_reasoning_effort:
            payload["reasoning_effort"] = self.settings.llm_reasoning_effort
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
                response = client.post(url, headers=headers, content=json.dumps(payload))
                response.raise_for_status()
            data = response.json()
            message = (data.get("choices") or [{}])[0].get("message", {}) or {}
            content = self._strip_thinking_markup(message.get("content") or "")
            if content:
                return content
            reasoning = self._strip_thinking_markup(
                message.get("reasoning")
                or message.get("reasoning_content")
                or ""
            )
            if reasoning:
                logger.warning("LLM returned reasoning without final content, fallback to local formatter.")
            return None
        except Exception as exc:
            logger.warning("LLM call failed, fallback to mock formatter: %s", exc)
            return None
