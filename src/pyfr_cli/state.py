"""A paused update, recorded in .git/ so a re-run of the same command resumes.

Written when a merge stops on conflicts and before the after-scripts run;
deleted when the update completes. Inside .git/, so never committed
(spec section 4.8).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pyfr_cli.errors import UpdateError
from pyfr_cli.git import Git
from pyfr_cli.versions import Version

FILE = "pyfr-update.json"
Phase = Literal["merging", "after-scripts"]
PHASES: tuple[Phase, ...] = ("merging", "after-scripts")


@dataclass(frozen=True)
class State:
    from_version: Version
    to_version: Version
    phase: Phase
    # The sha of the HEAD the tool grafted an extra parent onto for the
    # merge (spec section 4.7), so a run that died before deleting the
    # graft is cleaned up by the next one.
    graft: str | None = None


def path(git: Git) -> Path:
    return git.git_dir() / FILE


def load(git: Git) -> State | None:
    file = path(git)
    if not file.exists():
        return None
    fix = f"delete {file} if no update is in progress, then run again"
    try:
        data = json.loads(file.read_text())
        phase = data["phase"]
        if phase not in PHASES:
            raise ValueError(f"unknown phase {phase!r}")
        return State(
            Version.parse(data["from"]),
            Version.parse(data["to"]),
            "merging" if phase == "merging" else "after-scripts",
            data.get("graft"),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise UpdateError(f"{FILE} is unreadable: {exc}", fix) from exc


def save(git: Git, state: State) -> None:
    record = {
        "from": str(state.from_version),
        "to": str(state.to_version),
        "phase": state.phase,
        "graft": state.graft,
    }
    path(git).write_text(json.dumps(record, indent=2) + "\n")


def clear(git: Git) -> None:
    path(git).unlink(missing_ok=True)
