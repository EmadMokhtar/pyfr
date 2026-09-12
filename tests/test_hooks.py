"""The two hooks, driven through pytest-cookies.

Every render here sets PYFR_REGEN, so the post-generation hook prunes and
stops: no git, no uv, no network. The one test of the side-effect half
points `git` and `uv` at a shim that fails, to prove best effort.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

REGEN = {"PYFR_REGEN": "1"}


@pytest.fixture(autouse=True)
def _regen_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in REGEN.items():
        monkeypatch.setenv(key, value)


def test_default_answers_render(cookies) -> None:
    result = cookies.bake()
    assert result.exit_code == 0, result.exception
    assert result.project_path.name == "my-service"
    assert (result.project_path / "src" / "my_service" / "main.py").is_file()


@pytest.mark.parametrize(
    ("answers", "message"),
    [
        ({"project_slug": "My-Service"}, "project_slug"),
        ({"project_slug": "9lives"}, "project_slug"),
        ({"package_name": "email"}, "standard library"),
        ({"package_name": "class"}, "keyword"),
        ({"package_name": "my-service"}, "identifier"),
        # 26 characters: one over the cap tests/test_generation.py proves
        # format-clean.
        ({"package_name": "abcde_fghij_klmno_pqrst_uv"}, "25 characters"),
        ({"http_port": "0"}, "http_port"),
        ({"http_port": "70000"}, "http_port"),
        ({"http_port": "eighty"}, "http_port"),
    ],
)
def test_bad_answers_are_rejected_before_anything_is_written(
    cookies, capfd, answers: dict[str, str], message: str
) -> None:
    result = cookies.bake(extra_context=answers)
    # cookiecutter wraps a failing hook as FailedHookException("Hook script
    # failed (exit status: 1)"); the hook's own sentence is on stderr.
    assert result.exit_code != 0
    assert result.project_path is None or not result.project_path.exists()
    assert message in capfd.readouterr().err


@pytest.mark.parametrize("choice", ["Apache-2.0", "MIT", "MPL-2.0", "Proprietary"])
def test_only_the_chosen_licence_survives(cookies, choice: str) -> None:
    result = cookies.bake(extra_context={"license": choice})
    assert result.exit_code == 0, result.exception
    licence = result.project_path / "LICENSE"
    assert licence.is_file()
    assert not list(result.project_path.glob("LICENSE.*"))
    text = licence.read_text()
    expected_first_line = {
        "Apache-2.0": "Apache License",
        "MIT": "MIT License",
        "MPL-2.0": "Mozilla Public License Version 2.0",
        "Proprietary": "Proprietary",
    }[choice]
    assert text.lstrip().startswith(expected_first_line)


def test_regen_mode_leaves_no_git_repository(cookies) -> None:
    result = cookies.bake()
    assert result.exit_code == 0, result.exception
    assert not (result.project_path / ".git").exists()
    assert not (result.project_path / ".venv").exists()
    assert not (result.project_path / "uv.lock").exists()


def test_side_effects_are_best_effort(
    cookies, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capfd
) -> None:
    # A `git` and a `uv` that always fail, first on PATH. The hook must
    # still exit 0 and tell the user what to run later.
    shims = tmp_path / "shims"
    shims.mkdir()
    for name in ("git", "uv"):
        shim = shims / name
        shim.write_text("#!/bin/sh\nexit 1\n")
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("PYFR_REGEN")

    result = cookies.bake()

    assert result.exit_code == 0, result.exception
    out = capfd.readouterr().out
    assert "git init" in out
    assert "uv sync" in out
