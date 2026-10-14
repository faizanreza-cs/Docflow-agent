import json
from datetime import date

from docflow.classify import classify
from docflow.extractors.rules import RulesExtractor, _dayfirst
from docflow.ingest import load
from docflow.schemas import DocType


def test_classify_sample_types(samples):
    for name, expected in [
        ("invoice_01", "invoice"),
        ("receipt_01", "receipt"),
        ("contract_01", "contract"),
    ]:
        assert classify(load(samples / "docs" / f"{name}.pdf")[0].text).value == expected
    assert classify("hello world") is DocType.unknown


def test_email_attachment_is_extracted(samples):
    docs = load(samples / "docs" / "email_with_invoice.eml")
    assert len(docs) == 1 and docs[0].source.endswith("#invoice_01.pdf")
    assert "INVOICE" in docs[0].text


def test_dayfirst_detection():
    assert _dayfirst("Issued: 28/09/2026")
    assert not _dayfirst("Date: 09/03/2026")


def test_rules_invoice_matches_truth(samples):
    truth = json.loads((samples / "truth" / "invoice_02.json").read_text())["data"]
    got = RulesExtractor().extract(
        load(samples / "docs" / "invoice_02.pdf")[0].text, DocType.invoice
    )
    assert got["invoice_number"] == truth["invoice_number"]
    assert got["issue_date"] == date.fromisoformat(truth["issue_date"])
    assert got["total"] == truth["total"]
    assert len(got["line_items"]) == len(truth["line_items"])


def test_total_not_confused_with_subtotal():
    text = (
        "INVOICE\nInvoice # A-1\nDate: 2026-01-02\n"
        "Subtotal: USD 100.00\nTax: USD 5.00\nTOTAL: USD 105.00"
    )
    assert RulesExtractor().extract(text, DocType.invoice)["total"] == 105.00


def test_rules_dont_misread_due_date_or_european_amounts():
    text = (
        "INVOICE\nInvoice # A-1\nDue Date: 2026-02-01\nInvoice Date: 2026-01-01\n"
        "Total: EUR 1.234,56"
    )
    got = RulesExtractor().extract(text, DocType.invoice)
    assert got["issue_date"] == date(2026, 1, 1) and got["due_date"] == date(2026, 2, 1)
    assert got["total"] is None  # unreadable amount -> review, never 1.23
