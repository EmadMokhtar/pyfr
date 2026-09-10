"""Generate the configuration reference and .env.example from the model.

`settings.py` is the single source of truth for every environment variable
this service reads. Before M5 the same 38 variables were described three
times by hand -- in the model's own comments, in .env.example, and in the
documentation table -- in three voices, with nothing keeping the three in
agreement. This script deletes two of those copies.

Run `just config-docs` to regenerate both outputs. `just gates` fails if
either has drifted, exactly as it does for the committed OpenAPI document.

Not an installed module: it is a build tool that reads the package beside
it, so it lives in scripts/ and is imported by path.
"""

from __future__ import annotations

import types
import typing
from dataclasses import dataclass
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
    # "unset, required once any APP_STORAGE__* variable is set" case. A
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


def _render_default(info: FieldInfo) -> str:
    """The default, as a reader should see it written in a file.

    Verified Fact 2 is the whole reason this is not `str(info.default)`:
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
        if isinstance(produced, dict):
            # Rendered as the JSON a reader would actually write.
            return "{}" if not produced else repr(produced)
        return str(produced)
    if info.default is PydanticUndefined or info.default is None:
        return "unset"
    if isinstance(info.default, bool):
        return "true" if info.default else "false"
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

    if minimum is not None and maximum is not None:
        return f"{base}, {minimum}–{maximum}"
    if minimum is not None:
        return f"{base}, ≥ {minimum}"
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
        _walk_model(sub_model, (*path, field_name), was_optional, groups)


def walk_settings() -> list[ConfigGroup]:
    """Every environment variable the service reads, grouped by sub-model."""
    groups: list[ConfigGroup] = []
    _walk_model(Settings, (), optional=False, groups=groups)
    return groups
