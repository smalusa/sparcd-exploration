FROM python:3.12-slim

WORKDIR /app

ENV PORT=8080 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.7.13 /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY assets ./assets
COPY notebooks ./notebooks

EXPOSE 8080

CMD ["sh", "-c", "uv run marimo run notebooks/hello.py --host 0.0.0.0 --port ${PORT:-8080} --no-token --headless"]
