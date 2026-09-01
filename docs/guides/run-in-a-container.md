# Run in a container

```bash
just up
```

That builds the image and starts the stack, serving on
<http://localhost:8000>. Stop it with `just down`, which also removes the
volumes.

Run these from `examples/reference-service/`.

## What the image is

A two-stage build. The first stage resolves and installs dependencies into a
virtual environment. The second copies that environment into a clean base
image and adds nothing else.

The result has **no `uv`, no compiler, no build tools, and no shell utilities
beyond the base image**. Every tool absent from the final layer is a tool an
attacker cannot use if they get code execution.

Other properties worth knowing:

- **Runs as a non-root user** (`app`), created in the image.
- **`uv sync --locked`** — installs exactly the versions in `uv.lock`, and
  *fails* if the lock file is out of date with `pyproject.toml`, rather than
  quietly resolving something new. Builds are reproducible.
- **Dependencies are installed before the source is copied**, so editing a
  Python file does not re-resolve the dependency tree.

!!! warning "Both stages must stay on the same Debian release"

    The builder is `uv:0.11-python3.13-trixie-slim` and the runtime is
    `python:3.13-slim-trixie`. Both are Debian trixie, and that is load-bearing:
    a virtual environment built against one version of the C library is not
    safe to run on an older one. If you change one base image, change both.

## The health check

The image declares its own health check. There is no `curl` in the final
image — that is the point of a minimal image — so the check uses the Python
interpreter that is already there, and reads `APP_HTTP_PORT` exactly as the
start command does.

`compose.yaml` deliberately does **not** repeat it. Compose applies the
image's own health check automatically, and a duplicate here would hardcode
the port, drifting from the real one the moment `APP_HTTP_PORT` is overridden.

## The shutdown deadline trap

This one is worth understanding before you deploy to Kubernetes, because it is
silent when you get it wrong.

The container starts uvicorn with `--timeout-graceful-shutdown 30`. On the
shutdown signal, uvicorn stops accepting new connections and lets in-flight
requests finish, for up to 30 seconds.

**That 30 seconds is only a promise if whatever is running the container waits
longer than 30 seconds before killing it.** Otherwise requests still running
when the deadline hits are killed, not drained, no matter what uvicorn was
told.

Docker Compose's own default is 10 seconds — well under uvicorn's 30. So
`compose.yaml` sets it explicitly:

```yaml
stop_grace_period: 40s
```

**Kubernetes has the identical mismatch and needs the identical fix**:
`terminationGracePeriodSeconds` on the pod specification, set comfortably above
uvicorn's own deadline.

This is easy to miss precisely because Kubernetes' default (30 seconds)
*equals* uvicorn's deadline here. It does not look wrong. But equal leaves no
margin at all: the two deadlines expire together, so the shutdown uvicorn was
promised time for is cut off exactly as it begins.

Set it to 40 or more, the same way Compose does.

## Configuration

Pass environment variables as normal. `compose.yaml` sets the environment to
`production`, which switches logs from colourised text to one JSON object per
line.

```yaml
environment:
  APP_ENVIRONMENT: production
  APP_LOG__LEVEL: info
```

Every variable is listed in [Configuration](../reference/configuration.md).
A bad value stops the container at startup with exit code 78 and a readable
message, rather than serving broken traffic.

## Reading the logs

```bash
docker compose logs -f app
```

In `production` that is one JSON object per line. To read it as a person,
pipe it through [`jq`](https://jqlang.github.io/jq/):

```bash
docker compose logs -f app | jq -r '"\(.timestamp) \(.level) \(.event)"'
```

Health-check requests produce no access-log records, so this stays readable
rather than filling with probe traffic. See [Logging](../reference/logging.md).
