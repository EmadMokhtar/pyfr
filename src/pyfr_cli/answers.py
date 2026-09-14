""".pyfr-answers.yml: what the generator recorded, what an update rewrites."""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from pyfr_cli.errors import UpdateError
from pyfr_cli.versions import Version

FILE = ".pyfr-answers.yml"
GUIDE = "docs/guides/update-from-template.md"


@dataclass(frozen=True)
class Answers:
    path: Path
    template: str
    version: Version
    # Every key, every value as a string: cookiecutter's extra_context
    # takes strings, and the generator wrote the file from strings.
    values: dict[str, str]


def load(project: Path) -> Answers:
    path = project / FILE
    if not path.is_file():
        raise UpdateError(
            f"{FILE} not found in {project}",
            "run from the project root; a project generated before PyFr "
            f"v0.7.0 has no answers file -- {GUIDE} shows how to write one",
        )
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise UpdateError(
            f"{FILE} is not valid YAML: {exc}", f"fix the file; see {GUIDE}"
        ) from exc
    if not isinstance(data, dict):
        raise UpdateError(f"{FILE} is not a mapping", f"fix the file; see {GUIDE}")
    values = {str(key): str(value) for key, value in data.items()}
    for key in ("_template", "_template_version"):
        if key not in values:
            raise UpdateError(f"{FILE} has no {key}", f"add it; see {GUIDE}")
    try:
        version = Version.parse(values["_template_version"])
    except ValueError as exc:
        raise UpdateError(
            f"{FILE}: _template_version {exc}",
            f"set it to the version the project was generated from; see {GUIDE}",
        ) from exc
    return Answers(path, values["_template"], version, values)


def context(
    answers: Answers, prompts: Iterable[str]
) -> tuple[dict[str, str], list[str]]:
    """cookiecutter's extra_context for a render at a template declaring
    `prompts`, and the names of the prompts that will take their default.

    A prompt the target added since the project was generated has no
    recorded value; a recorded answer the target no longer declares is
    left out (spec section 4.4).
    """
    wanted = [prompt for prompt in prompts if not prompt.startswith("_")]
    recorded = {p: answers.values[p] for p in wanted if p in answers.values}
    defaulted = [p for p in wanted if p not in answers.values]
    return recorded, defaulted


def install(rendered_project: Path, project: Path) -> None:
    """Step 10: the render's answers file -- the recorded answers, the new
    prompts' defaults, the target version -- becomes the project's."""
    shutil.copyfile(rendered_project / FILE, project / FILE)


def version_in(text: str) -> Version | None:
    """The _template_version an answers file's text records, if any."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict) or "_template_version" not in data:
        return None
    try:
        return Version.parse(str(data["_template_version"]))
    except ValueError:
        return None
