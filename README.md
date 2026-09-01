# PyFr

**A cookiecutter template for production-ready Python microservices.**

📖 **[Documentation](https://emadmokhtar.github.io/pyfr/)**

You answer a short list of prompts and receive a repository that runs, is
tested, is observable, and is documented. The target is a working service in
ten minutes, in place of the two to four weeks teams spend assembling the same
components by hand.

Generated code belongs entirely to your team. Nothing is published to a
package index, and a generated service imports no PyFr package. There is no
framework to upgrade — and, from M8, a generated project can still pull later
template fixes into itself through an ordinary git merge.

---

## Status: milestone M0 of 8

**The template itself does not exist yet.** What exists today is the
*reference service* in [`examples/reference-service/`](examples/reference-service/)
— the complete, running service the template will be built from.

PyFr is built in three phases. Phase A (M0–M6) builds that service as ordinary
Python with no template placeholders anywhere. Phase B (M7) converts it into
the template. Phase C keeps the two in step forever after. The rule behind the
order: never debug Jinja and Python at the same time.

M0 — the walking skeleton — is done. **PyFr becomes a usable template at M7.**
See the [roadmap](https://emadmokhtar.github.io/pyfr/roadmap/).

Until then you can run the reference service, read it, and copy from it.

## Try it

```bash
cd examples/reference-service && uv sync && just dev
```

Then open <http://localhost:8000/docs>.

The [getting started guide](https://emadmokhtar.github.io/pyfr/getting-started/)
walks through placing an order and explains what each response shows.

## What a generated service contains

All of this already runs in the reference service:

- **FastAPI** with an application factory and a lifespan.
- **Four layers** — domain, services, infrastructure, api — with the
  dependency rule enforced by a build check, not by code review.
- **Configuration validated at startup.** A bad value stops the process with a
  readable message and exit code 78, rather than causing a 500 an hour later.
- **Structured logging**: one JSON object per line on standard output, with
  third-party records passing through the same chain.
- **Three health endpoints** answering three different questions — liveness
  never checks a dependency, so a database hiccup cannot restart every
  instance at once.
- **RFC 9457 Problem Details** error responses.
- **Correlation identifiers** binding one value to every log line a request
  produced.
- **Graceful shutdown**, so a rolling deployment does not drop live requests.
- **A hardened container image**: non-root, no build tools, no shell utilities
  in the final layer, and reproducible installs from a lock file.

M1 through M6 add persistence, OpenTelemetry, contract testing, cache and
object storage, release automation, and supply-chain scanning.

## Documentation

| | |
| --- | --- |
| [Getting started](https://emadmokhtar.github.io/pyfr/getting-started/) | Run the reference service and place an order |
| [Add an endpoint](https://emadmokhtar.github.io/pyfr/guides/add-an-endpoint/) | Build a feature through all four layers |
| [Architecture](https://emadmokhtar.github.io/pyfr/explanation/architecture/) | How the pieces fit and why |
| [Configuration](https://emadmokhtar.github.io/pyfr/reference/configuration/) | Every environment variable |
| [Roadmap](https://emadmokhtar.github.io/pyfr/roadmap/) | What ships when |
| [Contributing](https://emadmokhtar.github.io/pyfr/contributing/) | Working on PyFr itself |

The design specification and milestone plans live in
[`docs/superpowers/`](docs/superpowers/). They are the reasoning behind the
decisions the site describes, and are deliberately not published.

## Development

The repository root and the reference service are two separate Python
projects, each with its own `pyproject.toml`. They are never synced together.

```bash
# The reference service
cd examples/reference-service && uv sync && just check
```

```bash
# The documentation site
just docs-install && just docs
```

Commit messages and pull request titles must follow
[Conventional Commits](https://www.conventionalcommits.org/). See
[Contributing](https://emadmokhtar.github.io/pyfr/contributing/).

## Credits

PyFr's architecture is influenced by [GoFr](https://gofr.dev), the Go
microservice framework — the context-driven layering and the emphasis on
developer experience, adapted to Python's ecosystem and to a template rather
than a library.

## License

[Mozilla Public License 2.0](LICENSE).
