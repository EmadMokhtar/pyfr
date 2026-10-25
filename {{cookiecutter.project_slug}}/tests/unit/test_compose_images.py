"""compose.yaml is the single source of every container image pin the
tests use (ADR 0014). This pins the loader so a renamed compose service
fails in `just test`, not only in the integration tier."""
{%- if cookiecutter.database == "postgres" %}

import re

from tests.compose_images import (
    compose_image,
    dockerfile_arg_default,
    dockerfile_base_image,
    dockerfile_stage_image,
)
{%- else %}

from tests.compose_images import compose_image
{%- endif %}


def test_every_pinned_service_has_an_explicit_tag() -> None:
    for service in (
{%- if cookiecutter.database == "postgres" %}
        "postgres",
{%- endif %}
{%- if cookiecutter.cache == "redis" %}
        "redis",
{%- endif %}
{%- if cookiecutter.object_storage == "s3" %}
        "minio",
{%- endif %}
        "lgtm",
        "trivy",
        "payment-stub",
    ):
        image = compose_image(service)
        assert ":" in image, image
        assert not image.endswith(":latest"), image
{%- if cookiecutter.database == "postgres" %}


def test_the_migrations_base_image_is_the_dockerfile_from_line() -> None:
    assert dockerfile_base_image().startswith("migrate/migrate:v")


def test_the_migrate_source_version_is_the_upstream_image_tag() -> None:
    """Dependabot bumps the `upstream` tag and cannot bump the ARG. This
    fails until both name the same release, so the binary is never built
    from a different version than the image it replaces."""
    upstream_tag = dockerfile_stage_image("upstream").split(":", 1)[1]
    assert dockerfile_arg_default("MIGRATE_VERSION") == upstream_tag


def test_the_go_builder_is_an_exact_release_pinned_by_digest() -> None:
    """A floating `golang:1.26` would make the same Dockerfile build a
    different toolchain next month. Tag and digest, both."""
    builder = dockerfile_stage_image("build")
    assert re.fullmatch(
        r"golang:\d+\.\d+\.\d+-alpine[\d.]+@sha256:[0-9a-f]{64}", builder
    ), builder
{%- endif %}
