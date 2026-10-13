"""Field-level accuracy against ground truth in samples/truth.

python evals/run_eval.py --extractor rules       # offline baseline
python evals/run_eval.py --extractor anthropic   # needs ANTHROPIC_API_KEY + DOCFLOW_MODEL
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from docflow.config import Settings  # noqa: E402
from docflow.extractors import get_extractor  # noqa: E402
from docflow.ingest import load  # noqa: E402
from docflow.pipeline import Pipeline  # noqa: E402

FIELDS = {
    "invoice": [
        "invoice_number",
        "vendor_name",
        "po_number",
        "issue_date",
        "due_date",
        "subtotal",
        "tax",
        "total",
    ],
    "receipt": ["merchant", "date", "subtotal", "tax", "total"],
    "contract": [
        "parties",
        "effective_date",
        "end_date",
        "auto_renewal",
        "notice_period_days",
        "governing_law",
        "payment_terms",
    ],
}


def _eq(a: object, b: object) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) < 0.01  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
    if isinstance(a, list) and isinstance(b, list):
        return sorted(map(str, a)) == sorted(map(str, b))
    return a == b


def run(extractor: str) -> dict:
    settings = Settings(review_threshold=0.85)
    pipe = Pipeline(get_extractor(extractor, settings), None, settings)
    rows, correct, total, routed_ok = [], 0, 0, 0
    truths = sorted((ROOT / "samples" / "truth").glob("*.json"))
    for tf in truths:
        truth = json.loads(tf.read_text())
        doc = load(ROOT / "samples" / "docs" / f"{tf.stem}.pdf")[0]
        res = pipe.process_document(doc)
        got = res.data or {}
        fields = FIELDS[truth["doc_type"]]
        hits = {f: _eq(got.get(f), truth["data"].get(f)) for f in fields}
        if truth["doc_type"] == "invoice":
            hits["line_items"] = len(got.get("line_items") or []) == len(
                truth["data"]["line_items"]
            )
        correct += sum(hits.values())
        total += len(hits)
        routed = (res.status != "auto_approved") == truth["expect_review"]
        routed_ok += routed
        rows.append(
            {
                "doc": tf.stem,
                "type_ok": res.doc_type.value == truth["doc_type"],
                "fields": f"{sum(hits.values())}/{len(hits)}",
                "status": res.status,
                "routing_ok": routed,
                "missed": [f for f, ok in hits.items() if not ok],
            }
        )
    summary = {
        "extractor": extractor,
        "documents": len(rows),
        "field_accuracy": round(correct / total, 4),
        "routing_accuracy": round(routed_ok / len(rows), 4),
        "doc_type_accuracy": round(sum(r["type_ok"] for r in rows) / len(rows), 4),
    }
    return {"summary": summary, "rows": rows}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--extractor", default="rules")
    p.add_argument("--min-field-accuracy", type=float, default=0.0)
    a = p.parse_args()
    out = run(a.extractor)
    for r in out["rows"]:
        print(
            f"{r['doc']:<12} fields {r['fields']:<6} {r['status']:<14} "
            f"{'' if r['routing_ok'] else 'ROUTING MISS '}{r['missed'] or ''}"
        )
    print(json.dumps(out["summary"], indent=2))
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / f"eval_{a.extractor}.json").write_text(json.dumps(out, indent=2))
    return 0 if out["summary"]["field_accuracy"] >= a.min_field_accuracy else 1


if __name__ == "__main__":
    sys.exit(main())
