"""Migration scripts: updates/<version>/before.py and after.py in the template.

Some template changes cannot be expressed as a merge -- a file that moves,
a setting that changes shape. For each version in (recorded, target] the
template may ship a `before.py`, run on the project's tree before the
merge, and an `after.py`, run after it (spec section 6; updates/README.md
is the contract for the scripts' authors).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from pyfr_cli.errors import UpdateError
from pyfr_cli.versions import Version


@dataclass(frozen=True)
class Migration:
    version: Version
    before: Path | None
    after: Path | None


def discover(clone: Path, after: Version, up_to: Version) -> list[Migration]:
    """The migrations for versions in (after, up_to], oldest first."""
    updates = clone / "updates"
    if not updates.is_dir():
        return []
    found: list[Migration] = []
    for entry in updates.iterdir():
        if not entry.is_dir():
            continue
        try:
            version = Version.parse(entry.name)
        except ValueError:
            continue
        # Exactly vX.Y.Z: the v is required, and no zero padding.
        if entry.name != str(version) or not after < version <= up_to:
            continue
        before, after_script = entry / "before.py", entry / "after.py"
        found.append(
            Migration(
                version,
                before if before.is_file() else None,
                after_script if after_script.is_file() else None,
            )
        )
    return sorted(found, key=lambda migration: migration.version)


def run_script(
    script: Path,
    project: Path,
    from_version: Version,
    to_version: Version,
    out: TextIO,
) -> None:
    """One script, in the project root, with the update's versions in the
    environment. `--no-project`: scripts are standard-library only, and a
    project sync here would be slow and would fail in a fresh checkout."""
    label = f"{script.parent.name}/{script.name}"
    out.write(f"migrations: {label}\n")
    env = {
        **os.environ,
        "PYFR_UPDATE_FROM": str(from_version),
        "PYFR_UPDATE_TO": str(to_version),
    }
    result = subprocess.run(
        ["uv", "run", "--no-project", "python", str(script)],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        out.write(result.stdout)
    if result.returncode != 0:
        raise UpdateError(
            f"{label} failed (exit {result.returncode}): {result.stderr.strip()}",
            "fix what it reports; `git reset --hard HEAD` reverts what it "
            "changed, then run pyfr update again",
        )
    # A warning the script printed is worth seeing when it succeeds too.
    if result.stderr:
        out.write(result.stderr)


def run_before(
    migrations: list[Migration],
    project: Path,
    from_version: Version,
    to_version: Version,
    out: TextIO,
) -> None:
    for migration in migrations:
        if migration.before is not None:
            run_script(migration.before, project, from_version, to_version, out)


def run_after(
    migrations: list[Migration],
    project: Path,
    from_version: Version,
    to_version: Version,
    out: TextIO,
) -> None:
    for migration in migrations:
        if migration.after is not None:
            run_script(migration.after, project, from_version, to_version, out)
