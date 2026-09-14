"""The `pyfr` command: arguments, exit codes, error printing."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

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
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    assert __version__ == tomllib.loads(pyproject.read_text())["project"]["version"]


def test_update_check_reports_the_versions_and_exits_by_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from cli.helpers import git, make_repo

    template = make_repo(tmp_path / "template")
    git(template, "tag", "v0.10.0")
    project = tmp_path / "project"
    project.mkdir()
    (project / ".pyfr-answers.yml").write_text(
        f'_template: {template}\n_template_version: "0.10.0"\n'
    )
    monkeypatch.chdir(project)

    assert main(["update-check"]) == 0
    assert capsys.readouterr().out == "recorded v0.10.0, newest v0.10.0\n"

    git(template, "tag", "v0.11.0")
    assert main(["update-check", "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "recorded": "v0.10.0",
        "newest": "v0.11.0",
        "behind": True,
        "template": str(template),
    }
    # --template overrides the recorded URL.
    other = make_repo(tmp_path / "other")
    git(other, "tag", "v0.10.0")
    assert main(["update-check", "--template", str(other)]) == 0


def test_an_error_is_two_lines_on_stderr_and_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["update-check"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: .pyfr-answers.yml not found in ")
    assert "\n  fix: run from the project root" in captured.err


def test_pyfr_debug_re_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from pyfr_cli.errors import UpdateError

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYFR_DEBUG", "1")
    with pytest.raises(UpdateError):
        main(["update-check"])


def test_a_subcommand_is_required() -> None:
    with pytest.raises(SystemExit) as stop:
        main([])
    assert stop.value.code == 2


def test_an_os_error_is_two_lines_on_stderr_and_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import pyfr_cli.update as update_module

    def raise_os_error(*args: object, **kwargs: object) -> int:
        raise OSError("disk full")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(update_module, "check", raise_os_error)
    assert main(["update-check"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: disk full")
    assert "\n  fix: check the paths" in captured.err


def test_an_os_error_re_raises_under_pyfr_debug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pyfr_cli.update as update_module

    def raise_os_error(*args: object, **kwargs: object) -> int:
        raise OSError("disk full")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(update_module, "check", raise_os_error)
    monkeypatch.setenv("PYFR_DEBUG", "1")
    with pytest.raises(OSError):
        main(["update-check"])
