"""compose.yaml is the single source of every container image pin the
tests use (ADR 0014). This pins the loader so a renamed compose service
fails in `just test`, not only in the integration tier."""

import re

from tests.compose_images import (
    DOCKERFILE,
    DOCKERFILE_MIGRATIONS,
    compose_image,
    dockerfile_arg_default,
    dockerfile_base_image,
    dockerfile_stage_image,
)


def test_every_pinned_service_has_an_explicit_tag() -> None:
    for service in (
        "postgres",
        "redis",
        "minio",
        "lgtm",
        "trivy",
        "payment-stub",
    ):
        image = compose_image(service)
        assert ":" in image, image
        assert not image.endswith(":latest"), image


def test_the_builder_and_the_runtime_run_the_same_python_minor() -> None:
    """The builder makes the virtual environment and the runtime runs it,
    and a virtual environment works only with the Python minor version that
    made it: under any other, every import of a dependency fails. Dependabot
    can bump the runtime's `python:` tag but not the version inside the uv
    tag, so this fails until both name the same version."""
    builder = dockerfile_stage_image("builder", DOCKERFILE)
    runtime = dockerfile_stage_image("runtime", DOCKERFILE)
    builder_python = re.search(r"-python(\d+\.\d+)-", builder)
    runtime_python = re.fullmatch(r"python:(\d+\.\d+)-.+", runtime)
    assert builder_python, builder
    assert runtime_python, runtime
    assert builder_python.group(1) == runtime_python.group(1), (builder, runtime)


def test_the_migrations_base_image_is_the_dockerfile_from_line() -> None:
    assert dockerfile_base_image().startswith("migrate/migrate:v")


def test_the_migrate_source_version_is_the_upstream_image_tag() -> None:
    """Dependabot bumps the `upstream` tag and cannot bump the ARG. This
    fails until both name the same release, so the binary is never built
    from a different version than the image it replaces."""
    upstream = dockerfile_stage_image("upstream", DOCKERFILE_MIGRATIONS)
    upstream_tag = upstream.split(":", 1)[1]
    assert dockerfile_arg_default("MIGRATE_VERSION") == upstream_tag


def test_the_go_builder_is_an_exact_release_pinned_by_digest() -> None:
    """A floating `golang:1.26` would make the same Dockerfile build a
    different toolchain next month. Tag and digest, both."""
    builder = dockerfile_stage_image("build", DOCKERFILE_MIGRATIONS)
    assert re.fullmatch(
        r"golang:\d+\.\d+\.\d+-alpine[\d.]+@sha256:[0-9a-f]{64}", builder
    ), builder
