"""Turn files into text. PDF, email (.eml with PDF attachments), plain text and images (OCR)."""

from __future__ import annotations

import email
import io
from dataclasses import dataclass
from email import policy
from pathlib import Path

from pypdf import PdfReader


@dataclass
class Document:
    source: str
    text: str


def pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def image_text(data: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:  # pragma: no cover - optional extra
        raise RuntimeError("OCR needs the 'ocr' extra: pip install 'docflow-agent[ocr]'") from e
    return str(pytesseract.image_to_string(Image.open(io.BytesIO(data))))


def email_documents(data: bytes, source: str) -> list[Document]:
    """One document per PDF/image attachment; the body itself if there are none."""
    msg = email.message_from_bytes(data, policy=policy.default)
    docs: list[Document] = []
    for part in msg.iter_attachments():
        name = part.get_filename() or "attachment"
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            continue
        ctype = part.get_content_type()
        if ctype == "application/pdf" or name.lower().endswith(".pdf"):
            docs.append(Document(f"{source}#{name}", pdf_text(payload)))
        elif ctype.startswith("image/"):
            try:
                docs.append(Document(f"{source}#{name}", image_text(payload)))
            except RuntimeError:  # no OCR installed: skip logos/signatures, keep the PDFs
                continue
    if not docs:
        body = msg.get_body(preferencelist=("plain", "html"))
        docs.append(Document(source, body.get_content() if body else ""))
    return docs


def load(path: str | Path, data: bytes | None = None) -> list[Document]:
    path = Path(path)
    data = data if data is not None else path.read_bytes()
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return [Document(str(path), pdf_text(data))]
    if suffix == ".eml":
        return email_documents(data, str(path))
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        return [Document(str(path), image_text(data))]
    if suffix in {".txt", ".md"}:
        return [Document(str(path), data.decode("utf-8", errors="replace"))]
    raise ValueError(f"unsupported file type: {suffix}")
