"""Extractor selection."""

from __future__ import annotations

import os
from typing import Any, Protocol

from docflow.config import Settings, get_settings
from docflow.schemas import DocType


class Extractor(Protocol):
    name: str

    def extract(self, text: str, doc_type: DocType) -> dict[str, Any]: ...


def get_extractor(name: str | None = None, settings: Settings | None = None) -> Extractor:
    s = settings or get_settings()
    name = (name or s.provider).lower()
    if name == "auto":
        name = "anthropic" if os.environ.get("ANTHROPIC_API_KEY") and s.model else "rules"
    if name == "anthropic":
        from docflow.extractors.llm import AnthropicExtractor

        return AnthropicExtractor(s)
    if name == "openai":
        from docflow.extractors.llm import OpenAIExtractor

        return OpenAIExtractor(s)
    if name in {"rules", "mock"}:
        from docflow.extractors.rules import RulesExtractor

        return RulesExtractor()
    raise ValueError(f"unknown extractor {name!r} (auto | anthropic | openai | rules)")
