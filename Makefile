PY ?= .venv/bin/python

.PHONY: setup samples test lint eval eval-llm api ui docker

setup:
	uv venv --allow-existing .venv
	uv pip install --python $(PY) -e ".[app,dev]"

samples:          ## regenerate the synthetic sample documents
	$(PY) samples/generate.py

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .
	$(PY) -m mypy

eval:             ## offline baseline (rules extractor)
	$(PY) evals/run_eval.py --extractor rules --min-field-accuracy 0.95

eval-llm:         ## LLM extractor (needs ANTHROPIC_API_KEY and DOCFLOW_MODEL)
	$(PY) evals/run_eval.py --extractor anthropic

api:
	$(PY) -m uvicorn docflow.api:app --reload --port 8000

ui:
	$(PY) -m streamlit run app/review_ui.py

docker:
	docker build -t docflow-agent .
