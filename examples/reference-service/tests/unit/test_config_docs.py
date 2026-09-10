"""The settings walker, which turns the model into documentable variables.

These tests pin the four introspection traps the plan records as Verified
Facts 2 to 5. Each one, got wrong, produces documentation that is confidently
incorrect rather than obviously broken -- which is the worse failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ is not an installed package; the generator is a build tool that
# lives beside the code it reads.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from generate_config_docs import ConfigGroup, ConfigVariable, walk_settings


@pytest.fixture(scope="module")
def groups() -> list[ConfigGroup]:
    return walk_settings()


@pytest.fixture(scope="module")
def by_name(groups: list[ConfigGroup]) -> dict[str, ConfigVariable]:
    return {variable.name: variable for group in groups for variable in group.variables}


def test_walks_every_environment_variable(by_name: dict[str, ConfigVariable]) -> None:
    """38 variables across 8 models -- see the plan's Verified Fact 6."""
    assert len(by_name) == 38


def test_top_level_fields_carry_no_group_prefix(
    by_name: dict[str, ConfigVariable],
) -> None:
    assert "APP_ENVIRONMENT" in by_name
    assert "APP_SERVICE_NAME" in by_name
    assert "APP_HTTP_PORT" in by_name


def test_nested_models_use_the_double_underscore_delimiter(
    by_name: dict[str, ConfigVariable],
) -> None:
    assert "APP_LOG__LEVEL" in by_name
    assert "APP_CACHE__TTL_SECONDS" in by_name


def test_doubly_nested_models_repeat_the_delimiter(
    by_name: dict[str, ConfigVariable],
) -> None:
    """PaymentSettings.http is the only double nesting in the model."""
    assert "APP_PAYMENT__HTTP__CONNECT_TIMEOUT_SECONDS" in by_name


def test_optional_submodels_are_unwrapped_not_skipped(
    by_name: dict[str, ConfigVariable],
) -> None:
    """Verified Fact 4: `DatabaseSettings | None` must be recursed into.

    A walker that only recurses into bare BaseModel annotations silently
    documents 10 variables instead of 38.
    """
    assert "APP_DATABASE__DSN" in by_name
    assert "APP_STORAGE__BUCKET" in by_name


def test_default_factory_fields_do_not_leak_the_undefined_sentinel(
    by_name: dict[str, ConfigVariable],
) -> None:
    """Verified Fact 2: `.default` is PydanticUndefined when a factory is set."""
    levels = by_name["APP_LOG__LEVELS"]
    assert "PydanticUndefined" not in levels.default_label
    assert levels.default_label == "{}"


def test_secret_fields_are_flagged(by_name: dict[str, ConfigVariable]) -> None:
    assert by_name["APP_STORAGE__ACCESS_KEY_ID"].secret is True
    assert by_name["APP_STORAGE__SECRET_ACCESS_KEY"].secret is True


def test_secret_inside_a_union_is_flagged(by_name: dict[str, ConfigVariable]) -> None:
    """Verified Fact 3: `SecretStr | None` fails an identity check.

    Getting this wrong publishes the payment API key as an ordinary string
    field, which is precisely what the SecretStr annotation exists to prevent.
    """
    assert by_name["APP_PAYMENT__API_KEY"].secret is True


def test_ordinary_fields_are_not_flagged_as_secret(
    by_name: dict[str, ConfigVariable],
) -> None:
    assert by_name["APP_SERVICE_NAME"].secret is False


def test_constraints_reach_the_type_label(by_name: dict[str, ConfigVariable]) -> None:
    """Verified Fact 5: annotated_types objects in FieldInfo.metadata."""
    assert by_name["APP_CACHE__POOL_SIZE"].type_label == "integer, ≥ 1"
    assert by_name["APP_CACHE__TTL_SECONDS"].type_label == "integer, ≥ 1"
    assert by_name["APP_CACHE__CONNECT_TIMEOUT_SECONDS"].type_label == "float, > 0"


def test_bounded_integers_render_as_a_range(by_name: dict[str, ConfigVariable]) -> None:
    assert by_name["APP_HTTP_PORT"].type_label == "integer, 1–65535"


def test_literals_render_as_alternatives(by_name: dict[str, ConfigVariable]) -> None:
    assert by_name["APP_ENVIRONMENT"].type_label == "`local` | `staging` | `production`"


def test_network_types_render_by_name(by_name: dict[str, ConfigVariable]) -> None:
    assert by_name["APP_DATABASE__DSN"].type_label == "PostgreSQL URL"
    assert by_name["APP_CACHE__DSN"].type_label == "Redis URL"
    assert by_name["APP_PAYMENT__BASE_URL"].type_label == "URL"


def test_secret_type_label_says_secret(by_name: dict[str, ConfigVariable]) -> None:
    assert by_name["APP_STORAGE__ACCESS_KEY_ID"].type_label == "secret"


def test_required_field_in_an_optional_group_is_marked(
    by_name: dict[str, ConfigVariable],
) -> None:
    """The rule the hand-written table states for every APP_STORAGE__ field."""
    assert by_name["APP_STORAGE__BUCKET"].required_in_group is True
    assert by_name["APP_STORAGE__REGION"].required_in_group is False


def test_optional_groups_are_marked_optional(groups: list[ConfigGroup]) -> None:
    by_path = {group.path: group for group in groups}
    assert by_path[("storage",)].optional is True
    assert by_path[("database",)].optional is True
    assert by_path[("log",)].optional is False


def test_groups_are_returned_in_declaration_order(
    groups: list[ConfigGroup],
) -> None:
    """Rendering order is model order, so the diff of a regeneration is small."""
    assert [group.path for group in groups] == [
        (),
        ("log",),
        ("otel",),
        ("database",),
        ("payment",),
        ("payment", "http"),
        ("cache",),
        ("storage",),
    ]
