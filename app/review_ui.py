"""Review UI. Run: streamlit run app/review_ui.py"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from docflow.config import get_settings
from docflow.exporters import to_csv
from docflow.pipeline import Pipeline
from docflow.review import ReviewQueue

st.set_page_config(page_title="docflow", page_icon="📄", layout="wide")
SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "docs"


@st.cache_resource
def services() -> tuple[ReviewQueue, Pipeline]:
    s = get_settings()
    q = ReviewQueue(s.db_path)
    return q, Pipeline(queue=q, settings=s)


queue, pipeline = services()

st.title("docflow")
st.caption(
    f"Document automation: extract → validate → review → export. Extractor: "
    f"**{pipeline.extractor.name}** · auto-approve threshold "
    f"{pipeline.settings.review_threshold:.2f}"
)

with st.sidebar:
    st.header("Add documents")
    files = st.file_uploader("PDF, email (.eml) or text", accept_multiple_files=True)
    if files and st.button("Process uploads", type="primary"):
        for f in files:
            pipeline.process_path(f.name, f.getvalue())
        st.rerun()
    if st.button("Process sample documents"):
        pipeline.process_dir(SAMPLES)
        st.rerun()

stats = queue.stats()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Auto-approved", stats.get("auto_approved", 0))
c2.metric("Needs review", stats.get("needs_review", 0))
c3.metric("Approved by reviewer", stats.get("approved", 0))
c4.metric("Rejected / failed", stats.get("rejected", 0) + stats.get("failed", 0))

tab_review, tab_all = st.tabs(["Review queue", "All documents"])

with tab_review:
    pending = queue.list("needs_review")
    if not pending:
        st.success("Nothing waiting for review.")
    for d in pending:
        with st.expander(
            f"#{d['id']} · {d['doc_type']} · {Path(d['source']).name} · "
            f"confidence {d['confidence']:.2f}",
            expanded=d is pending[0],
        ):
            for i in d["issues"]:
                (st.error if i["severity"] == "error" else st.warning)(
                    f"**{i['field']}**: {i['message']}"
                )
            data = d["data"] or {}
            scalars = {k: v for k, v in data.items() if not isinstance(v, list | dict)}
            edited = st.data_editor(
                pd.DataFrame({"field": list(scalars), "value": [str(v) for v in scalars.values()]}),
                key=f"edit_{d['id']}",
                hide_index=True,
                disabled=["field"],
                use_container_width=True,
            )
            items = data.get("line_items") or data.get("items")
            if items:
                st.dataframe(pd.DataFrame(items), hide_index=True, use_container_width=True)
            reviewer = st.text_input("Reviewer", "reviewer", key=f"who_{d['id']}")
            a, r = st.columns(2)
            if a.button("Approve with edits", key=f"ok_{d['id']}", type="primary"):
                changes = {}
                for f, v in zip(edited["field"], edited["value"], strict=True):
                    if str(scalars.get(f)) != v:
                        try:
                            changes[f] = json.loads(v)
                        except json.JSONDecodeError:
                            changes[f] = None if v in {"", "None"} else v
                try:
                    queue.approve(d["id"], reviewer, changes)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
            if r.button("Reject", key=f"no_{d['id']}"):
                queue.reject(d["id"], reviewer, "rejected in UI")
                st.rerun()

with tab_all:
    docs = queue.list()
    if docs:
        df = pd.DataFrame(
            [
                {
                    "id": d["id"],
                    "status": d["status"],
                    "type": d["doc_type"],
                    "source": Path(d["source"]).name,
                    "confidence": d["confidence"],
                    "vendor": d["vendor"],
                    "number": d["doc_number"],
                    "total": (d["data"] or {}).get("total"),
                    "issues": len(d["issues"]),
                }
                for d in docs
            ]
        )
        st.dataframe(df, hide_index=True, use_container_width=True)
        ok = [
            d
            for d in docs
            if d["status"] in {"auto_approved", "approved"} and d["doc_type"] == "invoice"
        ]
        if ok:
            path = to_csv(ok, Path(get_settings().db_path).parent / "approved_invoices.csv")
            st.download_button(
                "Download approved invoices (CSV)",
                path.read_bytes(),
                file_name="approved_invoices.csv",
            )
