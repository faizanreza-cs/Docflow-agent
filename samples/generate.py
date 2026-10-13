"""Generate synthetic sample documents (PDF + .eml) with ground-truth JSON.

Layouts, labels and date formats vary on purpose so extractors are tested on realistic
variety. A few documents contain deliberate errors (totals that don't add up, a due date
before the issue date) to exercise validation and the review queue.

Run: python samples/generate.py
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

ROOT = Path(__file__).parent
DOCS, TRUTH = ROOT / "docs", ROOT / "truth"

VENDORS = [
    ("Northwind Supplies LLC", "1450 Market St, Denver CO"),
    ("Acme Cloud Services Inc", "88 Harbor Way, Seattle WA"),
    ("Blue Ridge Office Co", "12 Pine Rd, Asheville NC"),
    ("Helix Lab Instruments", "400 Science Pkwy, Boston MA"),
    ("Orbit Logistics Ltd", "7 Dock Lane, Newark NJ"),
]
CUSTOMER = "Contoso Health Partners, 500 Lake Ave, Chicago IL"
ITEMS = [
    ("Printer paper A4 (box)", 32.50),
    ("Toner cartridge XL", 89.00),
    ("Cloud compute (vCPU-hours)", 0.12),
    ("Object storage (GB-month)", 0.023),
    ("Pipette tips 200uL (rack)", 14.75),
    ("Nitrile gloves (box of 100)", 9.90),
    ("Freight - pallet", 145.00),
    ("Consulting hours", 125.00),
    ("Ergonomic chair", 289.00),
]
DATE_FORMATS = ["%Y-%m-%d", "%b %d, %Y", "%d/%m/%Y"]
LABELS = [
    {"no": "Invoice #", "date": "Invoice Date", "due": "Due Date", "total": "Total Due"},
    {"no": "Invoice No.", "date": "Date", "due": "Payment Due", "total": "TOTAL"},
    {"no": "Invoice Number:", "date": "Issued", "due": "Due", "total": "Amount Due"},
]


def _money(x: float) -> str:
    return f"{x:,.2f}"


def _write_lines(path: Path, lines: list[tuple[float, str, int, bool]]) -> None:
    """lines: (y_mm, text, x_mm, bold)."""
    c = canvas.Canvas(str(path), pagesize=A4)
    for y, text, x, bold in lines:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        c.drawString(x * mm, y * mm, text)
    c.save()


def make_invoice(i: int, rng: random.Random, broken: str | None = None) -> dict:
    vendor, addr = rng.choice(VENDORS)
    lab = LABELS[i % len(LABELS)]
    fmt = DATE_FORMATS[i % len(DATE_FORMATS)]
    issue = date(2026, 8, 1) + timedelta(days=rng.randint(0, 60))
    due = issue + timedelta(days=rng.choice([15, 30, 45]))
    if broken == "due_before_issue":
        due = issue - timedelta(days=5)
    n_items = rng.randint(2, 4)
    items = []
    for desc, price in rng.sample(ITEMS, n_items):
        qty = rng.choice([1, 2, 3, 5, 10, 40, 100])
        items.append(
            {
                "description": desc,
                "quantity": float(qty),
                "unit_price": price,
                "amount": round(qty * price, 2),
            }
        )
    subtotal = round(sum(it["amount"] for it in items), 2)
    tax = round(subtotal * rng.choice([0.0, 0.05, 0.0825]), 2)
    total = round(subtotal + tax, 2)
    printed_total = total + 100.0 if broken == "bad_total" else total
    number = f"INV-{2026}{i:04d}"
    po = f"PO-{rng.randint(10000, 99999)}" if i % 2 == 0 else None

    y = 280
    lines: list[tuple[float, str, int, bool]] = [(y, vendor, 20, True), (y - 6, addr, 20, False)]
    lines += [(y - 20, "INVOICE", 150, True)]
    lines += [
        (y - 30, f"{lab['no']} {number}", 120, False),
        (y - 36, f"{lab['date']}: {issue.strftime(fmt)}", 120, False),
        (y - 42, f"{lab['due']}: {due.strftime(fmt)}", 120, False),
    ]
    if po:
        lines.append((y - 48, f"PO Number: {po}", 120, False))
    lines += [(y - 30, "Bill To:", 20, True), (y - 36, CUSTOMER, 20, False)]
    y2 = y - 65
    lines.append((y2, "Description          Qty     Unit Price     Amount", 20, True))
    for k, it in enumerate(items):
        lines.append(
            (
                y2 - 7 * (k + 1),
                f"{it['description']}  {it['quantity']:g}  x  {_money(it['unit_price'])}"
                f"  =  {_money(it['amount'])}",
                20,
                False,
            )
        )
    y3 = y2 - 7 * (n_items + 2)
    lines += [
        (y3, f"Subtotal: USD {_money(subtotal)}", 120, False),
        (y3 - 6, f"Tax: USD {_money(tax)}", 120, False),
        (y3 - 12, f"{lab['total']}: USD {_money(printed_total)}", 120, True),
        (y3 - 30, "Payment terms: bank transfer. Thank you for your business.", 20, False),
    ]
    name = f"invoice_{i:02d}"
    _write_lines(DOCS / f"{name}.pdf", lines)
    truth = {
        "doc_type": "invoice",
        "expect_review": broken is not None,
        "data": {
            "invoice_number": number,
            "vendor_name": vendor,
            "po_number": po,
            "issue_date": issue.isoformat(),
            "due_date": due.isoformat(),
            "currency": "USD",
            "subtotal": subtotal,
            "tax": tax,
            "total": printed_total,
            "line_items": items,
        },
    }
    return {name: truth}


def make_receipt(i: int, rng: random.Random) -> dict:
    merchant = rng.choice(["Corner Coffee Co", "Metro Office Depot", "QuickFuel #482", "City Deli"])
    d = date(2026, 9, 1) + timedelta(days=rng.randint(0, 25))
    items = []
    for desc, price in rng.sample(
        [
            ("Latte", 4.75),
            ("Bagel", 3.25),
            ("Notebook", 6.99),
            ("Pens 12pk", 8.49),
            ("Unleaded 12.4 gal", 43.28),
            ("Sandwich", 9.50),
        ],
        2,
    ):
        items.append({"description": desc, "quantity": 1.0, "unit_price": price, "amount": price})
    subtotal = round(sum(x["amount"] for x in items), 2)
    tax = round(subtotal * 0.07, 2)
    total = round(subtotal + tax, 2)
    pay = rng.choice(["VISA ****4242", "MASTERCARD ****5100", "CASH"])
    lines = [
        (270, merchant, 70, True),
        (264, "RECEIPT", 85, True),
        (256, f"Date: {d.strftime('%m/%d/%Y')}", 60, False),
    ]
    for k, it in enumerate(items):
        lines.append((246 - 6 * k, f"{it['description']}    {_money(it['amount'])}", 60, False))
    lines += [
        (228, f"SUBTOTAL    {_money(subtotal)}", 60, False),
        (222, f"TAX    {_money(tax)}", 60, False),
        (216, f"TOTAL    {_money(total)}", 60, True),
        (208, f"PAID {pay}", 60, False),
        (198, "Thank you for shopping with us!", 60, False),
    ]
    name = f"receipt_{i:02d}"
    _write_lines(DOCS / f"{name}.pdf", lines)
    return {
        name: {
            "doc_type": "receipt",
            "expect_review": False,
            "data": {
                "merchant": merchant,
                "date": d.isoformat(),
                "subtotal": subtotal,
                "tax": tax,
                "total": total,
                "currency": "USD",
            },
        }
    }


def make_contract(i: int) -> dict:
    eff = date(2026, 10, 1) + timedelta(days=30 * i)
    end = eff.replace(year=eff.year + 1)
    party_b = ["Northwind Supplies LLC", "Helix Lab Instruments"][i % 2]
    lines = [
        (275, "MASTER SERVICES AGREEMENT", 60, True),
        (
            262,
            f"This Agreement is entered into as of {eff.strftime('%B %d, %Y')} (the "
            f'"Effective Date") between',
            20,
            False,
        ),
        (
            256,
            f'Contoso Health Partners ("Customer") and {party_b} ("Supplier") (the "Parties").',
            20,
            False,
        ),
        (
            244,
            "1. Term. This Agreement begins on the Effective Date and continues until "
            f"{end.strftime('%B %d, %Y')}.",
            20,
            False,
        ),
        (
            238,
            "It renews automatically for successive one-year terms unless either party gives "
            "60 days written notice.",
            20,
            False,
        ),
        (226, "2. Fees. Invoices are payable Net 30 from receipt.", 20, False),
        (
            214,
            "3. Limitation of Liability. Each party's liability is capped at the fees paid in "
            "the prior 12 months.",
            20,
            False,
        ),
        (
            202,
            "4. Termination. Either party may terminate for material breach on 30 days notice.",
            20,
            False,
        ),
        (
            190,
            "5. Governing Law. This Agreement is governed by the laws of the State of Delaware.",
            20,
            False,
        ),
    ]
    name = f"contract_{i:02d}"
    _write_lines(DOCS / f"{name}.pdf", lines)
    return {
        name: {
            "doc_type": "contract",
            "expect_review": False,
            "data": {
                "parties": ["Contoso Health Partners", party_b],
                "effective_date": eff.isoformat(),
                "end_date": end.isoformat(),
                "auto_renewal": True,
                "notice_period_days": 60,
                "governing_law": "Delaware",
                "payment_terms": "Net 30",
            },
        }
    }


def make_email(pdf_name: str) -> None:
    msg = EmailMessage()
    msg["From"] = "billing@northwind.example"
    msg["To"] = "ap@contoso.example"
    msg["Subject"] = "Invoice attached"
    msg.set_content("Hi team, please find our invoice attached. Regards, Northwind billing")
    msg.add_attachment(
        (DOCS / f"{pdf_name}.pdf").read_bytes(),
        maintype="application",
        subtype="pdf",
        filename=f"{pdf_name}.pdf",
    )
    (DOCS / "email_with_invoice.eml").write_bytes(bytes(msg))


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    TRUTH.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    truth: dict = {}
    for i in range(1, 10):
        broken = {4: "bad_total", 8: "due_before_issue"}.get(i)
        truth |= make_invoice(i, rng, broken)
    for i in range(1, 5):
        truth |= make_receipt(i, rng)
    for i in range(1, 3):
        truth |= make_contract(i)
    make_email("invoice_01")
    for name, t in truth.items():
        (TRUTH / f"{name}.json").write_text(json.dumps(t, indent=2) + "\n")
    print(f"wrote {len(truth)} documents + 1 email to {DOCS}")


if __name__ == "__main__":
    main()
