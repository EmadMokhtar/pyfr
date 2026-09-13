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
import shutil
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

DATABASE = "{{ cookiecutter.database }}"
CACHE = "{{ cookiecutter.cache }}"
OBJECT_STORAGE = "{{ cookiecutter.object_storage }}"
PACKAGE = "{{ cookiecutter.package_name }}"

# Whole files and directories that belong to one backend. Jinja removes lines
# inside mixed files; everything here is deleted outright when its answer is
# "none". Directories end with "/". tests/test_generation.py carries the same
# table and asserts that each path exists exactly when its backend is chosen.
# Only the two declared values can arrive here: cookiecutter refuses an
# override outside a choice list before any hook runs, so "not none" below
# always means the backend's own value (tests/test_hooks.py pins that).
PRUNED: dict[str, list[str]] = {
    "database": [
        "migrations/",
        "schema.sql",
        "Dockerfile.migrations",
        ".sqlfluff",
        f"src/{PACKAGE}/infrastructure/db/",
        "tests/unit/test_db_mappers.py",
        "tests/unit/test_engine.py",
        "tests/unit/test_migration_files.py",
        "tests/unit/test_order_repository.py",
        "tests/integration/test_order_repository.py",
        "tests/integration/test_db_instrumentation.py",
        "tests/integration/test_schema_drift.py",
        "tests/integration/test_schema_gates.py",
    ],
    "cache": [
        f"src/{PACKAGE}/infrastructure/cache/",
        "tests/unit/test_cached_order_repository.py",
        "tests/integration/test_cached_order_repository.py",
        "tests/integration/test_redis_instrumentation.py",
    ],
    "object_storage": [
        f"src/{PACKAGE}/infrastructure/storage/",
        "tests/integration/test_receipt_store.py",
    ],
}
ANSWERS = {"database": DATABASE, "cache": CACHE, "object_storage": OBJECT_STORAGE}


def prune_backends(root: Path) -> None:
    for key, answer in ANSWERS.items():
        if answer != "none":
            continue
        for relative in PRUNED[key]:
            path = root / relative.rstrip("/")
            if not path.exists():
                # The table and the tree have diverged; fail loudly so the
                # generation tests catch it before a user does.
                sys.exit(f"pruning: {relative} is missing from the template body")
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()


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
    prune_backends(root)
    remove_empty_directories(root)
    if os.environ.get("PYFR_REGEN"):
        return 0
    set_up(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
