"""scripts/regen.py on a tiny fake template -- no cookiecutter, no network.

`render` is exercised by tests/test_golden.py against the real template;
here the render is a directory the test writes by hand.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import regen  # noqa: E402

ANSWERS = {"project_slug": "demo", "package_name": "demo", "license": "MIT"}
PINS_TEMPLATE = "pin = 1\nname = {{ cookiecutter.project_slug }}\n"


def git(example: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=example, check=True, capture_output=True)


@pytest.fixture
def trees(tmp_path: Path) -> tuple[Path, Path, Path]:
    template_body = tmp_path / "{{cookiecutter.project_slug}}"
    package = template_body / "src" / "{{cookiecutter.package_name}}"
    package.mkdir(parents=True)
    (template_body / "pins.txt").write_text(PINS_TEMPLATE)
    (package / "a.py").write_text("X = 1\n")
    (template_body / "LICENSE.MIT").write_text("MIT\n")
    (template_body / "LICENSE.MPL-2.0").write_text("MPL\n")

    rendered = tmp_path / "rendered" / "demo"
    (rendered / "src" / "demo").mkdir(parents=True)
    (rendered / "pins.txt").write_text("pin = 1\nname = demo\n")
    (rendered / "src" / "demo" / "a.py").write_text("X = 1\n")
    (rendered / "LICENSE").write_text("MIT\n")

    example = tmp_path / "example"
    example.mkdir()
    git(example, "init", "-q")
    git(example, "config", "user.email", "t@example.com")
    git(example, "config", "user.name", "t")
    return template_body, rendered, example


def commit_all(example: Path) -> None:
    git(example, "add", "-A")
    git(example, "commit", "-q", "-m", "x")


def test_compare_reports_missing_extra_and_differing(trees) -> None:
    _, rendered, example = trees
    (example / "pins.txt").write_text("pin = 2\nname = demo\n")
    (example / "stale.txt").write_text("gone from the template\n")
    (example / "uv.lock").write_text("resolver output\n")
    commit_all(example)

    comparison = regen.compare(rendered, example)

    assert comparison.missing == ["LICENSE", "src/demo/a.py"]
    assert comparison.extra == ["stale.txt"]
    assert comparison.differing == ["pins.txt"]
    assert not comparison.clean


def test_sync_writes_the_render_and_removes_tracked_leftovers(trees) -> None:
    _, rendered, example = trees
    (example / "stale.txt").write_text("gone\n")
    (example / "uv.lock").write_text("resolver output\n")
    commit_all(example)
    # Untracked, like a virtual environment: never the render's to remove.
    (example / ".venv").mkdir()
    (example / ".venv" / "keep").write_text("ignored, untracked\n")

    regen.sync(rendered, example)

    assert (example / "src" / "demo" / "a.py").read_text() == "X = 1\n"
    assert (example / "LICENSE").read_text() == "MIT\n"
    assert not (example / "stale.txt").exists()
    assert (example / "uv.lock").read_text() == "resolver output\n"
    assert (example / ".venv" / "keep").exists()
    # sync writes files and leaves staging to the caller, as `just regen`
    # does: stage the deletion and the new files, then the check is clean.
    git(example, "add", "-u")
    git(example, "add", "--", "src", "LICENSE", "pins.txt")
    assert regen.compare(rendered, example).clean


def test_adopt_copies_a_changed_line_back_into_the_template(trees) -> None:
    template_body, rendered, example = trees
    regen.sync(rendered, example)
    commit_all(example)
    (example / "pins.txt").write_text("pin = 2\nname = demo\n")

    adopted = regen.adopt(rendered, example, template_body, ANSWERS)

    assert adopted == ["pins.txt"]
    expected = PINS_TEMPLATE.replace("pin = 1", "pin = 2")
    assert (template_body / "pins.txt").read_text() == expected


def test_adopt_maps_rendered_paths_back_to_template_paths(trees) -> None:
    template_body, rendered, example = trees
    regen.sync(rendered, example)
    commit_all(example)
    (example / "src" / "demo" / "a.py").write_text("X = 2\n")
    (example / "LICENSE").write_text("MIT, amended\n")

    adopted = regen.adopt(rendered, example, template_body, ANSWERS)

    assert adopted == ["LICENSE", "src/demo/a.py"]
    package = template_body / "src" / "{{cookiecutter.package_name}}"
    assert (package / "a.py").read_text() == "X = 2\n"
    assert (template_body / "LICENSE.MIT").read_text() == "MIT, amended\n"


def test_adopt_refuses_a_change_it_cannot_express(trees) -> None:
    template_body, rendered, example = trees
    regen.sync(rendered, example)
    commit_all(example)
    # An inserted line, not a replaced one.
    (example / "pins.txt").write_text("pin = 1\nextra = true\nname = demo\n")

    with pytest.raises(regen.AdoptError, match=r"pins\.txt"):
        regen.adopt(rendered, example, template_body, ANSWERS)


def test_adopt_refuses_a_line_that_is_not_unique_in_the_template(trees) -> None:
    template_body, rendered, example = trees
    (template_body / "pins.txt").write_text("pin = 1\n" + PINS_TEMPLATE)
    (rendered / "pins.txt").write_text("pin = 1\npin = 1\nname = demo\n")
    regen.sync(rendered, example)
    commit_all(example)
    (example / "pins.txt").write_text("pin = 2\npin = 1\nname = demo\n")

    with pytest.raises(regen.AdoptError, match="exactly once"):
        regen.adopt(rendered, example, template_body, ANSWERS)
