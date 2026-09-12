# Builder: uv resolves and installs into a virtual environment we copy out.
# Debian trixie, not bookworm: astral-sh no longer publishes a
# bookworm-slim variant for the 0.11 line. The runtime stage below must
# stay on the same Debian release — a virtual environment built against
# one glibc is not safe to run on an older one.
FROM ghcr.io/astral-sh/uv:0.12-python3.14-trixie-slim AS builder

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
FROM python:3.14-slim-trixie AS runtime

# Apply Debian's security updates at build time. The official python:slim
# tag is rebuilt on Python's schedule, not Debian's, so it lags the
# security archive by days or weeks: the first CI run of the scan gate
# found twelve fixed HIGH and CRITICAL findings (perl-base, gzip, libpcre2,
# libsqlite3) in a base whose fixes had already shipped in Debian 13.7,
# while the same base scanned clean a day earlier against an older
# vulnerability database. `apt-get upgrade` installs exactly the fixed
# versions the scan names, so the image is as current as Debian's archive
# on the day it is built rather than the day the base tag was cut. The
# package lists are removed afterwards so they do not ship in the image.
# The cost is that two builds days apart can differ in Debian package
# versions; the SBOM records which versions a given image carries.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

# pip is not used at runtime -- the virtual environment copied in below
# was built by uv -- and the copy the base image ships is the ONLY source
# of vulnerability findings in this image: its vendored msgpack
# (GHSA-6v7p-g79w-8964) and pkg_resources (CVE-2025-47273) are both HIGH,
# both fixed upstream, and both unreachable from anything this service
# runs (M6 plan, Verified Fact 5). Removing pip removes the findings, and
# a tool nobody should run inside a production container. The interpreter
# is named by its full path on purpose: /app/.venv/bin goes first on PATH
# below, and the venv's own python has no pip to uninstall.
RUN /usr/local/bin/python -m pip uninstall -y pip

# What links a pushed image to this repository on GHCR, so the package
# inherits the repository's visibility and README. Version and revision
# are stamped at publish time (`just publish-images`); they are not known
# here. Becomes a template variable in M7.
LABEL org.opencontainers.image.source="https://github.com/EmadMokhtar/pyfr"

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
# Reads APP_HTTP_PORT the same way the CMD below does, so the two cannot
# drift out of sync if the port is overridden at runtime.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request,sys; port = os.environ.get('APP_HTTP_PORT', '8000'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=2).status == 200 else 1)"]

# Shell form with an explicit `exec`, not exec-form CMD with a literal
# --port: APP_HTTP_PORT is a runtime setting (see settings.py), so it is
# not known at build time and must be expanded by a shell. `exec` replaces
# that shell with uvicorn rather than running it as a child, so uvicorn
# stays PID 1 and still receives SIGTERM directly — the graceful-shutdown
# behaviour below is unchanged.
#
# --no-access-log: our own middleware emits the structured access record.
# --timeout-graceful-shutdown: finish in-flight requests on SIGTERM, then stop.
CMD ["sh", "-c", "exec uvicorn reference_service.main:create_app --factory --host 0.0.0.0 --port \"${APP_HTTP_PORT:-8000}\" --no-access-log --timeout-graceful-shutdown 30"]
