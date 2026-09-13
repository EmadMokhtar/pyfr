"""Generate the configuration reference and .env.example from the model.

`settings.py` is the single source of truth for every environment variable
this service reads. Previously the same 38 variables were described three
times by hand -- in the model's own comments, in .env.example, and in the
documentation table -- in three voices, with nothing keeping the three in
agreement. This script deletes two of those copies.

Run `just config-docs` to regenerate both outputs. `just gates` fails if
either has drifted, exactly as it does for the committed OpenAPI document.

Not an installed module: it is a build tool that reads the package beside
it, so it lives in scripts/ and is imported by path.
"""

from __future__ import annotations

import json
import re
import sys
import types
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import annotated_types
from pydantic import BaseModel, SecretStr
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from reference_service.settings import Settings

ENV_PREFIX = "APP_"
NESTED_DELIMITER = "__"

# Pydantic network types render by what they mean to whoever sets the
# variable, not by their Python class name. `PostgresDsn` tells a reader
# nothing that "PostgreSQL URL" does not tell them better.
_NETWORK_TYPE_LABELS = {
    "PostgresDsn": "PostgreSQL URL",
    "RedisDsn": "Redis URL",
    "HttpUrl": "URL",
    "AnyUrl": "URL",
}

_SCALAR_TYPE_LABELS = {
    bool: "boolean",
    int: "integer",
    float: "float",
    str: "string",
}


@dataclass(frozen=True)
class ConfigVariable:
    """One environment variable, as the documentation needs to describe it."""

    name: str
    type_label: str
    default_label: str
    description: str
    secret: bool
    # True when the field has no default AND its group is optional -- the
    # "unset, required once any APP_PAYMENT__* variable is set" case. A
    # required field in a non-optional group is simply required.
    required_in_group: bool


@dataclass(frozen=True)
class ConfigGroup:
    """A settings sub-model, with the variables it contributes."""

    # () for Settings itself, ("cache",), ("payment", "http").
    path: tuple[str, ...]
    # The sub-model's docstring, used as the group header in .env.example.
    doc: str
    # True when the whole group may be absent -- `X | None = None`.
    optional: bool
    variables: tuple[ConfigVariable, ...]


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    """Return the non-None member of `X | None`, and whether it was one.

    Verified Facts 3 and 4 both reduce to this: optional sub-models and
    optional secrets are unions, and every check downstream -- "is this a
    BaseModel", "is this a SecretStr" -- fails against the union itself.
    """
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        members = [
            argument
            for argument in typing.get_args(annotation)
            if argument is not type(None)
        ]
        if len(members) == 1:
            return members[0], True
    return annotation, False


def _is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


_JSON_TYPE_LABELS = frozenset({"JSON object", "JSON array"})


def _json_default(value: Any) -> str:
    """JSON, compact, deterministic -- what a reader writes into .env.

    Sets are sorted first: a frozenset's iteration order is not stable
    across processes, and a generated file must not change between runs.
    """
    if isinstance(value, (set, frozenset)):
        value = sorted(value)
    return json.dumps(value, separators=(",", ":"))


def _render_default(info: FieldInfo) -> str:
    """The default, as a reader should see it written in a file.

    Verified Fact 2 (M5) is the whole reason this is not `str(info.default)`:
    a field declared with `default_factory` reports `PydanticUndefined` as
    its default while reporting itself as not required, so the naive
    version writes the sentinel's repr into the published documentation.
    """
    if info.default_factory is not None:
        produced = info.default_factory()  # type: ignore[call-arg]
        if isinstance(produced, BaseModel):
            # A sub-model default is not a value anyone sets; the group's
            # own variables carry the real defaults.
            return ""
        if isinstance(produced, (dict, list, set, frozenset)):
            return _json_default(produced)
        return str(produced)
    if info.default is PydanticUndefined or info.default is None:
        return "unset"
    if isinstance(info.default, bool):
        return "true" if info.default else "false"
    if isinstance(info.default, (dict, list, set, frozenset)):
        return _json_default(info.default)
    return str(info.default)


def _constraint_label(base: str, metadata: list[Any]) -> str:
    """Fold annotated_types constraints into the base type's label.

    Verified Fact 5: `Field(default=10, ge=1)` puts `Ge(ge=1)` here, and
    these are what the hand-written table rendered as "integer, ≥ 1".
    """
    minimum: Any = None
    maximum: Any = None
    exclusive_minimum: Any = None
    for item in metadata:
        if isinstance(item, annotated_types.Ge):
            minimum = item.ge
        elif isinstance(item, annotated_types.Le):
            maximum = item.le
        elif isinstance(item, annotated_types.Gt):
            exclusive_minimum = item.gt

    # Every combination has to render BOTH bounds when both are present.
    # The bug this replaced handled only Ge+Le together (the one shape a
    # real field happens to use today) and fell through to a lower-bound-only
    # label — or, for Gt+Le, to an upper-bound-DROPPING label — for every
    # other combination. Losing the upper bound silently is worse than an
    # ugly label: "float, > 0" for a field capped at 100 is confidently
    # wrong, not merely unpolished, which is the exact failure this
    # generator exists to eliminate.
    if minimum is not None and maximum is not None:
        return f"{base}, {minimum}–{maximum}"
    if exclusive_minimum is not None and maximum is not None:
        return f"{base}, > {exclusive_minimum}, ≤ {maximum}"
    if minimum is not None:
        return f"{base}, ≥ {minimum}"
    if maximum is not None:
        return f"{base}, ≤ {maximum}"
    if exclusive_minimum is not None:
        return f"{base}, > {exclusive_minimum}"
    return base


