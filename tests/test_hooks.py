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
        # Free text is pasted into pyproject.toml, Python and Markdown as is:
        # a quote, a backslash or a line break would break one of them.
        ({"description": 'Orders "API"'}, "description"),
        ({"author_name": "Back\\slash"}, "author_name"),
        ({"project_name": "Line\nbreak"}, "project_name"),
        ({"author_email": "tab\tme@example.com"}, "author_email"),
        ({"http_port": "0"}, "http_port"),
        ({"http_port": "70000"}, "http_port"),
        ({"http_port": "eighty"}, "http_port"),
        # int() accepts a leading zero; the render would not (`default=08000`).
        ({"http_port": "08000"}, "http_port"),
        # Ports the generated stack binds on the host (compose.yaml and
        # `just docs`): always, and per chosen backend -- the defaults
        # choose every backend.
        ({"http_port": "8001"}, "documentation preview"),
        ({"http_port": "9099"}, "payment stub"),
        ({"http_port": "3000"}, "Grafana"),
        ({"http_port": "5432"}, "PostgreSQL"),
        ({"http_port": "6379"}, "Redis"),
        ({"http_port": "9000"}, "MinIO"),
        ({"http_port": "9001"}, "MinIO console"),
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


def test_free_text_may_contain_apostrophes_and_non_ascii(cookies) -> None:
    # The refusal above is narrow: everything the formats can carry is fine.
    result = cookies.bake(
        extra_context={
            "description": "Emad's caf\u00e9 orders service \u2014 v2.",
            "author_name": "Zo\u00eb O'Neil",
        }
    )
    assert result.exit_code == 0, result.exception
    pyproject = (result.project_path / "pyproject.toml").read_text()
    assert "Emad's caf\u00e9 orders service \u2014 v2." in pyproject
    assert "Zo\u00eb O'Neil" in pyproject


def test_a_backend_port_is_free_when_the_backend_is_absent(cookies) -> None:
    # MinIO's 9000 is refused only when MinIO is in the stack; a project
    # without object storage may listen there.
    result = cookies.bake(extra_context={"http_port": "9000", "object_storage": "none"})
    assert result.exit_code == 0, result.exception
    assert '"9000:9000"' in (result.project_path / "compose.yaml").read_text()


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


@pytest.mark.parametrize(
    "answers",
    [{"database": "mysql"}, {"cache": "memcached"}, {"object_storage": "gcs"}],
)
def test_a_backend_answer_outside_its_choices_is_refused_before_any_hook(
    cookies, answers: dict[str, str]
) -> None:
    # cookiecutter validates a choice variable when the override is applied,
    # before pre_gen_project.py runs, so `database=mysql` can never reach the
    # Jinja blocks (which would treat it as "not postgres") and the hook's
    # pruning table (which would treat it as "not none") with two different
    # meanings. This pins that guard: no project is written at all.
    result = cookies.bake(extra_context=answers)
    assert result.exit_code != 0
    assert result.project_path is None or not result.project_path.exists()
    assert "choice variable" in str(result.exception)


@pytest.mark.parametrize(
    ("answers", "gone", "kept"),
    [
        (
            {"database": "none"},
            ("migrations", "schema.sql", "src/my_service/infrastructure/db"),
            (
                "src/my_service/infrastructure/memory",
                "src/my_service/infrastructure/cache",
            ),
        ),
        (
            {"cache": "none"},
            ("src/my_service/infrastructure/cache",),
            ("src/my_service/infrastructure/db",),
        ),
        (
            {"object_storage": "none"},
            (
                "src/my_service/infrastructure/storage",
                "tests/integration/test_receipt_store.py",
            ),
            ("src/my_service/infrastructure/memory/receipt_store.py",),
        ),
    ],
)
def test_the_hook_deletes_an_unchosen_backend_whole(
    cookies, answers, gone, kept
) -> None:
    result = cookies.bake(extra_context=answers)
    assert result.exit_code == 0, result.exception
    for path in gone:
        assert not (result.project_path / path).exists(), path
    for path in kept:
        assert (result.project_path / path).exists(), path


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
