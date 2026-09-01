# Why a template, not a framework

PyFr v1 is a pure cookiecutter template. All code is generated into your
repository and owned entirely by your team. Nothing is published to a package
index, and a generated service imports no PyFr package.

That is a deliberate reversal of how this project was first described, and the
reasoning is worth stating plainly.

## The framework option, and its cost

The obvious design is a library: a `pyfr` package on PyPI that services
install and import, with the shared machinery — the settings loader, the
logging chain, the health endpoints, the error handler — living inside it.

It has a real advantage. A fix ships once, and every service picks it up on
the next upgrade.

It also carries a cost that is easy to underestimate. A library's public
interface is a promise. Once three teams import a function, its signature is
frozen for years, whether or not it turned out to be the right shape. And the
right shape is exactly what nobody knows yet: the abstraction boundaries that
matter only become visible once several real services have pushed against
them.

Guessing those boundaries today means maintaining backward-compatibility
promises for abstractions that have never met a real requirement.

## The decision

Ship a template. Extract a library later, once three to five real services
exist and the parts nobody ever edits are visible. **Those** are the parts
worth extracting, and by then their shape will have been established by use
rather than by guesswork.

The practical effect: you can read every line of your service, change any of
it, and delete what you do not need. There is no framework to upgrade, no
version matrix, and no behaviour hidden inside a package you did not write.

## The obvious objection

A template hands you a copy. A fix made in PyFr after you generated does not
reach you. Multiply that across a dozen services and you have a dozen slightly
different copies of the same bug.

This is the standard reason teams choose a library, and it would be decisive
if it were not addressed.

## How the copy problem is solved

M8 makes a generated project able to pull in later template versions through
an ordinary git merge.

Generation records the answers you gave in a file in your repository. A
*vendor branch* holds pristine template output and nothing else — no local
edits. Updating means regenerating that branch at the newer template version
and merging it into your main branch.

Because git has a real merge base — the template output you originally started
from — it can tell "the template changed this" apart from "you changed this".
Your edits survive. Template fixes arrive. Conflicts appear only where both
sides genuinely changed the same lines, and git reports them the way it
reports any other conflict, with tools your team already knows.

One consequence is worth calling out, because it is the part naive copying
gets wrong: **code you deleted stays deleted.** Delete the example orders
slice, and a later update does not helpfully restore it, because the merge
base records that it was there and that you removed it.

Some paths are excluded from the merge entirely — the ones every team rewrites
immediately. Merging those would produce a conflict on every update until
people stopped updating, which is the actual failure mode this design is
avoiding.

This is what makes owning your code affordable rather than merely cheap to
start.

## What was considered and rejected

**[Copier](https://copier.readthedocs.io/)** has project updates built in and
solves this problem directly. It was rejected for an ecosystem reason, not a
technical one: Backstage — the developer portal many organisations use to
create services from a catalogue — ships a first-party cookiecutter action
and has no equivalent for Copier. Choosing Copier means writing and
maintaining that integration.

**[cruft](https://cruft.github.io/cruft/)** adds update support to cookiecutter
templates, which is exactly the gap. It was rejected because it has been
largely dormant, and an update mechanism is not a component to make load-bearing
on an unmaintained dependency.

The git vendor branch needs no third-party update tool at all. It uses merge
machinery that git has had for decades and that every team already understands.

## The narrow backend matrix

PyFr will ship adapters for PostgreSQL, Redis, and S3-compatible object
storage. Each is optional. MySQL, MongoDB, Memcached, Google Cloud Storage and
Azure Blob are **not** included.

The reason is the same instinct as everything above: a small number of
adapters that are genuinely finished and tested beats a long list of
half-working ones. A team on MySQL writes one adapter against a documented
port, using the shipped PostgreSQL adapter as a worked example — see
[Add a backend](../guides/add-a-backend.md).

Object storage is one adapter rather than several, because Amazon S3, MinIO,
Cloudflare R2, Ceph and Backblaze B2 all speak the same protocol. One adapter
with a configurable endpoint covers all of them: MinIO locally, real S3 in
production, no code change.

## The build order

The template is being built in three phases, in a specific order.

**Phase A (M0–M6)** builds the reference service as ordinary Python, with no
template placeholders anywhere. Every hard problem — the database adapter, the
telemetry wiring, the dashboards — is solved as a normal engineering problem.

**Phase B (M7)** converts it into the template in one focused pass.

**Phase C**, permanently after that, makes the template the source of truth.
`examples/reference-service/` is regenerated from the template, and the build
fails if the result differs from what is committed.

The rule behind the ordering: **never debug Jinja and Python at the same
time.** A bug in generated code, in a language full of `{{ }}` placeholders,
is far harder to find than the same bug in plain Python.

Phase C also buys something a reviewer feels every day. Every pull request
that changes the template shows the *generated output* as a readable diff. You
see what a template change did to real files, not only what it did to the
placeholders.
