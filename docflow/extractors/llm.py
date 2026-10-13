"""LLM extractors with schema-constrained (structured) output."""

from __future__ import annotations

import os
from typing import Any

from docflow.config import Settings
from docflow.schemas import SCHEMAS, DocType

SYSTEM = """\
You extract structured data from business documents for an accounts-payable team.
Rules:
- Copy values exactly as printed; do not compute or infer amounts that are not on the page.
- Dates: return ISO format. If a slash date is ambiguous, use the convention the rest of the
  document makes unambiguous (any day > 12 reveals day-first).
- Use null for fields that are not present. Never invent a PO number, due date or tax.
- Currency: ISO 4217 code.
"""


def _prompt(text: str, doc_type: DocType) -> str:
    return f"Document type: {doc_type.value}\n\n<document>\n{text}\n</document>"


class AnthropicExtractor:
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        import anthropic

        if not settings.model:
            raise ValueError("DOCFLOW_MODEL must be set to an Anthropic model id")
        self.model = settings.model
        self.client = anthropic.Anthropic()

    def extract(self, text: str, doc_type: DocType) -> dict[str, Any]:
        schema = SCHEMAS[doc_type]
        resp = self.client.messages.parse(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM,
            messages=[{"role": "user", "content": _prompt(text, doc_type)}],
            output_format=schema,
        )
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            raise RuntimeError(f"model returned no structured output ({resp.stop_reason})")
        return resp.parsed_output.model_dump()


class OpenAIExtractor:
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI

        self.model = os.environ.get("DOCFLOW_OPENAI_MODEL") or settings.model
        if not self.model:
            raise ValueError("DOCFLOW_OPENAI_MODEL or DOCFLOW_MODEL must be set")
        self.client = OpenAI()

    def extract(self, text: str, doc_type: DocType) -> dict[str, Any]:
        resp = self.client.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": _prompt(text, doc_type)},
            ],
            response_format=SCHEMAS[doc_type],
        )
        parsed = resp.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("model returned no structured output")
        return parsed.model_dump()
