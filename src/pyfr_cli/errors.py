"""The one error the command reports: a cause and a fix, one line each."""

from __future__ import annotations


class UpdateError(Exception):
    """Stops the run. `__main__` prints `cause` and `fix` and exits 2."""

    def __init__(self, cause: str, fix: str) -> None:
        super().__init__(cause)
        self.cause = cause
        self.fix = fix