def _render_type(info: FieldInfo) -> str:
    """A human label for the annotation, constraints folded in.

    An explicit `json_schema_extra={"type_label": ...}` always wins. That
    escape hatch exists for the handful of fields whose real constraint is
    a regular expression: deriving "string, 3–63 chars" from
    `^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$` is not a job for a generator.
    """
    extra = info.json_schema_extra
    if isinstance(extra, dict) and "type_label" in extra:
        return str(extra["type_label"])

    annotation, _ = _unwrap_optional(info.annotation)

    if annotation is SecretStr:
        return "secret"

    name = getattr(annotation, "__name__", "")
    if name in _NETWORK_TYPE_LABELS:
        return _NETWORK_TYPE_LABELS[name]

    origin = typing.get_origin(annotation)
    if origin is typing.Literal:
        return " | ".join(f"`{value}`" for value in typing.get_args(annotation))
    if origin is dict:
        return "JSON object"
    if origin in (list, set, frozenset):
        return "JSON array"

    base = _SCALAR_TYPE_LABELS.get(annotation, name or "string")
    return _constraint_label(base, list(info.metadata))


def _is_secret(info: FieldInfo) -> bool:
    """Verified Fact 3: unwrap before comparing, or `SecretStr | None` slips."""
    annotation, _ = _unwrap_optional(info.annotation)
    return annotation is SecretStr


def _variable_name(path: tuple[str, ...], field_name: str) -> str:
    parts = (*path, field_name)
    return ENV_PREFIX + NESTED_DELIMITER.join(part.upper() for part in parts)


def _walk_model(
    model: type[BaseModel],
    path: tuple[str, ...],
    optional: bool,
    groups: list[ConfigGroup],
) -> None:
    """Append this model's group, then recurse into its sub-models.

    Depth-first in declaration order, so the generated files diff minimally
    against a model whose fields were reordered rather than rewritten.
    """
    variables: list[ConfigVariable] = []
    nested: list[tuple[str, type[BaseModel], bool]] = []

    for field_name, info in model.model_fields.items():
        annotation, was_optional = _unwrap_optional(info.annotation)
        if _is_model(annotation):
            nested.append((field_name, annotation, was_optional))
            continue
        variables.append(
            ConfigVariable(
                name=_variable_name(path, field_name),
                type_label=_render_type(info),
                default_label=_render_default(info),
                description=info.description or "",
                secret=_is_secret(info),
                required_in_group=info.is_required() and optional,
            )
        )

    groups.append(
        ConfigGroup(
            path=path,
            doc=(model.__doc__ or "").strip(),
            optional=optional,
            variables=tuple(variables),
        )
    )

    for field_name, sub_model, was_optional in nested:
        # A group nested under an optional one is absent whenever its
        # parent is: PaymentSettings.http is not itself `X | None`, but it
        # only exists at all when APP_PAYMENT__* is set. Without this,
        # .env.example would set APP_PAYMENT__HTTP__* defaults on their own
        # -- and pydantic-settings, seeing any APP_PAYMENT__* variable,
        # builds PaymentSettings and rejects the missing base_url.
        _walk_model(sub_model, (*path, field_name), optional or was_optional, groups)


def walk_settings() -> list[ConfigGroup]:
    """Every environment variable the service reads, grouped by sub-model."""
    groups: list[ConfigGroup] = []
    _walk_model(Settings, (), optional=False, groups=groups)
    return groups


_SERVICE_ROOT = Path(__file__).resolve().parents[1]
_REPOSITORY_ROOT = _SERVICE_ROOT.parents[1]

ENV_EXAMPLE = _SERVICE_ROOT / ".env.example"
CONFIGURATION_DOC = _REPOSITORY_ROOT / "docs" / "reference" / "configuration.md"

MARKER_BEGIN = "<!-- generated: config-table. Run `just config-docs`. -->"
MARKER_END = "<!-- /generated: config-table -->"

_ENV_HEADER = """\
# Copy to .env for local development. Never commit .env itself.
#
# GENERATED FILE -- do not edit. Every line below comes from
# src/reference_service/settings.py. Change a description there and run
# `just config-docs`; `just gates` fails if this file has drifted.
"""

# Markdown that means something to a rendered page and nothing to someone
# reading a dotfile in an editor.
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MARKDOWN_EMPHASIS = re.compile(r"\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`")


def _plain_text(description: str) -> str:
    """Markdown reduced to what it says, for a file nobody renders."""
    text = _MARKDOWN_LINK.sub(r"\1", description)
    return _MARKDOWN_EMPHASIS.sub(
        lambda match: match.group(1) or match.group(2) or match.group(3), text
    )


