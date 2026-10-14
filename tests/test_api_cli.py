import csv

from fastapi.testclient import TestClient

from docflow.cli import main
from docflow.exporters import to_csv


def test_cli_run_and_export(samples, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DOCFLOW_DB", str(tmp_path / "q.db"))
    out = tmp_path / "out.csv"
    assert main(["run", str(samples / "docs"), "--extractor", "rules", "--export", str(out)]) == 0
    rows = list(csv.DictReader(out.open()))
    assert rows and all(r["status"] == "auto_approved" for r in rows)
    assert all(r["invoice_number"] for r in rows)
    assert "REVIEW" in capsys.readouterr().out


def test_to_csv_columns(tmp_path):
    records = [
        {"source": "a", "doc_type": "invoice", "data": {"total": 5, "vendor_name": "=1+1"}},
        {"source": "b", "doc_type": "receipt", "data": {"total": 9}},
    ]
    rows = list(csv.DictReader(to_csv(records, tmp_path / "x.csv").open()))
    assert len(rows) == 1 and rows[0]["total"] == "5"  # receipts are not AP rows
    assert rows[0]["vendor_name"] == "'=1+1"  # never runs as a formula


def test_api_upload_and_review(samples, tmp_path, monkeypatch):
    monkeypatch.setenv("DOCFLOW_DB", str(tmp_path / "api.db"))
    monkeypatch.setenv("DOCFLOW_PROVIDER", "rules")
    import importlib

    import docflow.api as api

    importlib.reload(api)
    c = TestClient(api.app)
    with (samples / "docs" / "invoice_04.pdf").open("rb") as f:
        r = c.post("/documents", files={"file": ("invoice_04.pdf", f, "application/pdf")})
    assert r.status_code == 200 and r.json()[0]["status"] == "needs_review"
    pending = c.get("/documents", params={"status": "needs_review"}).json()
    assert (
        c.post(f"/documents/{pending[0]['id']}/approve", json={"reviewer": "bob"}).status_code
        == 422
    )
    assert (
        c.post(
            f"/documents/{pending[0]['id']}/reject",
            json={"reviewer": "bob", "note": "wrong vendor"},
        ).json()["status"]
        == "rejected"
    )
    assert c.get("/health").json()["status"] == "ok"
