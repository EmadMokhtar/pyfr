"""The settings walker, which turns the model into documentable variables.

These tests pin the four introspection traps the plan records as Verified
Facts 2 to 5. Each one, got wrong, produces documentation that is confidently
incorrect rather than obviously broken -- which is the worse failure.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Annotated

import pytest
from pydantic import BaseModel, Field

from {{ cookiecutter.package_name }}.observability.redaction import DEFAULT_REDACT_FIELDS

# scripts/ is not an installed package; the generator is a build tool that
# lives beside the code it reads.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from generate_config_docs import (
    CONFIGURATION_DOC,
    MARKER_BEGIN,
    MARKER_END,
    ConfigGroup,
    ConfigVariable,
    _render_type,
    check_outputs,
    render_env_example,
    render_markdown_table,
    walk_settings,
)


@pytest.fixture(scope="module")
def groups() -> list[ConfigGroup]:
    return walk_settings()


@pytest.fixture(scope="module")
def by_name(groups: list[ConfigGroup]) -> dict[str, ConfigVariable]:
    return {variable.name: variable for group in groups for variable in group.variables}


def test_walks_every_environment_variable(by_name: dict[str, ConfigVariable]) -> None:
    """39 variables across 8 models -- see the plan's Verified Fact 6.

    38 before Task 2 added `APP_LOG__REDACT_FIELDS`.
    """
    assert len(by_name) == 39


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


# No field on the real Settings model uses Le alone or Gt combined with Le
# today -- these are throwaway models built only to exercise those two
# shapes, rather than waiting for a real field to happen to need one.


class _UpperBoundOnly(BaseModel):
    x: Annotated[float, Field(le=100.0)]


class _ExclusiveLowerAndUpperBound(BaseModel):
    x: Annotated[float, Field(gt=0.0, le=100.0)]


def test_an_upper_bound_alone_is_not_dropped() -> None:
    """`Le` with no `Ge`/`Gt` used to fall through to the bare base label,
    rendering a field capped at 100 as plain "float" -- no bound at all.
    """
    info = _UpperBoundOnly.model_fields["x"]
    assert _render_type(info) == "float, ≤ 100.0"


def test_an_exclusive_lower_bound_with_an_upper_bound_keeps_both() -> None:
    """`Gt` combined with `Le` used to render only the lower bound
    ("float, > 0"), silently dropping the upper one -- the specific
    confidently-wrong-output shape this generator exists to eliminate.
    """
    info = _ExclusiveLowerAndUpperBound.model_fields["x"]
    assert _render_type(info) == "float, > 0.0, ≤ 100.0"


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


def test_every_variable_has_a_description(by_name: dict[str, ConfigVariable]) -> None:
    """A new setting must not be able to arrive undocumented.

    This is the gate that makes `Field(description=...)` the single source
    of truth rather than a convention people remember unevenly. Without it,
    the generated table quietly grows a row with an empty Meaning column.
    """
    undocumented = sorted(
        name for name, variable in by_name.items() if not variable.description.strip()
    )
    assert undocumented == [], (
        f"{len(undocumented)} setting(s) have no Field(description=...): {undocumented}"
    )


def test_every_group_has_a_docstring(groups: list[ConfigGroup]) -> None:
    """Group docstrings become the section headers in .env.example."""
    undocumented = sorted(
        "".join(group.path) or "Settings" for group in groups if not group.doc
    )
    assert undocumented == []


def test_no_secret_field_has_a_default(by_name: dict[str, ConfigVariable]) -> None:
    """A credential with a default is a credential committed to the repository.

    The generator prints defaults into two published files. Today no secret
    has one; this asserts it rather than trusting it, because the day one
    does, the leak is silent and permanent.
    """
    leaked = sorted(
        name
        for name, variable in by_name.items()
        if variable.secret and variable.default_label != "unset"
    )
    assert leaked == []


def test_markdown_table_has_a_header_and_one_row_per_variable() -> None:
    table = render_markdown_table()
    lines = [line for line in table.splitlines() if line.startswith("|")]
    # header + separator + 39 rows
    assert len(lines) == 41
    assert lines[0].startswith("| Variable |")


def test_markdown_rows_carry_the_variable_type_and_default() -> None:
    row = next(
        line
        for line in render_markdown_table().splitlines()
        if line.startswith("| `APP_CACHE__TTL_SECONDS`")
    )
    assert "integer, ≥ 1" in row
    assert "`300`" in row


def test_markdown_never_emits_a_raw_newline_inside_a_row() -> None:
    """A description with a line break silently breaks the table.

    Descriptions are written as wrapped Python strings; if one ever gains a
    literal newline, the row after it renders as body text and the table
    ends early -- with no error anywhere.
    """
    for line in render_markdown_table().splitlines():
        if line.startswith("| `APP_"):
            assert line.rstrip().endswith("|")


def test_markdown_marks_a_required_field_in_an_optional_group() -> None:
    row = next(
        line
        for line in render_markdown_table().splitlines()
        if line.startswith("| `APP_STORAGE__BUCKET`")
    )
    assert "required once any" in row


def _columns(row: str) -> list[str]:
    """Split a table row on column-separator pipes, not escaped ones.

    `_escape_table_cell` turns a literal `|` inside a cell's own content
    into `\\|` before the cells are joined. Splitting a row on every `|`
    character -- escaped or not -- counts those escaped pipes as extra
    delimiters too, so it either hides a real regression (an unescaped `|`
    then looks exactly like a correctly escaped one) or flags a perfectly
    correct row as broken. Only a `|` with no backslash immediately before
    it is an actual column boundary. The row itself opens and closes with
    its own delimiter pipe, so the first and last elements of the result
    are always the empty string either side of it.
    """
    return re.split(r"(?<!\\)\|", row)


def test_every_markdown_row_has_exactly_four_columns() -> None:
    """Pins the column count so a reintroduced unescaped `|` fails here.

    `render_markdown_table()` drops `variable.type_label` and
    `variable.description` straight into a `| a | b | c | d |` row. Two
    fields have a `Literal` type, whose type_label is built by joining
    alternatives with `" | "` -- a string that is itself full of `|`
    characters and, unescaped, reads as extra column separators rather
    than the word "or". That is exactly the bug the escaping in
    `_escape_table_cell` exists to fix (see the task report's "A bug found
    in step 6"), and it shipped past the unit-test loop once already:
    `test_markdown_table_has_a_header_and_one_row_per_variable` only
    counts lines starting with `|`, and
    `test_markdown_never_emits_a_raw_newline_inside_a_row` only checks
    that a row *ends* with `|` -- an eight-column row satisfies both.
    `mkdocs build --strict` does not catch it either: an extra-wide row is
    syntactically valid Markdown, so `--strict` builds it without warning
    and it only shows up as a visibly broken table in the rendered HTML.
    A future edit to the escaping, or a new field whose description or
    default happens to gain a `|`, silently reintroduces the same
    corruption unless something here counts columns -- so this test does,
    for every row, not only the two known `Literal` fields.
    """
    for line in render_markdown_table().splitlines():
        if not line.startswith("| `APP_"):
            continue
        columns = _columns(line)
        assert columns[0] == ""
        assert columns[-1] == ""
        content_columns = len(columns) - 2
        assert content_columns == 4, (
            f"expected 4 columns, got {content_columns}: {line!r}"
        )


def test_environment_literal_alternatives_stay_in_one_cell() -> None:
    """The bug this file's column-count test exists to catch, made concrete.

    `APP_ENVIRONMENT.type_label` is the literal string "`local` | `staging`
    | `production`" (see `test_literals_render_as_alternatives` above) --
    three escaped pipes that must still add up to a single Type cell.
    Rendered the way the bug did it, those pipes split the row instead,
    and `staging`/`production` land in the Default and Meaning columns
    rather than the Type column.
    """
    row = next(
        line
        for line in render_markdown_table().splitlines()
        if line.startswith("| `APP_ENVIRONMENT`")
    )
    type_column = _columns(row)[2]
    assert "`local`" in type_column
    assert "`staging`" in type_column
    assert "`production`" in type_column


def test_env_example_strips_markdown_links() -> None:
    """`.env.example` is read in an editor, not rendered.

    A description carrying `[Outbound HTTP calls](../guides/outbound-http.md)`
    must appear as its text, not its source.
    """
    rendered = render_env_example()
    assert "](" not in rendered
    assert "**" not in rendered


def test_env_example_comments_every_prose_line() -> None:
    for line in render_env_example().splitlines():
        if line and not line.startswith("#"):
            assert "=" in line, f"uncommented prose line: {line!r}"


def test_env_example_comments_out_variables_with_no_default() -> None:
    """An unset optional variable must not become an empty assignment.

    `APP_DATABASE__DSN=` is not the same as absent: it is a malformed URL,
    and the service would exit 78 on a file that is supposed to be a
    working starting point.
    """
    rendered = render_env_example()
    assert "# APP_DATABASE__DSN=" in rendered
    assert "\nAPP_DATABASE__DSN=" not in rendered


def test_env_example_sets_variables_that_have_defaults() -> None:
    rendered = render_env_example()
    assert "\nAPP_HTTP_PORT={{ cookiecutter.http_port }}" in rendered
    assert "\nAPP_LOG__LEVEL=info" in rendered


def test_committed_outputs_are_current() -> None:
    """The drift gate, as a test as well as a recipe.

    Running it here means a stale file fails the fast unit loop rather than
    waiting for CI -- the same arrangement the OpenAPI contract has.
    """
    stale = check_outputs()
    assert stale == [], (
        f"stale generated file(s): {stale}. Run `just config-docs` and "
        f"commit the result."
    )


def test_configuration_doc_keeps_its_generated_markers() -> None:
    text = CONFIGURATION_DOC.read_text(encoding="utf-8")
    assert text.count(MARKER_BEGIN) == 1
    assert text.count(MARKER_END) == 1


def test_json_array_fields_render_as_compact_sorted_json(
    by_name: dict[str, ConfigVariable],
) -> None:
    redact = by_name["APP_LOG__REDACT_FIELDS"]

    assert redact.type_label == "JSON array"
    assert redact.default_label == json.dumps(
        sorted(DEFAULT_REDACT_FIELDS), separators=(",", ":")
    )
    assert "frozenset" not in redact.default_label


def test_json_defaults_are_single_quoted_in_the_env_example() -> None:
    """Verified Fact 13: `just`'s dotenv loader strips DOUBLE quotes out of
    an unquoted value, so `APP_X=["a","b"]` reaches a recipe as `[a,b]` —
    no longer JSON. Single quotes survive both loaders."""
    env = render_env_example()

    assert "APP_LOG__LEVELS='{}'" in env
    assert "APP_LOG__REDACT_FIELDS='[\"" in env
    assert "APP_LOG__REDACT_FIELDS=[" not in env


def test_generated_env_example_starts_the_service_with_no_backends(
    tmp_path: Path,
) -> None:
    """The file's header promises a working starting point. Prove it.

    Every optional group must stay wholly commented out, defaults included.
    A single active variable with a default -- a pool size, say -- is
    enough for pydantic-settings to build its group and reject the group's
    missing required fields, stopping the service with exit 78 -- which is
    exactly what the first generated version of this file did, and no test
    noticed because the tests only checked which lines were commented,
    never whether the file loaded.
    """
    from {{ cookiecutter.package_name }}.settings import Settings

    env_file = tmp_path / ".env"
    env_file.write_text(render_env_example(), encoding="utf-8")
    settings = Settings(_env_file=str(env_file))  # type: ignore[call-arg]
    assert settings.database is None
    assert settings.payment is None
    assert settings.cache is None
    assert settings.storage is None


def test_groups_nested_under_an_optional_group_are_optional() -> None:
    """PaymentSettings.http is not `X | None`, but it only exists when
    APP_PAYMENT__* does. Without ancestor propagation its defaults were
    emitted as active assignments, which built PaymentSettings on its own.
    """
    by_path = {group.path: group for group in walk_settings()}
    assert by_path[("payment", "http")].optional is True
