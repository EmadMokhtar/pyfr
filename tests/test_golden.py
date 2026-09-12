"""The golden diff: rendering the template with the reference answers
reproduces examples/reference-service/ byte for byte (uv.lock excepted).

The same command CI's `golden` job runs. It fails with the list of files
and a unified diff of the first, so a hand edit to the example is caught
with its location, not a bare "mismatch".
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_example_matches_the_template() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "regen.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
