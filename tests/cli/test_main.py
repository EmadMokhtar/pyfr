"""The `pyfr` command: arguments, exit codes, error printing."""

from __future__ import annotations

import pytest

from pyfr_cli import __version__
from pyfr_cli.__main__ import main


def test_version_prints_the_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["--version"])
    assert stop.value.code == 0
    assert capsys.readouterr().out.strip() == f"pyfr {__version__}"


def test_version_is_the_project_version() -> None:
    # importlib.metadata reads the installed distribution; uv installs the
    # project editable on every `uv run`, so this is pyproject.toml's value.
    assert __version__.count(".") == 2
