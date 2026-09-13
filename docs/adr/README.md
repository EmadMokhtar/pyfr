---
last_reviewed: 2026-09-13
---

# Decision records

Each page here records one of PyFr's own decisions: what was decided, when,
why, and what it cost. They are short on purpose. The full reasoning lives
in the
[design specification](https://github.com/EmadMokhtar/pyfr/tree/main/docs/superpowers),
and each record links to the section that argues its case.

## Why they are never edited

An accepted record is history. It says what was decided on a date, given
what was known then. Changing your mind means writing a **new** record and
marking the old one superseded — never rewriting the old one, which
destroys the only account of why the software is the way it is.

For the same reason, records are exempt from the review-date warning that
covers every other page on this site. A decision does not go stale.

## The records

| | Record | Decided |
|---|---|---|
| 0002 | [cookiecutter over Copier and cruft](0002-cookiecutter-over-copier-and-cruft.md) | M0 |
| 0003 | [uv, not pip or Poetry](0003-uv-over-pip-and-poetry.md) | M0 |
| 0017 | [The template is the source of truth, and a golden diff proves it](0017-the-template-is-the-source-of-truth.md) | M7 |

Every other decision belongs to the reference service — the project this
template generates — and is recorded on
[its own site](https://emadmokhtar.github.io/pyfr/reference-service/adr/).
