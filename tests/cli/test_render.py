"""Rendering the template at the target version with the recorded answers.

A tiny template stands in for the real one: the real body is rendered by
tests/test_update_e2e.py.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cli.helpers import commit_all, git, make_repo
from pyfr_cli import answers, render
from pyfr_cli.errors import UpdateError
from pyfr_cli.git import Git
from pyfr_cli.versions import Version

BODY = "{{cookiecutter.project_slug}}"
HOOK = """\
import os
import pathlib

# An environmental side effect, like the real hook's `git init`: it must
# not happen under PYFR_REGEN.
if not os.environ.get("PYFR_REGEN"):
    pathlib.Path("side-effect.txt").write_text("ran\\n")
"""
ANSWERS_BODY = """\
_template: https://example.com/pyfr
_template_version: "{{ cookiecutter._template_version }}"
project_slug: "{{ cookiecutter.project_slug }}"
flavour: "{{ cookiecutter.flavour }}"
greeting: "{{ cookiecutter.greeting }}"
"""


def write_template(root: Path, *, with_greeting_in_answers: bool = True) -> Path:
    (root / BODY).mkdir(parents=True)
    (root / "hooks").mkdir()
    (root / "cookiecutter.json").write_text(
        json.dumps(
            {
                "project_slug": "demo",
                "flavour": ["plain", "spicy"],
                "greeting": "hello",
                "_template_version": "1.1.0",
            }
        )
    )
    (root / "hooks" / "post_gen_project.py").write_text(HOOK)
    (root / BODY / "hello.txt").write_text(
        "{{ cookiecutter.greeting }} {{ cookiecutter.project_slug }}\n"
    )
    body = (
        ANSWERS_BODY
        if with_greeting_in_answers
        else ANSWERS_BODY.replace('greeting: "{{ cookiecutter.greeting }}"\n', "")
    )
    (root / BODY / answers.FILE).write_text(body)
    return root


def recorded(tmp_path: Path, **overrides: str) -> answers.Answers:
    values = {
        "_template": "https://example.com/pyfr",
        "_template_version": "1.0.0",
        "project_slug": "demo2",
        "flavour": "spicy",
        **overrides,
    }
    return answers.Answers(
        tmp_path / answers.FILE, values["_template"], Version(1, 0, 0), values
    )


def test_render_uses_recorded_answers_defaults_new_prompts_and_prunes_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = write_template(tmp_path / "template")
    monkeypatch.delenv("PYFR_REGEN", raising=False)
    result = render.render(
        template, Version(1, 1, 0), recorded(tmp_path), tmp_path / "out"
    )
    assert result.clone == template
    assert result.project == tmp_path / "out" / "demo2"
    assert (result.project / "hello.txt").read_text() == "hello demo2\n"
    # The prompt the target added took its default, and is reported ...
    assert result.defaulted == {"greeting": "hello"}
    # ... the render's answers file records everything at the target version ...
    written = answers.load(result.project)
    assert written.version == Version(1, 1, 0)
    assert written.values["flavour"] == "spicy"
    # ... the hook pruned and stopped: no side effect ...
    assert not (result.project / "side-effect.txt").exists()
    # ... and the environment is as it was.
    assert "PYFR_REGEN" not in os.environ


def test_render_reports_the_raw_default_when_the_answers_file_lacks_the_prompt(
    tmp_path: Path,
) -> None:
    template = write_template(tmp_path / "template", with_greeting_in_answers=False)
    result = render.render(
        template, Version(1, 1, 0), recorded(tmp_path), tmp_path / "out"
    )
    assert result.defaulted == {"greeting": "hello"}


def test_render_surfaces_a_recorded_choice_the_target_no_longer_offers(
    tmp_path: Path,
) -> None:
    template = write_template(tmp_path / "template")
    with pytest.raises(UpdateError) as stop:
        render.render(
            template,
            Version(1, 1, 0),
            recorded(tmp_path, flavour="hot"),
            tmp_path / "out",
        )
    assert "v1.1.0" in stop.value.cause
    assert "hot" in stop.value.cause
    assert "flavour" in stop.value.cause


def test_prompts_are_the_non_underscore_keys(tmp_path: Path) -> None:
    template = write_template(tmp_path / "template")
    assert list(render.prompts(template)) == ["project_slug", "flavour", "greeting"]


def test_clone_template_checks_out_the_tag(tmp_path: Path) -> None:
    remote = make_repo(tmp_path / "remote", {"marker.txt": "v1\n"})
    git(remote, "tag", "v1.0.0")
    (remote / "marker.txt").write_text("v2\n")
    commit_all(remote, "v2")
    git(remote, "tag", "v2.0.0")
    clone = render.clone_template(
        str(remote), Version(1, 0, 0), tmp_path / "clone", Git(tmp_path)
    )
    assert (clone / "marker.txt").read_text() == "v1\n"
    assert (clone / ".git").exists()


def test_clone_template_refuses_a_missing_tag(tmp_path: Path) -> None:
    remote = make_repo(tmp_path / "remote")
    with pytest.raises(UpdateError) as stop:
        render.clone_template(
            str(remote), Version(9, 9, 9), tmp_path / "clone", Git(tmp_path)
        )
    assert "could not clone" in stop.value.cause
    assert "v9.9.9" in stop.value.cause
