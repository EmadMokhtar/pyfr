#!/usr/bin/env python3
"""Regenerate examples/reference-service from the template -- or check it, or
adopt its edits back.

The template body, {{cookiecutter.project_slug}}/, is the only source of
truth; examples/reference-service/ is rendered from it with the answers in
tests/reference-answers.yaml (spec M7-1). Three modes:

  regen.py            render and sync the render into the example
  regen.py --check    render and compare; exit 1 on any difference
  regen.py --adopt    copy each line changed in the example back into the
                      template file that renders it, then check; then
                      copy the root workflows' action pins into the
                      template's workflows and regenerate

`--adopt` exists for Dependabot (spec M7-10): it edits the rendered example
because it cannot parse Jinja. A pin line never contains Jinja, so the
replacement is literal; any other shape of change is refused with the file
name, and is made in the template by hand.

Action pins go the other way: Dependabot's github-actions updates land in
the root's .github/workflows only, so --adopt copies each bumped `uses:`
ref from there into the template's workflows. The example's own
`.github/workflows/` never reaches `adopt()`: Dependabot does not read
it, and its `uses:` lines repeat, which `adopt()` would refuse.

The render runs with PYFR_REGEN set, so the post-generation hook prunes and
stops: no git init, no uv sync, no network. uv.lock is the one file outside
the comparison -- resolver output, not template content (spec M7-4).
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jinja2 import Environment

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_BODY = ROOT / "{{cookiecutter.project_slug}}"
EXAMPLE = ROOT / "examples" / "reference-service"
ANSWERS_FILE = ROOT / "tests" / "reference-answers.yaml"

# Resolver output, not template content (spec M7-4).
EXCLUDED = frozenset({"uv.lock"})

# Dependabot's github-actions ecosystem reads /.github/workflows only, so its
# bumps land in the root's workflows; the template's workflows follow them
# through --adopt (spec section 8, amended in PR 3).
ROOT_WORKFLOWS = ROOT / ".github" / "workflows"
TEMPLATE_WORKFLOWS = TEMPLATE_BODY / ".github" / "workflows"
# A SHA pin's trailing `# vN` comment is not compared or rewritten; the
# repository pins by tag.
USES = re.compile(
    r"^(?P<head>\s*-?\s*uses:\s*)(?P<action>[\w.-]+/[\w./-]+)@"
    r"(?P<ref>[^\s#]+)(?P<tail>.*)$"
)

# The post-generation hook keeps the chosen LICENSE.<choice> as LICENSE, so
# that one rendered path maps back to a template path the answers decide.
LICENCE_FILES = {
    "Apache-2.0": "LICENSE.Apache-2.0",
    "MIT": "LICENSE.MIT",
    "MPL-2.0": "LICENSE.MPL-2.0",
    "Proprietary": "LICENSE.Proprietary",
}


class AdoptError(Exception):
    """A change in the example that --adopt cannot express in the template."""


@dataclass
class Comparison:
    missing: list[str] = field(default_factory=list)  # in the render, not the example
    extra: list[str] = field(default_factory=list)  # in the example, not the render
    differing: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.missing or self.extra or self.differing)


def load_answers(path: Path = ANSWERS_FILE) -> dict[str, str]:
    with path.open() as handle:
        answers = yaml.safe_load(handle)
    return {key: str(value) for key, value in answers.items()}


def render(template_root: Path, answers: dict[str, str], output_dir: Path) -> Path:
    # Imported here so the unit tests of compare/sync/adopt need no
    # cookiecutter at all.
    from cookiecutter.main import cookiecutter

    os.environ["PYFR_REGEN"] = "1"
    return Path(
        cookiecutter(
            str(template_root),
            no_input=True,
            extra_context=answers,
            output_dir=str(output_dir),
            # Never read ~/.cookiecutterrc: a contributor's defaults must
            # not reach a render the golden diff compares.
            default_config=True,
        )
    )


def files_under(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }


def example_files(example: Path) -> set[str]:
    """The example's files as git sees them: tracked, plus untracked files
    .gitignore does not cover.

    So a freshly rendered file counts as present before `git add`, a stray
    untracked file counts as extra, and .venv, the caches and everything
    else ignored never count. Restricted to what is on disk, so a deletion
    counts as gone before it is staged.
    """
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=example,
        check=True,
        capture_output=True,
    ).stdout
    return {
        name
        for name in listed.decode().split("\0")
        if name and (example / name).is_file()
    }


def compare(rendered: Path, example: Path) -> Comparison:
    wanted = files_under(rendered) - EXCLUDED
    present = example_files(example) - EXCLUDED
    comparison = Comparison(
        missing=sorted(wanted - present),
        extra=sorted(present - wanted),
    )
    for name in sorted(wanted & present):
        if (rendered / name).read_bytes() != (example / name).read_bytes():
            comparison.differing.append(name)
    return comparison


def sync(rendered: Path, example: Path) -> None:
    wanted = files_under(rendered) - EXCLUDED
    for name in wanted:
        target = example / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((rendered / name).read_bytes())
    # Only leftovers git can see go: ignored files (.venv, the caches) and
    # uv.lock are never the render's to remove.
    for name in example_files(example) - EXCLUDED - wanted:
        stale = example / name
        stale.unlink()
        parent = stale.parent
        while parent != example and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


def template_paths(template_body: Path, answers: dict[str, str]) -> dict[str, str]:
    """Rendered relative path -> template relative path."""
    # Renders file NAMES, never HTML: autoescape would corrupt a path.
    env = Environment(keep_trailing_newline=True)  # noqa: S701
    mapping: dict[str, str] = {}
    for name in files_under(template_body):
        rendered_name = env.from_string(name).render(cookiecutter=answers)
        mapping[rendered_name] = name
    for choice, file_name in LICENCE_FILES.items():
        mapping.pop(file_name, None)
        if answers.get("license") == choice:
            mapping["LICENSE"] = file_name
    return mapping


def adopt(
    rendered: Path,
    example: Path,
    template_body: Path,
    answers: dict[str, str],
) -> list[str]:
    comparison = compare(rendered, example)
    if comparison.missing or comparison.extra:
        raise AdoptError(
            "adopt handles changed files only; "
            f"missing={comparison.missing} extra={comparison.extra}"
        )
    mapping = template_paths(template_body, answers)
    adopted: list[str] = []
    for name in comparison.differing:
        if name not in mapping:
            raise AdoptError(
                f"{name}: no template file renders this path; "
                "make this change in the template by hand"
            )
        template_file = template_body / mapping[name]
        old_lines = (rendered / name).read_text().splitlines(keepends=True)
        new_lines = (example / name).read_text().splitlines(keepends=True)
        template_lines = template_file.read_text().splitlines(keepends=True)
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            if tag != "replace":
                raise AdoptError(
                    f"{name}: lines were {tag}d, not replaced; "
                    "make this change in the template by hand"
                )
            old = old_lines[i1:i2]
            # Whole lines, not a substring: a comment quoting the changed
            # line must neither be replaced nor count as a second match.
            starts = line_runs(template_lines, old)
            if len(starts) != 1:
                raise AdoptError(
                    f"{name}: the changed lines must appear exactly once in "
                    f"{mapping[name]} (found {len(starts)}); "
                    "make this change in the template by hand"
                )
            template_lines[starts[0] : starts[0] + len(old)] = new_lines[j1:j2]
        template_file.write_text("".join(template_lines))
        adopted.append(name)
    return adopted


def line_runs(lines: list[str], block: list[str]) -> list[int]:
    """Every index at which `block` occurs in `lines` as a contiguous run."""
    width = len(block)
    return [
        start
        for start in range(len(lines) - width + 1)
        if lines[start : start + width] == block
    ]


def action_pins(workflows: Path) -> dict[str, str]:
    """`owner/repo` -> ref for every `uses:` line in the directory's *.yml."""
    pins: dict[str, str] = {}
    for path in sorted(workflows.glob("*.yml")):
        for line in path.read_text().splitlines():
            match = USES.match(line)
            if match is None:
                continue
            action, ref = match["action"], match["ref"]
            if pins.setdefault(action, ref) != ref:
                raise AdoptError(
                    f"{action} is pinned at both {pins[action]} and {ref} "
                    f"under {workflows}; pin it once"
                )
    return pins


