"""REST API. Run: uvicorn docflow.api:app --reload"""

from __future__ import annotations

import os
import secrets
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from pydantic import BaseModel

from docflow import __version__
from docflow.config import get_settings
from docflow.pipeline import Pipeline
from docflow.review import ReviewQueue


def check_token(x_api_key: str = Header(default="")) -> None:
    """When DOCFLOW_API_TOKEN is set, every request must send it as X-API-Key."""
    token = os.environ.get("DOCFLOW_API_TOKEN")
    if token and not secrets.compare_digest(x_api_key, token):
        raise HTTPException(401, "missing or wrong X-API-Key")


app = FastAPI(
    title="docflow-agent",
    version=__version__,
    description="Turn documents into validated, structured data.",
    dependencies=[Depends(check_token)],
)
_settings = get_settings()
queue = ReviewQueue(_settings.db_path)
pipeline = Pipeline(queue=queue, settings=_settings)


class Decision(BaseModel):
    reviewer: str
    corrections: dict[str, Any] | None = None
    note: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "extractor": pipeline.extractor.name, "queue": queue.stats()}


@app.post("/documents")
async def upload(file: UploadFile) -> list[dict[str, Any]]:
    data = await file.read()
    try:
        results = pipeline.process_path(file.filename or "upload.pdf", data)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return [r.model_dump(mode="json") for r in results]


@app.get("/documents")
def documents(status: str | None = None) -> list[dict[str, Any]]:
    return queue.list(status)


@app.post("/documents/{doc_id}/approve")
def approve(doc_id: int, d: Decision) -> dict[str, Any]:
    try:
        return queue.approve(doc_id, d.reviewer, d.corrections, d.note)
    except KeyError as e:
        raise HTTPException(404, "not found") from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/documents/{doc_id}/reject")
def reject(doc_id: int, d: Decision) -> dict[str, Any]:
    try:
        return queue.reject(doc_id, d.reviewer, d.note or "rejected")
    except KeyError as e:
        raise HTTPException(404, "not found") from e
