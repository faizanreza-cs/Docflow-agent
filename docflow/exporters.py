"""Send approved data where the business needs it: CSV, a webhook, or Google Sheets."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx

INVOICE_COLUMNS = [
    "source",
    "status",
    "confidence",
    "vendor_name",
    "invoice_number",
    "po_number",
    "issue_date",
    "due_date",
    "currency",
    "subtotal",
    "tax",
    "total",
]


def _cell(v: Any) -> Any:
    """Stop document text from running as a spreadsheet formula (=, +, -, @ ...)."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def _rows(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Invoice rows only: receipts and contracts have no place in an AP import."""
    rows = []
    for r in records:
        if r.get("doc_type") != "invoice":
            continue
        data = r.get("data") or {}
        rows.append({c: _cell(r.get(c, data.get(c))) for c in INVOICE_COLUMNS})
    return rows


def to_csv(records: Iterable[dict[str, Any]], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=INVOICE_COLUMNS)
        w.writeheader()
        w.writerows(_rows(records))
    return path


def to_webhook(records: Iterable[dict[str, Any]], url: str, timeout: float = 10.0) -> int:
    """POST each record as JSON (e.g. to Zapier, Make, n8n or your ERP). Returns count sent."""
    n = 0
    with httpx.Client(timeout=timeout) as client:
        for r in records:
            client.post(url, json=r).raise_for_status()
            n += 1
    return n


def to_google_sheet(
    records: Iterable[dict[str, Any]], sheet_id: str, worksheet: str = "Invoices"
) -> int:
    """Append rows using a service account (GOOGLE_APPLICATION_CREDENTIALS)."""
    try:
        import gspread
    except ImportError as e:  # pragma: no cover - optional extra
        raise RuntimeError("needs the 'sheets' extra: pip install 'docflow-agent[sheets]'") from e
    ws = gspread.service_account().open_by_key(sheet_id).worksheet(worksheet)
    rows = [[row[c] for c in INVOICE_COLUMNS] for row in _rows(records)]
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    return len(rows)
