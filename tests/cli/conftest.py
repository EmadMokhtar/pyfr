"""Every pyfr-cli test runs git in isolation from the contributor's machine."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Neither the contributor's global git configuration (commit signing,
    # hooks, an excludes file) nor the system one reaches the repositories
    # these tests build or the git the tool runs -- the same isolation as
    # tests/test_regen.py. The tool inherits the environment, so this
    # covers its subprocesses too.
    config = tmp_path / "gitconfig"
    config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
