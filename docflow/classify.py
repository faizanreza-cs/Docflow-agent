"""Cheap keyword classifier. Good enough to route; the extractor can override."""

from __future__ import annotations

import re

from docflow.schemas import DocType

_SIGNALS = {
    DocType.invoice: [r"\binvoice\b", r"\bbill to\b", r"\bdue date\b", r"\binv[-# ]", r"\bpo\b"],
    DocType.receipt: [
        r"\breceipt\b",
        r"\bthank you for (your )?(purchase|shopping)",
        r"\bvisa\b|\bmastercard\b|\bcash\b",
        r"\bchange\b",
        r"\bstore\b",
    ],
    DocType.contract: [
        r"\bagreement\b",
        r"\bparties\b",
        r"\bgoverning law\b",
        r"\btermination\b",
        r"\bwhereas\b",
        r"\beffective date\b",
    ],
}


def classify(text: str) -> DocType:
    t = text.lower()
    scores = {k: sum(bool(re.search(p, t)) for p in pats) for k, pats in _SIGNALS.items()}
    best, score = max(scores.items(), key=lambda kv: kv[1])
    return best if score >= 2 else DocType.unknown
