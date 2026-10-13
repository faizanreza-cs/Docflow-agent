"""Typed output schemas. These double as the JSON schema the LLM must fill."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class DocType(StrEnum):
    invoice = "invoice"
    receipt = "receipt"
    contract = "contract"
    unknown = "unknown"


class LineItem(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float
    amount: float


class Invoice(BaseModel):
    invoice_number: str
    vendor_name: str
    bill_to: str | None = None
    po_number: str | None = None
    issue_date: date
    due_date: date | None = None
    currency: str = Field(default="USD", description="ISO 4217 code")
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: float | None = None
    tax: float | None = None
    total: float


class Receipt(BaseModel):
    merchant: str
    date: date
    payment_method: str | None = None
    currency: str = "USD"
    items: list[LineItem] = Field(default_factory=list)
    subtotal: float | None = None
    tax: float | None = None
    total: float


class ContractTerms(BaseModel):
    title: str
    parties: list[str]
    effective_date: date
    end_date: date | None = None
    auto_renewal: bool = False
    notice_period_days: int | None = None
    governing_law: str | None = None
    payment_terms: str | None = None
    liability_cap: str | None = None


SCHEMAS: dict[DocType, type[BaseModel]] = {
    DocType.invoice: Invoice,
    DocType.receipt: Receipt,
    DocType.contract: ContractTerms,
}


class Issue(BaseModel):
    field: str
    message: str
    severity: Literal["error", "warning"] = "error"


class Result(BaseModel):
    """Everything the pipeline knows about one document."""

    source: str
    doc_type: DocType
    data: dict | None = None
    issues: list[Issue] = Field(default_factory=list)
    confidence: float = 0.0
    status: Literal["auto_approved", "needs_review", "failed"] = "needs_review"
    extractor: str = ""
    text_chars: int = 0
