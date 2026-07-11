# syntax=docker/dockerfile:1
FROM python:3.12-slim

# uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first for layer caching. README is needed because
# pyproject declares `readme = "README.md"` and the install builds the package.
COPY pyproject.toml README.md ./
RUN uv pip install --system --no-cache ".[dev]" || uv pip install --system --no-cache "."

COPY . .
RUN uv pip install --system --no-cache -e "."

EXPOSE 8000
CMD ["uvicorn", "juggle.main:app", "--host", "0.0.0.0", "--port", "8000"]
