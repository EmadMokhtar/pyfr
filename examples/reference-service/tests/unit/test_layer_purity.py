"""The inner layers may import only Pydantic and the standard library.

import-linter's contracts are blocklists — they catch the packages they
name. This is the allowlist half: it fails on ANY third-party import into
domain or application, including one nobody thought to forbid.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

import reference_service.application
import reference_service.domain

ALLOWED_THIRD_PARTY = frozenset({"pydantic"})


def _top_level_imports(source: Path) -> set[str]:
    """Every distinct top-level package this module imports."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        # level > 0 is a relative import, which is intra-package by definition.
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize(
    "package",
    [reference_service.domain, reference_service.application],
    ids=["domain", "application"],
)
def test_layer_imports_only_pydantic_and_the_standard_library(
    package: object,
) -> None:
    package_file = getattr(package, "__file__", None)
    assert package_file is not None, "package has no __file__"
    modules = sorted(Path(package_file).parent.glob("*.py"))
    assert modules, "no modules found — the glob is wrong, so this test is blind"

    offenders: dict[str, set[str]] = {}
    for module in modules:
        unexpected = {
            name
            for name in _top_level_imports(module)
            if name not in sys.stdlib_module_names
            and name not in ALLOWED_THIRD_PARTY
            and name != "reference_service"
        }
        if unexpected:
            offenders[module.name] = unexpected

    assert not offenders, f"third-party imports found: {offenders}"
