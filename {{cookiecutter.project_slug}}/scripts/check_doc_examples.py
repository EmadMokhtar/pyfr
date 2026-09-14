#!/usr/bin/env python3
"""Run the documentation's marked shell examples against a live service.

Spec 10.3 asks for a check that catches documentation that is WRONG rather
than merely old. A stale sentence is a nuisance; a `curl` example that
404s is a reader concluding the software is broken.

Opt-in by design. A block runs only when the line before its fence is
exactly `<!-- exec -->`. Most fenced blocks here are file contents,
fragments of output, or commands that would modify the reader's machine,
so "run everything" would mean a wall of exclusions -- and an exclusion
list is a place for a broken example to hide.

Stdlib only: it runs inside the service's environment via
`just docs-examples`, and adding a dependency to that project for a
documentation check would be the wrong trade.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

MARKER = "<!-- exec -->"

# The marker, then a bash fence, then the body up to the closing fence.
_BLOCK = re.compile(
    rf"^{re.escape(MARKER)}\n```(?:bash|shell|console)\n(.*?)^```",
    re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class Example:
    """One runnable block, with enough context to name it in a failure."""

    path: str
    line: int
    body: str


def find_examples(root: Path) -> list[Example]:
    """Every marked block under `root`, in file then document order."""
    examples: list[Example] = []
    for path in sorted(root.rglob("*.md")):
        # `superpowers` in parts, not a path prefix: `just docs-examples`
        # passes `docs`, but a caller can still pass a relative root with
        # `..` segments, so a prefix test would silently stop excluding
        # the archive.
        if "superpowers" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in _BLOCK.finditer(text):
            examples.append(
                Example(
                    path=path.as_posix(),
                    line=text[: match.start()].count("\n") + 1,
                    body=match.group(1),
                )
            )
    return examples


def run(example: Example) -> tuple[bool, str]:
    """Run one block under `bash -euo pipefail`, capturing everything.

    `-e` matters more than it looks: without it a multi-command block
    reports the exit status of its LAST command only, so a broken `curl`
    followed by a working `echo` passes.
    """
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", example.body],
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = completed.stdout + completed.stderr
    return completed.returncode == 0, output


def main(argv: Sequence[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path("docs")
    examples = find_examples(root)
    if not examples:
        sys.stderr.write(
            f"No `{MARKER}` blocks found under {root}. Either the marker "
            f"was renamed or the examples were removed; both are bugs.\n"
        )
        return 1

    failures = 0
    for example in examples:
        ok, output = run(example)
        location = f"{example.path}:{example.line}"
        if ok:
            print(f"  ok    {location}")
        else:
            failures += 1
            print(f"  FAIL  {location}")
            print("".join(f"        {line}\n" for line in output.splitlines()))

    print(f"\n{len(examples) - failures}/{len(examples)} examples passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
