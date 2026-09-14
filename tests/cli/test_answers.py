""".pyfr-answers.yml: reading what the generator recorded."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyfr_cli import answers
from pyfr_cli.errors import UpdateError
from pyfr_cli.versions import Version

RECORDED = """\
# Written by PyFr when this project was generated.
_template: https://github.com/EmadMokhtar/pyfr
_template_version: "0.10.0"
project_name: "My Service"
project_slug: "my-service"
package_name: "my_service"
database: "postgres"
http_port: "8000"
"""


def write(project: Path, text: str = RECORDED) -> Path:
    project.mkdir(exist_ok=True)
    (project / answers.FILE).write_text(text)
    return project


def test_load_reads_template_version_and_every_value_as_a_string(
    tmp_path: Path,
) -> None:
    loaded = answers.load(write(tmp_path / "p"))
    assert loaded.template == "https://github.com/EmadMokhtar/pyfr"
    assert loaded.version == Version(0, 10, 0)
    assert loaded.values["http_port"] == "8000"
    assert loaded.values["_template_version"] == "0.10.0"
    assert loaded.path == tmp_path / "p" / answers.FILE


def test_load_refuses_a_missing_file_and_points_to_the_guide(tmp_path: Path) -> None:
    with pytest.raises(UpdateError) as stop:
        answers.load(tmp_path)
    assert answers.FILE in stop.value.cause
    assert answers.GUIDE in stop.value.fix


@pytest.mark.parametrize(
    ("text", "cause"),
    [
        ("_template: x\n", "no _template_version"),
        ("_template_version: '0.1.0'\n", "no _template"),
        ("_template: x\n_template_version: latest\n", "not a version"),
        ("- a list\n", "not a mapping"),
        ("a: [unclosed\n", "not valid YAML"),
    ],
)
def test_load_refuses_a_broken_file(tmp_path: Path, text: str, cause: str) -> None:
    with pytest.raises(UpdateError) as stop:
        answers.load(write(tmp_path / "p", text))
    assert cause in stop.value.cause


def test_context_keeps_recorded_prompts_and_names_the_defaulted_ones(
    tmp_path: Path,
) -> None:
    loaded = answers.load(write(tmp_path / "p"))
    # The target declares a new prompt (team_channel), dropped one the
    # project recorded (http_port), and its _ keys are never prompts.
    prompts = ["project_name", "database", "team_channel", "_template_version"]
    recorded, defaulted = answers.context(loaded, prompts)
    assert recorded == {"project_name": "My Service", "database": "postgres"}
    assert defaulted == ["team_channel"]


def test_install_copies_the_rendered_file_over_the_project_one(
    tmp_path: Path,
) -> None:
    project = write(tmp_path / "p")
    rendered = write(tmp_path / "r", RECORDED.replace("0.10.0", "0.12.0"))
    answers.install(rendered, project)
    assert answers.load(project).version == Version(0, 12, 0)


def test_version_in_reads_the_text_of_an_answers_file() -> None:
    assert answers.version_in(RECORDED) == Version(0, 10, 0)
    assert answers.version_in("project_name: x\n") is None
    assert answers.version_in("not: [yaml\n") is None
