"""The `pyfr` command."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pyfr_cli import __version__, update
from pyfr_cli.errors import UpdateError

TEMPLATE_HELP = "the template repository (default: _template in .pyfr-answers.yml)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfr",
        description="Keep a project generated from PyFr up to date with the template.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "update", help="pull in a newer template version through a git merge"
    )
    run.add_argument(
        "--to", metavar="VERSION", help="the version to update to (default: the newest)"
    )
    run.add_argument(
        "--no-push",
        action="store_true",
        help="do not push the template branch to origin (the next run will)",
    )
    run.add_argument("--template", metavar="URL", help=TEMPLATE_HELP)

    check = commands.add_parser(
        "update-check", help="exit 1 when a newer template version exists"
    )
    check.add_argument(
        "--json", action="store_true", help="print a JSON object instead of a sentence"
    )
    check.add_argument("--template", metavar="URL", help=TEMPLATE_HELP)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project = Path.cwd()
    try:
        if args.command == "update":
            options = update.Options(
                to=args.to, push=not args.no_push, template=args.template
            )
            return update.update(project, options, sys.stdout)
        options = update.Options(template=args.template)
        return update.check(project, options, sys.stdout, as_json=args.json)
    except UpdateError as exc:
        if os.environ.get("PYFR_DEBUG"):
            raise
        print(f"error: {exc.cause}", file=sys.stderr)
        print(f"  fix: {exc.fix}", file=sys.stderr)
        return 2
    except OSError as exc:
        if os.environ.get("PYFR_DEBUG"):
            raise
        print(f"error: {exc}", file=sys.stderr)
        print(
            "  fix: check the paths and permissions the message names, then run again",
            file=sys.stderr,
        )
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
