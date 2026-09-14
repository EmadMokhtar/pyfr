"""The `pyfr` command."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from pyfr_cli import __version__
from pyfr_cli.errors import UpdateError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfr",
        description="Keep a project generated from PyFr up to date with the template.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_subparsers(dest="command", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        raise UpdateError(f"unknown command {args.command}", "run pyfr --help")
    except UpdateError as exc:
        if os.environ.get("PYFR_DEBUG"):
            raise
        print(f"error: {exc.cause}", file=sys.stderr)
        print(f"  fix: {exc.fix}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
