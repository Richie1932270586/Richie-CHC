from __future__ import annotations

import json
import re

from app.core.config import Settings


JSON_BLOCK_RE = re.compile(r"```json\s*(.*?)```", re.DOTALL)


class PromptLoader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _read_file(self, filename: str) -> str:
        path = self.settings.prompts_dir / filename
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _extract_json_block(self, content: str) -> dict:
        match = JSON_BLOCK_RE.search(content)
        if not match:
            return {}
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}

    def system_prompt(self) -> str:
        return self._read_file("system_prompt.md")

    def tool_policies(self) -> dict:
        content = self._read_file("tool_policies.md")
        data = self._extract_json_block(content)
        data["raw_markdown"] = content
        return data

    def response_style(self) -> dict:
        content = self._read_file("response_style.md")
        data = self._extract_json_block(content)
        data["raw_markdown"] = content
        return data
