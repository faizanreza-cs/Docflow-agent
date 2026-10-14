"""Deterministic regex extractor.

Runs offline with no API key: used for demos, CI and as a cheap first pass. It knows common
label variants ("Invoice #", "Invoice No.", "Amount Due", ...) but not every layout. That's
the gap the LLM extractor closes, and the eval reports both.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from dateutil import parser as dateparser

from docflow.schemas import DocType

# trailing guard: "1.234,56" (European) fails to match and goes to review, not misread as 1.23
_NUM = r"([0-9][0-9,]*\.[0-9]{2})(?![0-9,])"
_DATE = r"([A-Z][a-z]{2,8} \d{1,2}, \d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})"


def _dayfirst(text: str) -> bool:
    """A document uses day-first dates if any slash date has a first field > 12."""
    return any(int(a) > 12 for a, _ in re.findall(r"\b(\d{1,2})/(\d{1,2})/\d{4}\b", text))


def _date(s: str | None, dayfirst: bool) -> date | None:
    if not s:
        return None
    try:
        return dateparser.parse(s, dayfirst=dayfirst).date()
    except (ValueError, OverflowError):
        return None


def _money(s: str | None) -> float | None:
    return float(s.replace(",", "")) if s else None


def _first(patterns: list[str], text: str, flags: int = re.I) -> str | None:
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return m.group(1).strip()
    return None


def extract_invoice(text: str) -> dict[str, Any]:
    df = _dayfirst(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    items = []
    for m in re.finditer(rf"^(.+?)\s+([0-9.]+)\s+x\s+{_NUM}\s+=\s+{_NUM}\s*$", text, re.M):
        items.append(
            {
                "description": m.group(1).strip(),
                "quantity": float(m.group(2)),
                "unit_price": _money(m.group(3)),
                "amount": _money(m.group(4)),
            }
        )
    return {
        "invoice_number": _first([r"invoice\s*(?:#|no\.?|number:?)\s*([A-Z0-9-]+)"], text),
        "vendor_name": lines[0] if lines else None,
        "po_number": _first([r"\bPO (?:Number|No\.?|#):?\s*([A-Z0-9-]+)"], text),
        "issue_date": _date(
            _first([rf"(?:invoice date|issued|(?<!due )date)\s*:?\s*{_DATE}"], text), df
        ),
        "due_date": _date(_first([rf"(?:due date|payment due|due)\s*:?\s*{_DATE}"], text), df),
        "currency": _first([r"\b(USD|EUR|GBP|INR|CAD|AUD)\b"], text, 0) or "USD",
        "line_items": items,
        "subtotal": _money(_first([rf"subtotal\s*:?\s*(?:[A-Z]{{3}}\s*)?{_NUM}"], text)),
        "tax": _money(_first([rf"\btax\s*:?\s*(?:[A-Z]{{3}}\s*)?{_NUM}"], text)),
        "total": _money(
            _first(
                [rf"\b(?<!sub)(?:total due|amount due|total)\s*:?\s*(?:[A-Z]{{3}}\s*)?{_NUM}"], text
            )
        ),
    }


def extract_receipt(text: str) -> dict[str, Any]:
    df = _dayfirst(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    items = []
    for m in re.finditer(
        rf"^(?!SUBTOTAL|TAX|TOTAL)([A-Za-z][^\n]*?)\s{{2,}}{_NUM}\s*$", text, re.M
    ):
        amt = _money(m.group(2))
        items.append(
            {"description": m.group(1).strip(), "quantity": 1.0, "unit_price": amt, "amount": amt}
        )
    return {
        "merchant": lines[0] if lines else None,
        "date": _date(_first([rf"date\s*:?\s*{_DATE}"], text), df),
        "payment_method": _first([r"PAID\s+(.+)"], text),
        "currency": "USD",
        "items": items,
        "subtotal": _money(_first([rf"subtotal\s+{_NUM}"], text)),
        "tax": _money(_first([rf"\btax\s+{_NUM}"], text)),
        "total": _money(_first([rf"^\s*total\s+{_NUM}"], text, re.I | re.M)),
    }


def extract_contract(text: str) -> dict[str, Any]:
    parties = re.findall(
        r"([A-Z][A-Za-z&.,' ]+?) \(\"(?:Customer|Supplier|Vendor|Client)\"\)", text
    )
    renew = bool(re.search(r"renews? automatically|auto(?:matic)?[- ]renew", text, re.I))
    notice = _first([r"(\d+)\s+days(?:'|’)? (?:prior )?written notice"], text)
    title_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return {
        "title": title_line.title(),
        "parties": [p.strip().removeprefix("and ").strip() for p in parties],
        "effective_date": _date(_first([rf"as of\s+{_DATE}"], text), False),
        "end_date": _date(_first([rf"until\s+{_DATE}"], text), False),
        "auto_renewal": renew,
        "notice_period_days": int(notice) if notice else None,
        "governing_law": _first([r"laws of (?:the State of )?([A-Z][A-Za-z ]+?)[.,]"], text),
        "payment_terms": _first([r"\b(Net \d+)\b"], text),
        "liability_cap": _first([r"liability is capped at ([^.]+)\."], text),
    }


EXTRACTORS = {
    DocType.invoice: extract_invoice,
    DocType.receipt: extract_receipt,
    DocType.contract: extract_contract,
}


class RulesExtractor:
    name = "rules"

    def extract(self, text: str, doc_type: DocType) -> dict[str, Any]:
        fn = EXTRACTORS.get(doc_type)
        if fn is None:
            raise ValueError(f"no rules extractor for {doc_type}")
        return fn(text)
