"""Business-rule validation. Each rule returns Issues; the pipeline turns them into a score."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, ValidationError

from docflow.schemas import SCHEMAS, ContractTerms, DocType, Invoice, Issue, Receipt

TOLERANCE = 0.02  # currency rounding


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= TOLERANCE


def parse(doc_type: DocType, raw: dict[str, Any]) -> tuple[BaseModel | None, list[Issue]]:
    """Coerce raw extractor output into the typed schema."""
    try:
        return SCHEMAS[doc_type].model_validate(raw), []
    except ValidationError as e:
        issues = [
            Issue(field=".".join(str(p) for p in err["loc"]) or "document", message=err["msg"])
            for err in e.errors()
        ]
        return None, issues


def check_invoice(inv: Invoice, known_vendors: tuple[str, ...] = ()) -> list[Issue]:
    issues: list[Issue] = []
    if inv.line_items:
        items_sum = round(sum(li.amount for li in inv.line_items), 2)
        ref = inv.subtotal if inv.subtotal is not None else inv.total
        if not _close(items_sum, ref):
            issues.append(
                Issue(
                    field="line_items",
                    message=f"line items sum to {items_sum:.2f} but "
                    f"{'subtotal' if inv.subtotal is not None else 'total'} "
                    f"is {ref:.2f}",
                )
            )
        for li in inv.line_items:
            if not _close(li.quantity * li.unit_price, li.amount):
                issues.append(
                    Issue(
                        field="line_items",
                        severity="warning",
                        message=f"'{li.description}': {li.quantity:g} x "
                        f"{li.unit_price:.2f} != {li.amount:.2f}",
                    )
                )
    if inv.subtotal is not None:
        expected = inv.subtotal + (inv.tax or 0.0)
        if not _close(expected, inv.total):
            issues.append(
                Issue(
                    field="total",
                    message=f"subtotal + tax = {expected:.2f} but total is {inv.total:.2f}",
                )
            )
    if inv.due_date and inv.due_date < inv.issue_date:
        issues.append(Issue(field="due_date", message="due date is before the issue date"))
    today = date.today()
    if inv.issue_date > today + timedelta(days=30):
        issues.append(
            Issue(
                field="issue_date",
                severity="warning",
                message="issue date is more than 30 days in the future",
            )
        )
    if known_vendors and inv.vendor_name not in known_vendors:
        issues.append(
            Issue(
                field="vendor_name",
                severity="warning",
                message=f"vendor '{inv.vendor_name}' is not on the approved list",
            )
        )
    if inv.total <= 0:
        issues.append(Issue(field="total", message="total must be positive"))
    return issues


def check_receipt(r: Receipt) -> list[Issue]:
    issues: list[Issue] = []
    if r.subtotal is not None and not _close(r.subtotal + (r.tax or 0.0), r.total):
        issues.append(Issue(field="total", message="subtotal + tax does not equal total"))
    if r.items and r.subtotal is not None:
        s = round(sum(i.amount for i in r.items), 2)
        if not _close(s, r.subtotal):
            issues.append(
                Issue(
                    field="items",
                    severity="warning",
                    message=f"items sum to {s:.2f}, subtotal is {r.subtotal:.2f}",
                )
            )
    return issues


def check_contract(c: ContractTerms) -> list[Issue]:
    issues: list[Issue] = []
    if len(c.parties) < 2:
        issues.append(Issue(field="parties", message="expected at least two parties"))
    if c.end_date and c.end_date < c.effective_date:
        issues.append(Issue(field="end_date", message="end date is before the effective date"))
    if c.auto_renewal and c.notice_period_days is None:
        issues.append(
            Issue(
                field="notice_period_days",
                severity="warning",
                message="auto-renewal without a notice period",
            )
        )
    return issues


def check(model: BaseModel, known_vendors: tuple[str, ...] = ()) -> list[Issue]:
    if isinstance(model, Invoice):
        return check_invoice(model, known_vendors)
    if isinstance(model, Receipt):
        return check_receipt(model)
    if isinstance(model, ContractTerms):
        return check_contract(model)
    return []


def confidence(issues: list[Issue], n_null_optional: int = 0) -> float:
    """1.0 minus penalties. Errors cost 0.35, warnings 0.1, missing optional fields 0.02."""
    score = 1.0
    for i in issues:
        score -= 0.35 if i.severity == "error" else 0.10
    score -= 0.02 * n_null_optional
    return round(max(0.0, min(1.0, score)), 3)
