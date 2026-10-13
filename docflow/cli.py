"""docflow CLI.

docflow run samples/docs --export out/invoices.csv
docflow review list
docflow review approve 3 --reviewer alice --set total=1234.50
"""

from __future__ import annotations

import argparse
import json
import sys

from docflow.config import get_settings
from docflow.exporters import to_csv, to_webhook
from docflow.pipeline import Pipeline
from docflow.review import ReviewQueue


def _parse_value(v: str) -> object:
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="docflow")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="process a file or folder")
    run.add_argument("path")
    run.add_argument("--extractor", default=None, help="auto | anthropic | openai | rules")
    run.add_argument("--export", help="CSV path for auto-approved results")
    run.add_argument("--webhook", help="POST auto-approved results to this URL")
    rv = sub.add_parser("review", help="work the review queue")
    rv.add_argument("action", choices=["list", "approve", "reject", "stats"])
    rv.add_argument("id", nargs="?", type=int)
    rv.add_argument("--reviewer", default="reviewer")
    rv.add_argument("--set", action="append", default=[], help="field=value correction")
    rv.add_argument("--note", default="")
    a = p.parse_args(argv)

    s = get_settings()
    queue = ReviewQueue(s.db_path)
    if a.cmd == "run":
        from pathlib import Path

        from docflow.extractors import get_extractor

        pipe = Pipeline(get_extractor(a.extractor, s), queue, s)
        target = Path(a.path)
        results = pipe.process_dir(target) if target.is_dir() else pipe.process_path(target)
        for r in results:
            flag = {"auto_approved": "OK    ", "needs_review": "REVIEW", "failed": "FAILED"}[
                r.status
            ]
            print(f"{flag} {r.confidence:4.2f}  {r.doc_type.value:<8} {r.source}")
            for i in r.issues:
                print(f"         - [{i.severity}] {i.field}: {i.message}")
        ok = [r.model_dump(mode="json") for r in results if r.status == "auto_approved"]
        if a.export:
            print(f"exported {len(ok)} rows to {to_csv(ok, a.export)}")
        if a.webhook:
            print(f"posted {to_webhook(ok, a.webhook)} records")
        return 0

    if a.action == "stats":
        print(json.dumps(queue.stats(), indent=2))
    elif a.action == "list":
        for d in queue.list("needs_review"):
            print(f"#{d['id']:<4} {d['confidence']:4.2f} {d['doc_type']:<8} {d['source']}")
            for i in d["issues"]:
                print(f"       - {i['field']}: {i['message']}")
    elif a.id is None:
        print("an id is required", file=sys.stderr)
        return 2
    elif a.action == "approve":
        corrections = {k: _parse_value(v) for k, v in (x.split("=", 1) for x in a.set)}
        try:
            queue.approve(a.id, a.reviewer, corrections, a.note or None)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        print(f"approved #{a.id}")
    else:
        queue.reject(a.id, a.reviewer, a.note or "rejected")
        print(f"rejected #{a.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
