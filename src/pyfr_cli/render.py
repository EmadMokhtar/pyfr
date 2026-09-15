"""The template at the target version, rendered with the recorded answers.

A shallow clone into a temporary directory, rendered by path -- never by
URL, so cookiecutter's own clone cache and its re-clone prompt are never
involved, and the clone's updates/ and CHANGELOG.md are on disk for the
later steps (spec section 4.4).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from pyfr_cli import answers
from pyfr_cli.errors import UpdateError
from pyfr_cli.git import Git
from pyfr_cli.versions import Version


@dataclass(frozen=True)
class Render:
    clone: Path
    project: Path
    # Prompts the target added since the project was generated, and the
    # default each one took.
    defaulted: dict[str, str]


def clone_template(template: str, version: Version, into: Path, git: Git) -> Path:
    # `template` comes from .pyfr-answers.yml or --template, so it is not
    # trusted input. `--` stops git from reading a value starting with `-`
    # (say `--upload-pack=...`) as an option instead of the repository.
    result = git.run(
        "clone", "--quiet", "--depth", "1", "--branch", str(version),
        "--", template, str(into), check=False,
    )  # fmt: skip
    if result.returncode != 0:
        raise UpdateError(
            f"could not clone {template} at {version}: {result.stderr.strip()}",
            "check the _template URL in .pyfr-answers.yml (or --template), "
            "and that you are online",
        )
    return into


def prompts(clone: Path) -> dict[str, object]:
    """The target's prompts: cookiecutter.json without the `_` keys."""
    data = json.loads((clone / "cookiecutter.json").read_text())
    if not isinstance(data, dict):
        raise UpdateError(
            f"{clone / 'cookiecutter.json'} is not a JSON object",
            "the template is broken at this version; pick another --to",
        )
    return {str(key): value for key, value in data.items() if not key.startswith("_")}


def render(
    clone: Path, version: Version, recorded: answers.Answers, output_dir: Path
) -> Render:
    # Imported here so the other modules' unit tests need no cookiecutter.
    from cookiecutter.main import cookiecutter

    declared = prompts(clone)
    extra, defaulted = answers.context(recorded, declared)
    # PYFR_REGEN: the target's post-generation hook prunes and stops -- no
    # git init, no uv sync (the hook's own contract, scripts/regen.py sets
    # it the same way). Restored afterwards, whatever happens.
    previous = os.environ.get("PYFR_REGEN")
    os.environ["PYFR_REGEN"] = "1"
    try:
        project = Path(
            cookiecutter(
                str(clone),
                no_input=True,
                extra_context=extra,
                output_dir=str(output_dir),
                # Never read ~/.cookiecutterrc: a contributor's defaults
                # must not reach a project's update.
                default_config=True,
            )
        )
    except Exception as exc:
        # cookiecutter's own hierarchy, and ValueError for a recorded
        # choice the target no longer offers; the hook's message went to
        # stderr already.
        raise UpdateError(
            f"the template at {version} could not be rendered: {exc}",
            "the message names the recorded answer the template refused; "
            f"change it in {answers.FILE}, or pick another --to",
        ) from exc
    finally:
        if previous is None:
            os.environ.pop("PYFR_REGEN", None)
        else:
            os.environ["PYFR_REGEN"] = previous
    return Render(clone, project, _defaults(project, declared, defaulted))


def _defaults(
    project: Path, declared: dict[str, object], names: list[str]
) -> dict[str, str]:
    """What each defaulted prompt became: read from the render's answers
    file, or cookiecutter.json's raw default when that file lacks it."""
    written: dict[str, str] = {}
    file = project / answers.FILE
    if file.is_file():
        data = yaml.safe_load(file.read_text())
        if isinstance(data, dict):
            written = {str(key): str(value) for key, value in data.items()}
    defaults: dict[str, str] = {}
    for name in names:
        raw = declared[name]
        fallback = raw[0] if isinstance(raw, list) and raw else raw
        defaults[name] = written.get(name, str(fallback))
    return defaults
