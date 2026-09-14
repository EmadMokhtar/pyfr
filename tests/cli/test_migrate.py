"""updates/<version>/: which scripts run for an update, and how."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from pyfr_cli import migrate
from pyfr_cli.errors import UpdateError
from pyfr_cli.versions import Version

MARK = """\
import os
import pathlib

NAME = "{name}"
log = pathlib.Path("migrations.log")
existing = log.read_text() if log.exists() else ""
frm = os.environ["PYFR_UPDATE_FROM"]
to = os.environ["PYFR_UPDATE_TO"]
line = f"{{frm}}->{{to}} {{NAME}}\\n"
# Idempotent: a second run leaves the log as it is.
if line not in existing:
    with log.open("a") as handle:
        handle.write(line)
print("hello from", NAME)
"""
FAIL = "import sys\nsys.exit('the schema is not what I expected')\n"
WARN = 'import sys\nprint("warning: the schema looks old", file=sys.stderr)\n'


def script(clone: Path, version: str, name: str, text: str) -> Path:
    path = clone / "updates" / version / f"{name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    root = tmp_path / "clone"
    (root / "updates").mkdir(parents=True)
    (root / "updates" / "README.md").write_text("the contract\n")
    script(root, "v1.1.0", "before", MARK.format(name="v1.1.0/before"))
    script(root, "v1.1.0", "after", MARK.format(name="v1.1.0/after"))
    script(root, "v1.2.0", "after", MARK.format(name="v1.2.0/after"))
    script(root, "v1.10.0", "before", MARK.format(name="v1.10.0/before"))
    script(root, "v2.0.0", "before", MARK.format(name="v2.0.0/before"))
    script(root, "1.3.0", "before", FAIL)  # no v: not a migration directory
    (root / "updates" / "notes.txt").write_text("not a directory\n")
    return root


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / ".python-version").write_text("3.13\n")
    return root


def test_discover_takes_the_half_open_range_in_numeric_order(clone: Path) -> None:
    found = migrate.discover(clone, Version(1, 0, 0), Version(1, 10, 0))
    assert [m.version for m in found] == [
        Version(1, 1, 0),
        Version(1, 2, 0),
        Version(1, 10, 0),
    ]
    assert found[0].before is not None and found[0].after is not None
    assert found[1].before is None and found[1].after is not None
    assert found[2].after is None


def test_discover_is_empty_without_an_updates_directory(tmp_path: Path) -> None:
    assert migrate.discover(tmp_path, Version(0, 1, 0), Version(9, 0, 0)) == []


def test_run_before_and_after_run_their_scripts_in_order_with_the_env(
    clone: Path, project: Path
) -> None:
    found = migrate.discover(clone, Version(1, 0, 0), Version(1, 10, 0))
    out = io.StringIO()
    migrate.run_before(found, project, Version(1, 0, 0), Version(1, 10, 0), out)
    migrate.run_after(found, project, Version(1, 0, 0), Version(1, 10, 0), out)
    assert (project / "migrations.log").read_text() == (
        "v1.0.0->v1.10.0 v1.1.0/before\n"
        "v1.0.0->v1.10.0 v1.10.0/before\n"
        "v1.0.0->v1.10.0 v1.1.0/after\n"
        "v1.0.0->v1.10.0 v1.2.0/after\n"
    )
    text = out.getvalue()
    assert "migrations: v1.1.0/before.py" in text
    assert "hello from v1.2.0/after" in text


def test_a_failing_script_stops_the_update_with_its_message(
    clone: Path, project: Path
) -> None:
    script(clone, "v1.5.0", "before", FAIL)
    found = migrate.discover(clone, Version(1, 4, 0), Version(1, 5, 0))
    with pytest.raises(UpdateError) as stop:
        migrate.run_before(
            found, project, Version(1, 4, 0), Version(1, 5, 0), io.StringIO()
        )
    assert "v1.5.0/before.py failed" in stop.value.cause
    assert "the schema is not what I expected" in stop.value.cause
    assert "git reset --hard HEAD" in stop.value.fix


def test_a_successful_script_s_stderr_is_shown(clone: Path, project: Path) -> None:
    script(clone, "v1.5.0", "before", WARN)
    found = migrate.discover(clone, Version(1, 4, 0), Version(1, 5, 0))
    out = io.StringIO()
    migrate.run_before(found, project, Version(1, 4, 0), Version(1, 5, 0), out)
    assert "warning: the schema looks old\n" in out.getvalue()
