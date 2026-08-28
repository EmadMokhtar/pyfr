# Builder: uv resolves and installs into a virtual environment we copy out.
# Debian trixie, not bookworm: astral-sh no longer publishes a
# bookworm-slim variant for the 0.11 line. The runtime stage below must
# stay on the same Debian release — a virtual environment built against
# one glibc is not safe to run on an older one.
FROM ghcr.io/astral-sh/uv:0.11-python3.13-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Dependencies first, so a source change does not re-resolve them.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Runtime: no uv, no build tools, no shell utilities beyond the base image.
# Must match the builder's Debian release; see the note above.
FROM python:3.13-slim-trixie AS runtime

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app
EXPOSE 8000
STOPSIGNAL SIGTERM

# No curl in this image, so the health check uses the interpreter we have.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]

# --no-access-log: our own middleware emits the structured access record.
# --timeout-graceful-shutdown: finish in-flight requests on SIGTERM, then stop.
CMD ["uvicorn", "reference_service.main:create_app", \
     "--factory", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--no-access-log", \
     "--timeout-graceful-shutdown", "30"]
