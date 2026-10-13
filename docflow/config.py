"""Runtime settings from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    # auto: use the Anthropic API when ANTHROPIC_API_KEY and DOCFLOW_MODEL are set, else rules
    provider: str = field(default_factory=lambda: _env("DOCFLOW_PROVIDER", "auto"))
    model: str = field(default_factory=lambda: _env("DOCFLOW_MODEL", ""))
    review_threshold: float = field(
        default_factory=lambda: float(_env("DOCFLOW_REVIEW_THRESHOLD", "0.85"))
    )
    db_path: Path = field(default_factory=lambda: Path(_env("DOCFLOW_DB", "data/docflow.db")))
    # comma-separated list of approved vendors; unknown vendors are flagged for review
    known_vendors: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            v.strip() for v in _env("DOCFLOW_KNOWN_VENDORS", "").split(",") if v.strip()
        )
    )


def get_settings() -> Settings:
    return Settings()
