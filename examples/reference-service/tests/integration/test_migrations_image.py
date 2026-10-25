"""The migrations image that ships: the binary in it is the one we built.

`migrated_database` and the schema gates already run `migrate` from this
image against a real PostgreSQL, so a binary without the `postgres` driver
or one that cannot connect fails them. These tests pin what they cannot see:
which release the binary is.
"""

from __future__ import annotations

from testcontainers.core.container import DockerContainer

from tests.compose_images import dockerfile_arg_default


def test_the_image_binary_is_the_release_the_dockerfile_names(
    migrations_image: str,
) -> None:
    container = DockerContainer(migrations_image).with_command("-version")
    container.start()
    try:
        raw = container.get_wrapped_container()
        exit_code = int(raw.wait()["StatusCode"])
        logs = raw.logs().decode().strip()
    finally:
        container.stop()

    assert exit_code == 0, logs
    assert logs == dockerfile_arg_default("MIGRATE_VERSION").removeprefix("v")
