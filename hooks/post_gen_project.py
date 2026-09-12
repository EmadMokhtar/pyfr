"""Keep what the answers chose; then, outside regeneration, set the project up.

Cookiecutter runs this with the generated project as the working directory,
after rendering it through Jinja, so LICENCE below is a literal.

Two halves. Pruning always runs. The side effects -- git init, uv sync, the
pre-commit hook, a first commit -- run only when PYFR_REGEN is unset:
scripts/regen.py sets it so a render is a pure function of the template and
the answers. Every side effect is best effort: a failure prints the command
to run later and the hook still exits 0, because an offline laptop must
not receive a half-set-up project reported as a failed one.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LICENCE = "{{ cookiecutter.license }}"
LICENCE_FILES = {
    "Apache-2.0": "LICENSE.Apache-2.0",
    "MIT": "LICENSE.MIT",
    "MPL-2.0": "LICENSE.MPL-2.0",
    "Proprietary": "LICENSE.Proprietary",
}


def keep_chosen_licence(root: Path) -> None:
    chosen = root / LICENCE_FILES[LICENCE]
    if not chosen.is_file():
        # The pruning table and the tree have diverged. Fail here, loudly,
        # so the generation tests catch it before a user does.
        sys.exit(f"pruning: {chosen.name} is missing from the template body")
    chosen.rename(root / "LICENSE")
    for name in LICENCE_FILES.values():
        path = root / name
        if path.exists():
            path.unlink()


def remove_empty_directories(root: Path) -> None:
    for directory in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()


def best_effort(command: list[str], cwd: Path) -> bool:
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except (OSError, subprocess.CalledProcessError):
        print(f"Could not run `{' '.join(command)}`; run it later.")
        return False
    return True


def set_up(root: Path) -> None:
    # Each step on its own: a missing `git` must not stop `uv sync`, and a
    # failed `uv sync` (offline) must not stop the repository being made.
    initialised = best_effort(["git", "init", "-q"], root)
    best_effort(["uv", "sync"], root)
    best_effort(["uv", "run", "pre-commit", "install"], root)
    committed = (
        initialised
        and best_effort(["git", "add", "-A"], root)
        and best_effort(
            ["git", "commit", "-q", "-m", "chore: generate the project from pyfr"],
            root,
        )
    )
    if not committed:
        print("Run `git add -A && git commit` once the steps above succeed.")
    print()
    print("Next steps:")
    print(f"  cd {root.name}")
    print("  just up          # build the image and start the stack")
    print("  just check       # every fast gate")
    print("  see README.md for the rest")


def main() -> int:
    root = Path.cwd()
    keep_chosen_licence(root)
    remove_empty_directories(root)
    if os.environ.get("PYFR_REGEN"):
        return 0
    set_up(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
