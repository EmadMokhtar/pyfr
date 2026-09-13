"""compose.yaml is the single source of every container image pin the
tests use (ADR 0014). This pins the loader so a renamed compose service
fails in `just test`, not only in the integration tier."""

from tests.compose_images import compose_image, dockerfile_base_image


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


def test_the_migrations_base_image_is_the_dockerfile_from_line() -> None:
    assert dockerfile_base_image().startswith("migrate/migrate:v")
