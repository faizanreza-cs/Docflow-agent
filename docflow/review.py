"""SQLite-backed human review queue (and the system of record for processed documents)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docflow import validate
from docflow.schemas import DocType, Issue, Result

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    doc_type    TEXT NOT NULL,
    -- auto_approved | needs_review | approved | rejected | failed
    status      TEXT NOT NULL,
    confidence  REAL NOT NULL,
    extractor   TEXT NOT NULL,
    data        TEXT,
    issues      TEXT NOT NULL,
    vendor      TEXT,
    doc_number  TEXT,
    created_at  TEXT NOT NULL,
    reviewed_at TEXT,
    reviewer    TEXT,
    note        TEXT
);
CREATE INDEX IF NOT EXISTS ix_documents_dupe ON documents (vendor, doc_number);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ReviewQueue:
    def __init__(self, path: str | Path) -> None:
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)

    def is_duplicate(
        self,
        vendor: str | None,
        number: str | None,
        statuses: tuple[str, ...] = ("auto_approved", "needs_review", "approved", "failed"),
        exclude_id: int | None = None,
    ) -> bool:
        """Same vendor and number, ignoring case and spacing ("ACME CORP" == "Acme Corp ")."""
        if not vendor or not number:
            return False
        # shortcut: full scan (lower() skips the index), fine to ~100k documents; then store
        # normalised columns
        row = self.con.execute(
            "SELECT 1 FROM documents WHERE lower(trim(vendor)) = lower(trim(?))"
            " AND lower(trim(doc_number)) = lower(trim(?))"
            f" AND status IN ({','.join('?' * len(statuses))}) AND id != ?",
            (vendor, number, *statuses, exclude_id or -1),
        ).fetchone()
        return row is not None

    def add(self, r: Result) -> int:
        data = r.data or {}
        cur = self.con.execute(
            "INSERT INTO documents (source, doc_type, status, confidence, extractor, data, issues,"
            " vendor, doc_number, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                r.source,
                r.doc_type.value,
                r.status,
                r.confidence,
                r.extractor,
                json.dumps(r.data, default=str) if r.data is not None else None,
                json.dumps([i.model_dump() for i in r.issues]),
                data.get("vendor_name") or data.get("merchant"),
                data.get("invoice_number"),
                _now(),
            ),
        )
        self.con.commit()
        return int(cur.lastrowid or 0)

    def _row(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["data"] = json.loads(d["data"]) if d["data"] else None
        d["issues"] = json.loads(d["issues"])
        return d

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM documents"
        params: tuple[str, ...] = ()
        if status:
            sql, params = sql + " WHERE status = ?", (status,)
        return [self._row(r) for r in self.con.execute(sql + " ORDER BY id", params)]

    def get(self, doc_id: int) -> dict[str, Any]:
        row = self.con.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if row is None:
            raise KeyError(doc_id)
        return self._row(row)

    def approve(
        self,
        doc_id: int,
        reviewer: str,
        corrections: dict[str, Any] | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Apply reviewer corrections, re-validate, and mark approved.

        Approval with remaining *errors* is refused, so bad data can't be waved through.
        """
        doc = self.get(doc_id)
        data = {**(doc["data"] or {}), **(corrections or {})}
        model, issues = validate.parse(DocType(doc["doc_type"]), data)
        if model is not None:
            issues += validate.check(model)
        if (
            model is not None
            and doc["doc_type"] == "invoice"
            and self.is_duplicate(
                getattr(model, "vendor_name", None),
                getattr(model, "invoice_number", None),
                ("auto_approved", "approved"),
                exclude_id=doc_id,
            )
        ):
            issues.append(Issue(field="invoice_number", message="already approved (duplicate)"))
        errors = [i for i in issues if i.severity == "error"]
        if errors:
            raise ValueError(
                "cannot approve: " + "; ".join(f"{i.field}: {i.message}" for i in errors)
            )
        final = model.model_dump(mode="json") if model else data
        self.con.execute(
            "UPDATE documents SET status='approved', data=?, issues=?, reviewed_at=?, reviewer=?,"
            " note=?, vendor=?, doc_number=? WHERE id=?",
            (
                json.dumps(final),
                json.dumps([i.model_dump() for i in issues]),
                _now(),
                reviewer,
                note,
                final.get("vendor_name") or final.get("merchant"),
                final.get("invoice_number"),
                doc_id,
            ),
        )
        self.con.commit()
        return self.get(doc_id)

    def reject(self, doc_id: int, reviewer: str, note: str) -> dict[str, Any]:
        self.get(doc_id)
        self.con.execute(
            "UPDATE documents SET status='rejected', reviewed_at=?, reviewer=?, note=? WHERE id=?",
            (_now(), reviewer, note, doc_id),
        )
        self.con.commit()
        return self.get(doc_id)

    def stats(self) -> dict[str, int]:
        rows = self.con.execute("SELECT status, COUNT(*) n FROM documents GROUP BY status")
        return {r["status"]: r["n"] for r in rows}


__all__ = ["ReviewQueue", "Issue"]
