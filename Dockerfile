FROM ghcr.io/astral-sh/uv:0.9.2 AS uv
FROM python:3.13-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
RUN groupadd --gid 10001 opsmind && useradd --uid 10001 --gid opsmind --create-home opsmind
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
COPY knowledge ./knowledge
RUN mkdir -p /app/.cache/embeddings /app/.data/chroma && chown -R opsmind:opsmind /app/.cache /app/.data
ENV PATH="/app/.venv/bin:$PATH"
USER opsmind
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "opsmind.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
