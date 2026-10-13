"""ingest -> classify -> extract -> validate -> score -> route (auto-approve or review)."""

from __future__ import annotations

from pathlib import Path

from docflow import validate
from docflow.classify import classify
from docflow.config import Settings, get_settings
from docflow.extractors import Extractor, get_extractor
from docflow.ingest import Document, load
from docflow.review import ReviewQueue
from docflow.schemas import DocType, Issue, Result


class Pipeline:
    def __init__(
        self,
        extractor: Extractor | None = None,
        queue: ReviewQueue | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.extractor = extractor or get_extractor(settings=self.settings)
        self.queue = queue

    def process_document(self, doc: Document) -> Result:
        doc_type = classify(doc.text)
        base = Result(
            source=doc.source,
            doc_type=doc_type,
            extractor=self.extractor.name,
            text_chars=len(doc.text),
        )
        if not doc.text.strip():
            base.issues = [Issue(field="document", message="no text found (scanned? enable OCR)")]
            base.status = "failed"
            return base
        if doc_type is DocType.unknown:
            base.issues = [Issue(field="doc_type", message="could not determine document type")]
            return base
        try:
            raw = self.extractor.extract(doc.text, doc_type)
        except Exception as e:  # extractor/API failure goes to review, never crashes a batch
            base.issues = [Issue(field="extractor", message=f"{type(e).__name__}: {e}")]
            base.status = "failed"
            return base

        model, issues = validate.parse(doc_type, raw)
        if model is None:
            base.data = raw
            base.issues = issues
            return base
        issues += validate.check(model, self.settings.known_vendors)
        data = model.model_dump(mode="json")
        if (
            self.queue
            and doc_type is DocType.invoice
            and self.queue.is_duplicate(data.get("vendor_name"), data.get("invoice_number"))
        ):
            issues.append(Issue(field="invoice_number", message="duplicate of an existing invoice"))
        n_null = sum(v is None for v in data.values())
        base.data = data
        base.issues = issues
        base.confidence = validate.confidence(issues, n_null)
        has_error = any(i.severity == "error" for i in issues)
        base.status = (
            "auto_approved"
            if not has_error and base.confidence >= self.settings.review_threshold
            else "needs_review"
        )
        return base

    def process_path(self, path: str | Path, data: bytes | None = None) -> list[Result]:
        results = []
        for doc in load(path, data):
            r = self.process_document(doc)
            if self.queue is not None:
                self.queue.add(r)
            results.append(r)
        return results

    def process_dir(self, folder: str | Path) -> list[Result]:
        out: list[Result] = []
        for p in sorted(Path(folder).iterdir()):
            if p.suffix.lower() in {".pdf", ".eml", ".txt", ".png", ".jpg", ".jpeg"}:
                out += self.process_path(p)
        return out
