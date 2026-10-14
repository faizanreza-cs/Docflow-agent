from datetime import date

import pytest

from docflow import validate
from docflow.config import Settings
from docflow.extractors.rules import RulesExtractor
from docflow.ingest import Document, load
from docflow.pipeline import Pipeline
from docflow.review import ReviewQueue
from docflow.schemas import Invoice, LineItem


def _pipe(queue=None, **kw):
    return Pipeline(RulesExtractor(), queue, Settings(review_threshold=0.85, **kw))


def _invoice(**kw):
    base = dict(
        invoice_number="A1",
        vendor_name="V",
        issue_date=date(2026, 1, 1),
        due_date=date(2026, 1, 31),
        subtotal=100.0,
        tax=10.0,
        total=110.0,
        line_items=[LineItem(description="x", quantity=2, unit_price=50, amount=100)],
    )
    return Invoice(**{**base, **kw})


def test_clean_invoice_has_no_issues():
    assert validate.check(_invoice()) == []


def test_total_mismatch_is_error():
    issues = validate.check(_invoice(total=200.0))
    assert any(i.field == "total" and i.severity == "error" for i in issues)


def test_due_before_issue_is_error():
    issues = validate.check(_invoice(due_date=date(2025, 12, 1)))
    assert any(i.field == "due_date" for i in issues)


def test_unknown_vendor_needs_review():
    issues = validate.check(_invoice(), known_vendors=("Acme",))
    assert [i.severity for i in issues] == ["error"]


def test_confidence_penalties():
    assert validate.confidence([]) == 1.0
    assert validate.confidence(validate.check(_invoice(total=200.0))) < 0.85


def test_broken_invoices_route_to_review(samples):
    p = _pipe()
    bad = p.process_document(load(samples / "docs" / "invoice_04.pdf")[0])
    good = p.process_document(load(samples / "docs" / "invoice_02.pdf")[0])
    assert bad.status == "needs_review" and good.status == "auto_approved"


def test_empty_document_fails_cleanly():
    assert _pipe().process_document(Document("x.pdf", "   ")).status == "failed"


def test_extractor_crash_is_contained():
    class Boom:
        name = "boom"

        def extract(self, text, doc_type):
            raise RuntimeError("API down")

    p = Pipeline(Boom(), None, Settings())
    r = p.process_document(Document("x", "INVOICE\nBill To: a\nDue Date: 2026-01-01"))
    assert r.status == "failed" and "API down" in r.issues[0].message


def test_duplicate_invoice_flagged(samples):
    q = ReviewQueue(":memory:")
    p = _pipe(q)
    first = p.process_path(samples / "docs" / "invoice_02.pdf")[0]
    second = p.process_path(samples / "docs" / "invoice_02.pdf")[0]
    assert first.status == "auto_approved"
    assert second.status == "needs_review"
    assert any("duplicate" in i.message for i in second.issues)


def test_tax_without_subtotal_is_consistent():
    assert validate.check(_invoice(subtotal=None)) == []  # items 100 + tax 10 = total 110


def test_duplicate_cannot_be_approved_and_matching_ignores_case(samples):
    q = ReviewQueue(":memory:")
    p = _pipe(q)
    p.process_path(samples / "docs" / "invoice_02.pdf")
    p.process_path(samples / "docs" / "invoice_02.pdf")
    second = q.list("needs_review")[0]
    with pytest.raises(ValueError, match="duplicate"):
        q.approve(second["id"], "bob")
    v, n = second["vendor"], second["doc_number"]
    assert q.is_duplicate(f" {v.upper()} ", n.lower())


def test_corrections_update_duplicate_keys(samples):
    q = ReviewQueue(":memory:")
    p = _pipe(q)
    p.process_path(samples / "docs" / "invoice_04.pdf")
    doc = q.list("needs_review")[0]
    total = round(doc["data"]["subtotal"] + doc["data"]["tax"], 2)
    q.approve(doc["id"], "alice", {"total": total, "invoice_number": 20260004})
    assert q.get(doc["id"])["doc_number"] == "20260004"  # digits typed by a reviewer
    assert q.is_duplicate(doc["vendor"], "20260004")


def test_unreadable_file_does_not_stop_the_batch(tmp_path):
    (tmp_path / "a_broken.pdf").write_bytes(b"not a pdf")
    (tmp_path / "b.txt").write_text("INVOICE\nInvoice # A-1\nDate: 2026-01-02\nTOTAL: USD 5.00")
    results = _pipe(ReviewQueue(":memory:")).process_dir(tmp_path)
    assert [r.status for r in results][0] == "failed" and len(results) == 2


def test_review_approve_requires_fix(samples):
    q = ReviewQueue(":memory:")
    p = _pipe(q)
    p.process_path(samples / "docs" / "invoice_04.pdf")  # printed total is off by 100
    doc = q.list("needs_review")[0]
    with pytest.raises(ValueError, match="cannot approve"):
        q.approve(doc["id"], "alice")
    fixed_total = doc["data"]["subtotal"] + doc["data"]["tax"]
    out = q.approve(doc["id"], "alice", {"total": round(fixed_total, 2)})
    assert out["status"] == "approved" and out["reviewer"] == "alice"
    assert q.stats() == {"approved": 1}