def adopt_action_pins(source: Path, target: Path) -> list[str]:
    """Rewrite each `uses:` ref under `target` to the ref `source` pins it at.

    Only the ref changes: indentation, the action name and any trailing
    comment stay. An action `source` does not use is left alone. Returns the
    names of the files it rewrote.
    """
    pins = action_pins(source)
    changed: list[str] = []
    for path in sorted(target.glob("*.yml")):
        lines = path.read_text().splitlines(keepends=True)
        rewritten: list[str] = []
        for line in lines:
            match = USES.match(line.rstrip("\n"))
            if (
                match is not None
                and pins.get(match["action"], match["ref"]) != match["ref"]
            ):
                line = (
                    f"{match['head']}{match['action']}@"
                    f"{pins[match['action']]}{match['tail']}\n"
                )
            rewritten.append(line)
        if rewritten != lines:
            path.write_text("".join(rewritten))
            changed.append(path.name)
    return changed


def report(comparison: Comparison, rendered: Path, example: Path) -> None:
    for name in comparison.missing:
        print(f"missing from the example: {name}")
    for name in comparison.extra:
        print(f"tracked in the example but not in the template: {name}")
    for name in comparison.differing:
        print(f"differs: {name}")
    if comparison.differing:
        first = comparison.differing[0]
        diff = difflib.unified_diff(
            (example / first).read_text().splitlines(keepends=True),
            (rendered / first).read_text().splitlines(keepends=True),
            fromfile=f"examples/reference-service/{first}",
            tofile=f"rendered/{first}",
        )
        sys.stdout.writelines(diff)
    print()
    print("The template is the source of truth: edit {{cookiecutter.project_slug}}/")
    print("and run `just regen`. Never edit examples/reference-service/ by hand.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="compare; do not write")
    mode.add_argument(
        "--adopt",
        action="store_true",
        help="copy the example's changed lines into the template, then compare",
    )
    args = parser.parse_args(argv)

    answers = load_answers()
    with tempfile.TemporaryDirectory() as scratch:
        rendered = render(ROOT, answers, Path(scratch))
        if args.adopt:
            adopted = adopt(rendered, EXAMPLE, TEMPLATE_BODY, answers)
            for name in adopted:
                print(f"adopted into the template: {name}")
            again = Path(scratch) / "again"
            again.mkdir()
            rendered = render(ROOT, answers, again)
            comparison = compare(rendered, EXAMPLE)
            if not comparison.clean:
                report(comparison, rendered, EXAMPLE)
                return 1
            # The other direction: Dependabot bumps the root workflows'
            # action pins, the template's workflows follow, and the example
            # is regenerated so the golden diff stays clean.
            repinned = adopt_action_pins(ROOT_WORKFLOWS, TEMPLATE_WORKFLOWS)
            for name in repinned:
                print(f"adopted the root's action pins into .github/workflows/{name}")
            if repinned:
                repinned_render = Path(scratch) / "repinned"
                repinned_render.mkdir()
                sync(render(ROOT, answers, repinned_render), EXAMPLE)
            print("examples/reference-service matches the template.")
            return 0
        if args.check:
            comparison = compare(rendered, EXAMPLE)
            if comparison.clean:
                print("examples/reference-service matches the template.")
                return 0
            report(comparison, rendered, EXAMPLE)
            return 1
        sync(rendered, EXAMPLE)
        print("examples/reference-service regenerated.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