def _default_cell(variable: ConfigVariable) -> str:
    if variable.required_in_group:
        group = variable.name.rsplit(NESTED_DELIMITER, 1)[0]
        return f"unset, required once any `{group}{NESTED_DELIMITER}*` is set"
    if variable.default_label in {"", "unset"}:
        return "unset"
    return f"`{variable.default_label}`"


def _escape_table_cell(text: str) -> str:
    """Escape a literal "|", which would otherwise split the row.

    `_render_type` joins a `Literal`'s alternatives with " | " (Verified
    Fact: `APP_ENVIRONMENT`'s type_label is the literal string "`local` |
    `staging` | `production`"), and that string is about to be embedded in
    a Markdown table cell -- unescaped, it reads as two extra column
    separators, not the word "or".
    """
    return text.replace("|", "\\|")


def render_markdown_table() -> str:
    """The published reference table, one row per environment variable."""
    rows = [
        "| Variable | Type | Default | Meaning |",
        "| --- | --- | --- | --- |",
    ]
    for group in walk_settings():
        for variable in group.variables:
            # Descriptions are wrapped Python strings; a stray newline would
            # end the table silently, so collapse whitespace unconditionally.
            meaning = " ".join(variable.description.split())
            cells = (
                f"`{variable.name}`",
                variable.type_label,
                _default_cell(variable),
                meaning,
            )
            rows.append(
                "| " + " | ".join(_escape_table_cell(cell) for cell in cells) + " |"
            )
    return "\n".join(rows)


def _wrap_comment(text: str, width: int = 76) -> list[str]:
    """Prose as `#` lines, wrapped so the file stays readable in an editor."""
    words = text.split()
    lines: list[str] = []
    current = "#"
    for word in words:
        candidate = f"{current} {word}"
        if len(candidate) > width and current != "#":
            lines.append(current)
            current = f"# {word}"
        else:
            current = candidate
    if current != "#":
        lines.append(current)
    return lines


def render_env_example() -> str:
    """A working starting point, with every variable documented in place."""
    blocks: list[str] = [_ENV_HEADER]
    for group in walk_settings():
        section: list[str] = []
        if group.doc:
            section.extend(_wrap_comment(_plain_text(group.doc)))
        if group.optional:
            # The whole block stays commented out, defaults included. Any
            # single variable of the group being set -- even one with a
            # harmless default like a pool size -- makes pydantic-settings
            # build the group's model, which then rejects its missing
            # required fields and stops the service with exit 78. Absent
            # means the whole group is absent; that is the supported
            # configuration this file must start in.
            section.append(
                "# Optional. Uncomment the whole block to enable it; leave it "
                "all commented out to run without."
            )
        for variable in group.variables:
            section.extend(_wrap_comment(_plain_text(variable.description)))
            value = variable.default_label
            if group.optional:
                shown = value if value not in {"", "unset"} else ""
                section.append(f"# {variable.name}={shown}")
            elif value in {"", "unset"}:
                # Commented out, not left empty: an empty assignment is a
                # malformed value, not an absent one.
                section.append(f"# {variable.name}=")
            elif variable.type_label in _JSON_TYPE_LABELS:
                # Single-quoted. `just`'s dotenv loader strips the DOUBLE
                # quotes out of an unquoted value -- APP_X=["a","b"] reaches
                # a recipe as [a,b], which pydantic-settings can no longer
                # parse -- while single quotes survive both it and
                # python-dotenv (M6 plan, Verified Fact 13).
                section.append(f"{variable.name}='{value}'")
            else:
                section.append(f"{variable.name}={value}")
        blocks.append("\n".join(section))
    return "\n\n".join(blocks) + "\n"


def _configuration_doc_with_table(existing: str, table: str) -> str:
    """Replace only the region between the markers, keeping the prose."""
    begin = existing.index(MARKER_BEGIN) + len(MARKER_BEGIN)
    end = existing.index(MARKER_END)
    return existing[:begin] + "\n\n" + table + "\n\n" + existing[end:]


def _rendered_outputs() -> dict[Path, str]:
    return {
        ENV_EXAMPLE: render_env_example(),
        CONFIGURATION_DOC: _configuration_doc_with_table(
            CONFIGURATION_DOC.read_text(encoding="utf-8"), render_markdown_table()
        ),
    }


def write_outputs() -> None:
    for path, content in _rendered_outputs().items():
        path.write_text(content, encoding="utf-8")


def check_outputs() -> list[str]:
    """Paths whose committed content differs from what the model produces."""
    return [
        str(path.relative_to(_REPOSITORY_ROOT))
        for path, content in _rendered_outputs().items()
        if path.read_text(encoding="utf-8") != content
    ]


if __name__ == "__main__":
    if "--check" in sys.argv:
        stale = check_outputs()
        if stale:
            sys.stderr.write(
                "These generated files are stale:\n"
                + "".join(f"  {path}\n" for path in stale)
                + "Run `just config-docs` and commit the result.\n"
            )
            raise SystemExit(1)
        print("configuration documentation is current")
    else:
        write_outputs()
        print("regenerated .env.example and docs/reference/configuration.md")
