FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DOCFLOW_DB=/data/docflow.db
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
COPY pyproject.toml README.md LICENSE ./
COPY docflow ./docflow
RUN uv pip install --system --no-cache ".[app]"
COPY app ./app
COPY samples ./samples
VOLUME /data
EXPOSE 8000 8501
CMD ["uvicorn", "docflow.api:app", "--host", "0.0.0.0", "--port", "8000"]
