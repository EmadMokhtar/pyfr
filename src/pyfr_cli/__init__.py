"""pyfr-cli: bring a project generated from PyFr up to a newer template version.

`pyfr update` re-renders the template at the target version with the answers
the project recorded, commits the result on the `template` branch, and merges
that branch in (M8 design, section 4). `pyfr update-check` says whether a
newer version exists.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pyfr-cli")
except PackageNotFoundError:  # a checkout that was never installed
    __version__ = "0.0.0"
