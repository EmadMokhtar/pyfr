# PyFr M8 PR 2 — The Generated Project's Side Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every project generated from the template the means to update itself: `just update` / `just update-check`, a `.pyfr-update-ignore`, a weekly `template-update.yml` workflow that opens a pull request (clean merge) or an issue (conflicts), and the how-to page every `pyfr` error message already points at.

**Architecture:** Everything in this PR lives in the template body `{{cookiecutter.project_slug}}/` and is therefore rendered into every generated project and, by `just regen`, into `examples/reference-service/`. The recipes are one-line wrappers over `uvx --from pyfr-cli@latest pyfr …` (PR 1's tool, on PyPI since v0.11.0); the workflow keeps every decision in the tool's exit codes and only pushes and talks to GitHub. The template repository's tests render the body for all eight backend combinations and assert the new files' shape; the golden diff keeps the example in step.

**Tech Stack:** cookiecutter/Jinja (the template body), `just`, GitHub Actions (`gh`, `jq`, `uvx`), MkDocs (the generated site), pytest + pytest-cookies (the generation tests), the existing `pyfr-cli` end-to-end test.

**Spec:** [`docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md`](../specs/2026-09-14-pyfr-m8-template-updates-design.md) — this PR implements sections 5 (5.1 recipes, 5.2 ignore file, 5.3 workflow, 5.4 token), 7.1 (generated-side documentation), 8.3 (generation tests) and 8.5's manual verification; section 9 lists it as PR 2. Section 8.2's scenario 6 ("from PR 2 on the file arrives with the update") lands here too.

## Global Constraints

- The template body is the only source of truth (ADR 0017): edit `{{cookiecutter.project_slug}}/…`, never `examples/reference-service/…`; run `just regen` after every body change and commit the regenerated example with it. CI's `golden` job fails otherwise.
- Jinja in the body: GitHub Actions' `${{ }}` and `just`'s `{{name}}` must sit inside `{%- raw %} … {%- endraw %}` blocks (the body's other workflows and `justfile` show the convention: the tag on its own line, with the `-` that strips the newline before it). `tests/test_generation.py::test_no_template_syntax_survives_any_combination` checks every rendered file; a workflow file must be listed in its `RAW_GUARDED_FILES`.
- Backend-conditional lines use `{%- if cookiecutter.database == "postgres" %} … {%- endif %}` (the `-` keeps the render free of blank lines).
- The rendered `.pyfr-update-ignore` must equal `pyfr_cli.ignore.default_text(package_name, database)` byte for byte — the tool's built-in default and the shipped file are one text.
- The recipes are exactly spec 5.1's; `uvx --from pyfr-cli@latest pyfr …` and `uvx --from pyfr-cli==X.Y.Z pyfr … --to vX.Y.Z` are verified to work with uv 0.11.12 and `pyfr-cli 0.11.0` on PyPI. Neither `pyfr-cli` nor `cookiecutter` enters the project's dependency groups.
- Every generated docs page opens with front matter: `last_reviewed: 2026-09-15` and, when it describes files, `covers:` with paths relative to the project root.
- Comments and prose in simple, direct English, matching the density and tone of the neighbouring text in each file. Conventional Commits (`feat(template): …`, `docs(template): …`, `test: …`, `docs(pyfr): …`); every commit ends with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. Pre-commit hooks run on commit; fix causes, never bypass.
- Gates after every task: `just test` (renders the eight combinations; a few minutes), `just regen-check`, `just precommit`. `just check` once at the end.
- The template-repository tests never touch the network for the new behaviour except where noted (the manual verification task).

## Verified facts (checked on 2026-09-15 in this checkout, branch `claude/m8-pr2-generated-side` at `edc445c` = `origin/main`, v0.11.0)

- `pyfr-cli 0.11.0` is on PyPI; `uvx --from pyfr-cli@latest pyfr --version` and `uvx --from pyfr-cli==0.11.0 pyfr --version` both print `pyfr 0.11.0` (uv 0.11.12).
- `pyfr update` (PR 1) prints stable lines: `ignore: no .pyfr-update-ignore; using the built-in default`, `ignore: installed .pyfr-update-ignore from the template`, `conflict: <path>`, `recorded: vX.Y.Z`, `template: not pushed (--no-push); push it before this update is merged: git push origin template`; `pyfr update-check --json` prints `{"recorded": "vA", "newest": "vB", "behind": true|false, "template": "<url>"}` and exits 0 current / 1 behind / 2 error. `pyfr update --no-push` skips only the push of `template`; a later `git push origin template` is what the workflow does instead.
- `pyfr_cli.ignore.default_text(package, database)` is `HEADER + (SCHEMA if database == "postgres" else "") + FOOTER.format(package=package)` — see `src/pyfr_cli/ignore.py`; every pattern carries a leading `/`; comments are on their own lines.
- The body's `justfile` writes `just` interpolations as `{% raw %}{{name}}{% endraw %}` (its `migrate-new` recipe); its `changelog` and `next-version` recipes sit at lines ~592–610, just before `up:`.
- The body's workflows wrap `${{ }}` lines in `{%- raw %}` / `{%- endraw %}` on their own lines (`docs.yml:56-58`, `nightly.yml:72-76`); `nightly.yml`'s schedule comment explains the off-the-hour minute; `release.yml` sets the git identity with `git config user.name "github-actions[bot]"` / `user.email "41898282+github-actions[bot]@users.noreply.github.com"` and uses `persist-credentials: false` because third-party actions run after its checkout.
- `tests/test_generation.py`: `COMBINATIONS` (eight dicts), `render(cookies, **answers)`, `combination_id`, `RAW_GUARDED_FILES` (the four workflows plus the justfile and three others); the "every rendered justfile parses" check runs `just --list --justfile <path>` (skipped when `just` is absent).
- `tests/test_site_nav.py` requires every page under a `docs/` tree to be in its `mkdocs.yml` nav; the body's nav has a `Guides:` section (`mkdocs.yml:82-86`).
- Generated docs front matter: `last_reviewed:` and `covers:` (a list; a directory prefix covers everything under it); `docs/contributing.md:129-148` documents it.
- The generated README's "Continuous integration and releases" section has a four-row workflow table and a "Five settings live in the GitHub interface" list whose third bullet is `RELEASE_TOKEN`; `docs/contributing.md:293-300` ("Repository settings") repeats "Five settings" and points at the README.
- `docs/reference/commands.md`'s "Supply chain" section ends with the `just changelog` and `just next-version` rows (lines 106–107).
- `.pre-commit-config.yaml`'s `check-yaml` excludes the template body (unrendered Jinja); the rendered example's workflows are checked.
- `tests/test_update_e2e.py` (PR 1) asserts `ignore: no .pyfr-update-ignore; using the built-in default` in the clean-update scenario (line 271) because the body had no ignore file; its "project's own ignore file" scenario writes the file itself (line 434).
- `gh`, `jq` and `git` are preinstalled on `ubuntu-latest`; `uvx` comes from `astral-sh/setup-uv@v7`.

## File structure

| Path (under `{{cookiecutter.project_slug}}/` unless noted) | Responsibility |
|---|---|
| `.pyfr-update-ignore` | The paths an update never touches — the tool's built-in default, shipped. |
| `.pyfr-answers.yml` | Comment wording only ("`just update` reads it"). |
| `justfile` | `update` and `update-check` recipes. |
| `.github/workflows/template-update.yml` | The weekly job: check → update `--no-push` → push → PR or issue. |
| `docs/guides/update-from-template.md` | The how-to every `pyfr` error message names. |
| `mkdocs.yml` | Nav entry for the guide. |
| `docs/reference/commands.md` | Two rows. |
| `docs/glossary.md` | `pyfr-cli`, `template` branch, `.pyfr-update-ignore` entries. |
| `README.md`, `docs/contributing.md` | Five workflows; the widened `RELEASE_TOKEN`; the sixth repository setting. |
| `tests/test_generation.py` (root) | New assertions: ignore file equals `default_text`; recipes present; workflow present and raw-guarded; guide present. |
| `tests/test_update_e2e.py` (root) | The body now ships the ignore file: scenario 1 no longer sees the built-in-default line; new scenario 6. |
| `docs/superpowers/specs/…m8…design.md` (root) | Amendment: 5.3's token handling (workflow token persisted, `RELEASE_TOKEN` in the push step only, `--no-push` + explicit pushes). |
| `examples/reference-service/…` (root) | Regenerated by `just regen`; never edited by hand. |

---

### Task 1: `.pyfr-update-ignore` in the template body

**Files:**
- Create: `{{cookiecutter.project_slug}}/.pyfr-update-ignore`
- Modify: `{{cookiecutter.project_slug}}/.pyfr-answers.yml` (the two comment lines)
- Test: `tests/test_generation.py`
- Regenerate: `examples/reference-service/`

**Interfaces:**
- Produces: a rendered `.pyfr-update-ignore` identical to `pyfr_cli.ignore.default_text(package_name, database)` for every combination.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_generation.py` (after `test_a_render_owns_its_commitizen`):

```python


@pytest.mark.parametrize("answers", COMBINATIONS, ids=combination_id)
def test_the_ignore_file_is_the_tool_s_built_in_default(cookies, answers) -> None:
    # `pyfr update` carries the same list as its fallback for a project
    # generated before the file existed (spec section 5.2, decision M8-5).
    # One text, two places: the body ships it, the tool embeds it.
    from pyfr_cli.ignore import default_text

    root = render(cookies, **answers)
    recorded = yaml.safe_load((root / ".pyfr-answers.yml").read_text())
    expected = default_text(recorded["package_name"], recorded["database"])
    assert (root / ".pyfr-update-ignore").read_text() == expected
    schema_lines = {"/migrations/", "/schema.sql"}
    present = set(expected.splitlines()) & schema_lines
    assert bool(present) == (answers["database"] == "postgres")
```

`yaml` is already imported by that file (check the import block; add `import yaml` if it is not).

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --group dev --group docs pytest tests/test_generation.py -k ignore_file -v`
Expected: FAIL for all eight — `FileNotFoundError: … .pyfr-update-ignore`.

- [ ] **Step 3: Write the body file**

`{{cookiecutter.project_slug}}/.pyfr-update-ignore` — this text must render to `default_text(...)` exactly; the `-` on the Jinja tags is what keeps the blank lines out:

```
# Paths `just update` leaves exactly as this project has them: yours from
# the first day, or artifacts of your code. Add paths as you diverge --
# one gitignore pattern per line, comments on their own lines.
# Everything not listed is template-owned and receives fixes by default.

# Written by the update itself.
/.pyfr-answers.yml
# This file.
/.pyfr-update-ignore
/README.md
/CHANGELOG.md
# Resolver output; run `uv lock` after an update that touched pyproject.toml.
/uv.lock
{%- if cookiecutter.database == "postgres" %}
# Your schema.
/migrations/
/schema.sql
{%- endif %}
# Artifacts of your code: the contract, and the baseline your release promotes.
/openapi.json
/openapi.baseline.json
# Your decisions.
/docs/adr/
# The example slice, then your business model.
/src/{{ cookiecutter.package_name }}/domain/
/src/{{ cookiecutter.package_name }}/services/
/src/{{ cookiecutter.package_name }}/api/v1/
```

Then in `{{cookiecutter.project_slug}}/.pyfr-answers.yml`, replace the first two comment lines

```
# Written by PyFr when this project was generated. M8's `just update` reads
# it to re-render the template at a newer version and merge the result;
```

with

```
# Written by PyFr when this project was generated. `just update` reads it
# to re-render the template at a newer version and merge the result;
```

- [ ] **Step 4: Run the test, then regenerate the example**

Run: `uv run --group dev --group docs pytest tests/test_generation.py -k ignore_file -v`
Expected: 8 PASS. If a combination differs by a blank line, compare `repr()` of both texts: the `{%- if` / `{%- endif %}` must sit on their own lines exactly as above.

Run: `just regen && git status --short`
Expected: `examples/reference-service/.pyfr-update-ignore` created and `examples/reference-service/.pyfr-answers.yml` modified; nothing else.

- [ ] **Step 5: Gates and commit**

Run: `just regen-check && just precommit`
Expected: `examples/reference-service matches the template.`; hooks pass.

```bash
git add '{{cookiecutter.project_slug}}/.pyfr-update-ignore' '{{cookiecutter.project_slug}}/.pyfr-answers.yml' tests/test_generation.py examples/reference-service/.pyfr-update-ignore examples/reference-service/.pyfr-answers.yml
git commit -m "feat(template): ship .pyfr-update-ignore, the update's built-in default

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `just update` and `just update-check`

**Files:**
- Modify: `{{cookiecutter.project_slug}}/justfile` (before `up:`)
- Modify: `{{cookiecutter.project_slug}}/docs/reference/commands.md` (after the `next-version` row)
- Test: `tests/test_generation.py`
- Regenerate: `examples/reference-service/`

**Interfaces:**
- Produces: recipes `update to=""` and `update-check` in every render.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_generation.py`:

```python


def test_the_update_recipes_wrap_pyfr_cli_from_pypi(cookies) -> None:
    # spec section 5.1: the newest release on PyPI is, by construction, the
    # newest template tag, so `@latest` runs the updater at the target
    # version; a pinned `to` pins both the tool and the target.
    root = render(cookies, **EVERYTHING_ON)
    justfile = (root / "justfile").read_text()
    assert "uvx --from pyfr-cli@latest pyfr update\n" in justfile
    assert "uvx --from pyfr-cli@latest pyfr update-check\n" in justfile
    assert 'uvx --from "pyfr-cli==${version}" pyfr update --to "v${version}"' in justfile
    # just's own interpolation survived Jinja: the recipe reads {{to}}.
    assert 'if [ -n "{{to}}" ]; then' in justfile
    # Neither tool enters the project's environment.
    pyproject = (root / "pyproject.toml").read_text()
    assert "pyfr-cli" not in pyproject
    assert "cookiecutter" not in pyproject
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --group dev --group docs pytest tests/test_generation.py -k update_recipes -v`
Expected: FAIL on the first assertion.

- [ ] **Step 3: Add the recipes**

In `{{cookiecutter.project_slug}}/justfile`, immediately before the `up:` recipe (after `next-version`'s body), insert:

```
# Pull in a newer template version through a git merge: `pyfr update`
# re-renders the template with this project's recorded answers, commits
# the result on the `template` branch, and merges it (docs/guides/
# update-from-template.md). It runs the updater at the target version --
# the newest release of pyfr-cli on PyPI is, by construction, the newest
# template tag -- and `@latest` makes uvx resolve that instead of reusing
# a cached older tool. `just update v0.12.0` pins both.
update to="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -n "{% raw %}{{to}}{% endraw %}" ]; then
        version="{% raw %}{{to}}{% endraw %}"; version="${version#v}"
        uvx --from "pyfr-cli==${version}" pyfr update --to "v${version}"
    else
        uvx --from pyfr-cli@latest pyfr update
    fi

# Exit non-zero when a newer template version exists. The weekly workflow
# (.github/workflows/template-update.yml) runs this first.
update-check:
    uvx --from pyfr-cli@latest pyfr update-check

```

In `{{cookiecutter.project_slug}}/docs/reference/commands.md`, after the `just next-version` row (line ~107), add:

```
| `just update [VERSION]` | Pull in a newer template version through a git merge, the newest by default. Stops with exit 1 on conflicts; run it again after resolving them. Needs the network. See [Update from the template](../guides/update-from-template.md). |
| `just update-check` | Exit 1 when a newer template version exists, 0 when this project is current. The weekly `template-update.yml` runs it first. |
```

- [ ] **Step 4: Run the tests, then regenerate**

Run: `uv run --group dev --group docs pytest tests/test_generation.py -k "update_recipes or justfile or template_syntax" -v`
Expected: PASS — including the existing parse check over every rendered `justfile` and the Jinja-leftover check (the `{% raw %}` guards keep `{{to}}` out of the offenders).

Run: `just regen && git status --short`
Expected: `examples/reference-service/justfile` and `examples/reference-service/docs/reference/commands.md` modified.

- [ ] **Step 5: Try the rendered recipe once**

Run, from the example (network): `cd examples/reference-service && just update-check; echo "exit $?"; cd ../..`
Expected: `recorded v0.11.0, newest v0.11.0` and `exit 0` — the example records the version this checkout is at. (If `main` has released since, the exit is 1 and the newest is higher — either proves the recipe.)

- [ ] **Step 6: Gates and commit**

Run: `just regen-check && just precommit`

```bash
git add '{{cookiecutter.project_slug}}/justfile' '{{cookiecutter.project_slug}}/docs/reference/commands.md' tests/test_generation.py examples/reference-service/justfile examples/reference-service/docs/reference/commands.md
git commit -m "feat(template): add just update and just update-check

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `template-update.yml` — the weekly job

**Files:**
- Create: `{{cookiecutter.project_slug}}/.github/workflows/template-update.yml`
- Modify: `tests/test_generation.py` (`RAW_GUARDED_FILES`, one new test)
- Modify: `docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md` (section 5.3, the token paragraph)
- Regenerate: `examples/reference-service/`

**Interfaces:**
- Consumes: `pyfr update-check --json` (exit 0/1/2; keys `recorded`, `newest`, `behind`, `template`), `pyfr update --no-push` (exit 0 clean, 1 conflicts, 2 error; `conflict: <path>` lines).
- Produces: branch `pyfr/update-<newest>`, a pull request `chore: update template vA -> vB`, or an issue `chore: template vA -> vB conflicts`; `origin/template` pushed in both cases.

**Design decision carried from the spec, with one amendment.** Spec 5.3 wanted `RELEASE_TOKEN` persisted by the checkout. That would leave a long-lived token in `.git/config` while `uvx` installs packages and the *template's own hooks* run — code from another repository. The body's `release.yml` refuses exactly that. So: the checkout persists only the workflow token (it dies with the job, and `pyfr update` needs it to fetch `origin/template` of a private repository); the tool runs with `--no-push`; a separate push step pushes `template` and the update branch with `RELEASE_TOKEN` when it exists (so CI starts on the pull request) — the same shape as `release.yml`'s push step. Step 6 amends the spec.

- [ ] **Step 1: Write the failing test**

In `tests/test_generation.py`, add `".github/workflows/template-update.yml",` to `RAW_GUARDED_FILES` (after the `docs.yml` entry), and append:

```python


@pytest.mark.parametrize("answers", COMBINATIONS, ids=combination_id)
def test_every_render_carries_the_weekly_template_update(cookies, answers) -> None:
    root = render(cookies, **answers)
    workflow = (root / ".github" / "workflows" / "template-update.yml").read_text()
    # The decisions are the tool's exit codes (spec section 5.3); the
    # workflow only pushes and talks to GitHub.
    assert "uvx --from pyfr-cli@latest pyfr update-check --json" in workflow
    assert "uvx --from pyfr-cli@latest pyfr update --no-push" in workflow
    assert 'cron: "23 6 * * 1"' in workflow
    # RELEASE_TOKEN reaches the push step only, never the checkout: the
    # text before the first step after checkout must not mention it.
    checkout = workflow.split("- uses: actions/checkout@v7")[1].split("- name: Install uv")[0]
    assert "RELEASE_TOKEN" not in checkout
    assert "persist-credentials: true" in checkout
    assert "pyfr/update-" in workflow
    assert "gh pr create" in workflow and "gh issue create" in workflow
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --group dev --group docs pytest tests/test_generation.py -k weekly -v`
Expected: FAIL — `FileNotFoundError`.

- [ ] **Step 3: Write the workflow**

`{{cookiecutter.project_slug}}/.github/workflows/template-update.yml`. Everything from `jobs:` down sits in one raw block because it is full of `${{ }}`; the file uses no cookiecutter variable.

```yaml
name: Template update

# Once a week, ask whether a newer PyFr template version exists and, if it
# does, bring it in. `pyfr update` re-renders the template with this
# project's recorded answers, commits the result on the `template` branch
# and merges it (docs/guides/update-from-template.md). A clean merge
# becomes a pull request, which CI checks like any other change; a merge
# with conflicts becomes an issue, because a pull request cannot carry
# conflict markers. Every decision below is the tool's exit code; this
# file only pushes and talks to GitHub.

on:
  schedule:
    # Mondays 06:23 UTC. Off the hour, like nightly.yml: every scheduled
    # job on GitHub is queued at :00.
    - cron: "23 6 * * 1"
  workflow_dispatch:

permissions:
  contents: write        # the template branch and the update branch
  pull-requests: write   # gh pr create, gh pr comment
  issues: write          # gh issue create

concurrency:
  group: template-update
  cancel-in-progress: false

jobs:
  update:
    runs-on: ubuntu-latest
    timeout-minutes: 30
{%- raw %}
    env:
      # RELEASE_TOKEN when the repository has one, the workflow token
      # otherwise. A pull request opened, or a branch pushed, with the
      # workflow token starts no workflow, so CI would not run on the
      # update; the fallback still opens the pull request, and the
      # comment step below says what to do about CI. README.md,
      # "Continuous integration and releases", describes the token.
      GH_TOKEN: ${{ secrets.RELEASE_TOKEN || github.token }}
      HAS_RELEASE_TOKEN: ${{ secrets.RELEASE_TOKEN != '' }}
    steps:
      - uses: actions/checkout@v7
        with:
          # The root commit and the template branch must be reachable.
          fetch-depth: 0
          # Unlike release.yml, the checkout keeps its token -- the
          # WORKFLOW token, which dies with the job, and which `pyfr
          # update` needs to fetch origin/template of a private
          # repository. RELEASE_TOKEN never enters the checkout: the
          # template's own hooks and uvx's installs run in the steps
          # below, and a long-lived token must not be readable there. It
          # reaches the push step only, through its environment.
          persist-credentials: true

      - name: Install uv
        uses: astral-sh/setup-uv@v7

      - name: Identify the committer
        # The update's commits are made by automation and should say so.
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

      - name: Ask whether a newer template version exists
        id: check
        # 0: current, and nothing else runs. 1: behind; the JSON names
        # the versions. Anything else is an error, and the step fails.
        run: |
          set +e
          uvx --from pyfr-cli@latest pyfr update-check --json > check.json
          status=$?
          set -e
          cat check.json
          case "$status" in
            0) echo "behind=false" >> "$GITHUB_OUTPUT" ;;
            1) echo "behind=true" >> "$GITHUB_OUTPUT"
               echo "recorded=$(jq -r .recorded check.json)" >> "$GITHUB_OUTPUT"
               echo "newest=$(jq -r .newest check.json)" >> "$GITHUB_OUTPUT"
               echo "template=$(jq -r .template check.json)" >> "$GITHUB_OUTPUT" ;;
            *) exit "$status" ;;
          esac

      - name: Stop when this version already has an open pull request or issue
        id: existing
        if: steps.check.outputs.behind == 'true'
        env:
          RECORDED: ${{ steps.check.outputs.recorded }}
          NEWEST: ${{ steps.check.outputs.newest }}
        run: |
          prs=$(gh pr list --head "pyfr/update-${NEWEST}" --state open --json number --jq 'length')
          issues=$(gh issue list --state open --search "in:title \"chore: template ${RECORDED} -> ${NEWEST} conflicts\"" --json number --jq 'length')
          if [ "$prs" != "0" ] || [ "$issues" != "0" ]; then
            echo "${NEWEST} already has an open pull request or issue; nothing to do."
            echo "skip=true" >> "$GITHUB_OUTPUT"
          else
            echo "skip=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Run the update
        id: update
        if: steps.check.outputs.behind == 'true' && steps.existing.outputs.skip == 'false'
        env:
          NEWEST: ${{ steps.check.outputs.newest }}
        # --no-push: the tool's own push of the template branch would
        # need a credential in this step, where the template's hooks and
        # uvx's installs also run. The push step below pushes it instead.
        # Exit 0: clean, the merge is committed. Exit 1: conflicts; the
        # merge is abandoned here, and the issue tells the team to run
        # `just update` locally, where the template branch pushed below
        # is already at the target. Exit 2: an error, and the job fails.
        run: |
          git switch -c "pyfr/update-${NEWEST}"
          set +e
          uvx --from pyfr-cli@latest pyfr update --no-push 2>&1 | tee update.log
          status=${PIPESTATUS[0]}
          set -e
          echo "status=$status" >> "$GITHUB_OUTPUT"
          if [ "$status" = "1" ]; then git merge --abort; fi
          if [ "$status" != "0" ] && [ "$status" != "1" ]; then exit "$status"; fi

      - name: Push the template branch, and the update branch on a clean merge
        if: steps.update.outcome == 'success'
        env:
          # RELEASE_TOKEN reaches this step only. A push made with it, unlike
          # one made with the workflow token, starts CI on the update.
          PUSH_TOKEN: ${{ secrets.RELEASE_TOKEN || github.token }}
          NEWEST: ${{ steps.check.outputs.newest }}
          STATUS: ${{ steps.update.outputs.status }}
        run: |
          remote="https://x-access-token:${PUSH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
          git push "$remote" template:template
          if [ "$STATUS" = "0" ]; then
            git push "$remote" "HEAD:refs/heads/pyfr/update-${NEWEST}"
          fi

      - name: Open the pull request
        if: steps.update.outputs.status == '0'
        env:
          RECORDED: ${{ steps.check.outputs.recorded }}
          NEWEST: ${{ steps.check.outputs.newest }}
        run: |
          # The merge commit's body carries the template's changelog
          # entries for the range; the update may have a `chore: finish`
          # commit on top of it, so ask for the newest merge commit.
          git log --merges -1 --format=%b > body.md
          gh pr create \
            --base "${GITHUB_REF_NAME}" \
            --head "pyfr/update-${NEWEST}" \
            --title "chore: update template ${RECORDED} -> ${NEWEST}" \
            --body-file body.md
          if [ "$HAS_RELEASE_TOKEN" != "true" ]; then
            gh pr comment "pyfr/update-${NEWEST}" --body "Opened with the workflow token, which starts no workflows, so CI has not run on this pull request. Close and reopen it to start CI, or add a RELEASE_TOKEN secret (README.md, Continuous integration and releases) so the next update runs CI by itself."
          fi

      - name: Open an issue for the conflicts
        if: steps.update.outputs.status == '1'
        env:
          RECORDED: ${{ steps.check.outputs.recorded }}
          NEWEST: ${{ steps.check.outputs.newest }}
          TEMPLATE: ${{ steps.check.outputs.template }}
        run: |
          {
            echo "\`pyfr update\` to ${NEWEST} could not merge these files by itself:"
            echo
            grep '^conflict: ' update.log | sed 's/^conflict: /- `/; s/$/`/'
            echo
            echo "The \`template\` branch is already at ${NEWEST} on origin, so a local run goes straight to the merge:"
            echo
            echo '```'
            echo "just update ${NEWEST}"
            echo '```'
            echo
            echo "Resolve the files, \`git add\` them, \`git commit --no-edit\`, then run \`just update ${NEWEST}\` once more — docs/guides/update-from-template.md walks through it."
            echo
            echo "What changed in the template: ${TEMPLATE}/releases/tag/${NEWEST}"
          } > issue.md
          gh issue create \
            --title "chore: template ${RECORDED} -> ${NEWEST} conflicts" \
            --body-file issue.md
{%- endraw %}
```

- [ ] **Step 4: Run the tests, then regenerate**

Run: `uv run --group dev --group docs pytest tests/test_generation.py -k "weekly or template_syntax" -v`
Expected: PASS for all eight, including the `{{` / `${{` count check on the new workflow (the raw block covers every expression).

Run: `just regen && git status --short`
Expected: `examples/reference-service/.github/workflows/template-update.yml` created. The pre-commit `check-yaml` hook parses the rendered copy; run `uv run --group dev pre-commit run check-yaml --files examples/reference-service/.github/workflows/template-update.yml` and expect it to pass.

- [ ] **Step 5: Shell check of the `run:` blocks**

Extract each `run: |` block of the *rendered* file into a scratch script and run `bash -n` on it (a syntax check, no execution). Expected: no output. In particular `status=${PIPESTATUS[0]}` after the `tee` pipe is what carries the tool's exit code, not `tee`'s.

- [ ] **Step 6: Amend the spec**

In `docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md`, section 5.3, replace step 1 of the "Steps, one job" list (the paragraph beginning "`actions/checkout` with `fetch-depth: 0`" and ending "the comment in this workflow says why it differs.") with:

> `actions/checkout` with `fetch-depth: 0` (the root commit and `template` must be reachable). The checkout keeps the *workflow* token — it dies with the job, and `pyfr update` needs it to fetch `origin/template` of a private repository. `RELEASE_TOKEN` never enters the checkout: the template's own hooks and `uvx`'s installs run in later steps, and a long-lived token must not be readable there — the same rule `release.yml` follows. The tool runs with `--no-push`, and a separate push step pushes `template` and the update branch with `RELEASE_TOKEN` when it exists (so CI starts on the pull request), the workflow token otherwise. *(Amended in PR 2: the original text persisted `RELEASE_TOKEN` in the checkout.)*

And in step 4's first bullet, change "push the branch" to "the push step pushes `template` and the branch".

- [ ] **Step 7: Gates and commit**

Run: `just regen-check && just precommit`

```bash
git add '{{cookiecutter.project_slug}}/.github/workflows/template-update.yml' tests/test_generation.py examples/reference-service/.github/workflows/template-update.yml docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md
git commit -m "feat(template): open a pull request or an issue for template updates weekly

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: The guide, the nav, the glossary

**Files:**
- Create: `{{cookiecutter.project_slug}}/docs/guides/update-from-template.md`
- Modify: `{{cookiecutter.project_slug}}/mkdocs.yml` (nav), `{{cookiecutter.project_slug}}/docs/glossary.md`
- Test: `tests/test_generation.py`
- Regenerate: `examples/reference-service/`

**Interfaces:**
- Produces: the page `answers.GUIDE` (`docs/guides/update-from-template.md`) that thirteen `pyfr` error messages name.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_generation.py`:

```python


@pytest.mark.parametrize("answers", COMBINATIONS, ids=combination_id)
def test_every_render_carries_the_update_guide(cookies, answers) -> None:
    # Thirteen error messages in pyfr-cli end with "see
    # docs/guides/update-from-template.md"; the page must exist in every
    # render, and be in the site's nav (tests/test_site_nav.py checks the
    # example's nav; this checks the render's).
    from pyfr_cli.answers import GUIDE

    root = render(cookies, **answers)
    page = root / GUIDE
    assert page.is_file()
    text = page.read_text()
    assert text.startswith("---\nlast_reviewed: ")
    for phrase in ("just update", "git branch --force template", "git commit --no-edit", ".pyfr-update-ignore", "RELEASE_TOKEN"):
        assert phrase in text, phrase
    nav = (root / "mkdocs.yml").read_text()
    assert "guides/update-from-template.md" in nav
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --group dev --group docs pytest tests/test_generation.py -k update_guide -v`
Expected: FAIL — the page does not exist.

- [ ] **Step 3: Write the page**

`{{cookiecutter.project_slug}}/docs/guides/update-from-template.md`:

````markdown
---
last_reviewed: 2026-09-15
covers:
  - justfile
  - .pyfr-answers.yml
  - .pyfr-update-ignore
  - .github/workflows/template-update.yml
---

# Update from the template

This project was generated from [PyFr](https://github.com/EmadMokhtar/pyfr)
at the version `.pyfr-answers.yml` records. The template keeps improving —
CI workflows, container images, the observability wiring, the gates — and
`just update` brings those improvements in without touching what is
yours.

## How it works

An update is an ordinary three-way git merge (a merge that compares both
sides against the last state they agreed on). The tool behind it,
`pyfr-cli`, runs from PyPI through `uvx`, so nothing is installed in this
project:

1. It reads `.pyfr-answers.yml` — the answers this project was generated
   with, and the template version it is at.
2. It renders the template at the target version with those answers, and
   commits the result on a branch named `template`: pristine template
   output, nothing else. That branch is pushed to `origin`; every machine
   that updates this project needs it, so do not delete it.
3. It merges `template` into your branch. Files you changed and the
   template did not keep your version; files the template changed and you
   did not receive the template's; a file you deleted stays deleted. Only
   a line both sides changed conflicts.
4. It records the new version in `.pyfr-answers.yml`.

The paths in `.pyfr-update-ignore` are never touched — see below.

## Running it

```bash
just update
```

updates to the newest template release. To pin a version:

```bash
just update v0.12.0
```

Both need the network. A clean update leaves one merge commit,
`chore: update template vA -> vB`, whose body lists what changed in the
template — plus a `chore: prepare …` or `chore: finish …` commit when the
release shipped a migration script. Run `just check`, then push.

`just update-check` exits 1 when a newer version exists and 0 when this
project is current; the weekly workflow runs it first.

## When the merge conflicts

The update stops with exit 1 and lists the files:

```
conflict: pyproject.toml
merge: conflicts in the files above
  1. resolve them, then stage them:  git add <the files>
  2. commit the merge:               git commit --no-edit   (the message is prepared)
  3. run the same command again:     pyfr update  (runs what is left)
```

Resolve each file as in any merge, `git add` it, and commit with
`git commit --no-edit` — `--no-edit` keeps the prepared message; an editor
would strip its `#` headings. Then run `just update` again: it finishes
what is left (the release's `after.py` migration scripts) and records the
version. `git merge --abort` puts everything back if you want to stop.

## What is never updated

`.pyfr-update-ignore` lists the paths the update leaves exactly as this
project has them — yours from the first day, or artifacts of your code:
`README.md`, `CHANGELOG.md`, `uv.lock`, the schema, the OpenAPI document
and its baseline, `docs/adr/`, and the example slice under
`src/…/domain/`, `services/` and `api/v1/`. Everything else is
template-owned and receives fixes by default.

The file uses `.gitignore` syntax, one pattern per line, comments on
their own lines (a `#` after a pattern is part of the pattern), every
pattern anchored with a leading `/`. Add paths as you diverge — a
template-owned file you have rewritten and no longer want fixes for. Do
not add `pyproject.toml` or the workflows to keep a conflict away: a
conflict there is one line to resolve once, and the file keeps receiving
fixes afterwards.

## The weekly pull request

`.github/workflows/template-update.yml` runs every Monday (and on demand).
When a newer template exists it runs the update on a branch named
`pyfr/update-vX.Y.Z`:

- **A clean merge** becomes a pull request titled
  `chore: update template vA -> vB`, with the template's changelog entries
  in its body. CI runs on it like on any other change; review and merge
  it as usual (squash-merge is fine — the tool does not depend on the
  merge commit surviving).
- **Conflicts** become an issue, `chore: template vA -> vB conflicts`,
  naming the files. Run `just update vB` locally: the `template` branch
  is already at `vB` on `origin`, so the run goes straight to the merge.

Nothing is opened twice: the workflow stops when a pull request or issue
for that version is already open.

The workflow pushes with the `RELEASE_TOKEN` secret when the repository
has one, and with its own workflow token otherwise. With the fallback the
pull request still opens, but CI does not start on it — GitHub never runs
workflows for events the workflow token itself caused — so the workflow
leaves a comment: close and reopen the pull request to start CI, or add
`RELEASE_TOKEN`. The README's *Continuous integration and releases* says
what the token needs (Contents, Pull requests and Issues, read and write)
and names the repository setting the fallback depends on.

## Migration scripts

Some template changes cannot be expressed as a merge — a file that moves,
a setting that changes shape. The template ships a script for those under
`updates/<version>/` in its own repository; `just update` runs them for
every version between yours and the target, before the merge (`before.py`)
and after it (`after.py`), and commits what they change. They are standard
library only, idempotent, and never run twice for the same version.

## A project generated before the update tooling existed

Every project generated from PyFr v0.7.0 or later has `.pyfr-answers.yml`,
which is all the tool needs. `just update` first appeared in a later
template version; until this project has the recipe, run the tool directly
from the project root:

```bash
uvx --from pyfr-cli@latest pyfr update
```

The update brings the recipe, this page and `.pyfr-update-ignore` with
it; a project without an ignore file is updated with the tool's built-in
default, which is the same list.

A project generated before v0.7.0 has no answers file. Write one by hand
at the project root, with the answers you generated with and the version
you generated from, then run the command above:

```yaml
_template: https://github.com/EmadMokhtar/pyfr
_template_version: "0.6.0"
project_name: "My Service"
project_slug: "my-service"
package_name: "my_service"
description: "A Python microservice."
author_name: "Your Name"
author_email: "you@example.com"
github_org: "your-org"
database: "postgres"
cache: "redis"
object_storage: "s3"
http_port: "8000"
license: "Apache-2.0"
```

## When the `template` branch is wrong

The tool refuses to run when the `template` branch is not what it
expects, and says so. The cases, and the way out:

- **"template's tip … was not made by pyfr update"** — someone committed
  on the branch by hand. Point it back at the last commit the tool made,
  which the message names: `git branch --force template <sha>`.
- **"the repository has N root commits"** or a rewritten history — the
  tool creates `template` from the repository's first commit, which for a
  generated project is unmodified template output. When that commit is
  gone (a squashed or imported history), point the branch at the commit
  closest to pristine template output that you have, accept one noisier
  merge, and the tool maintains the branch from there:
  `git branch --force template <sha>`, then `just update`.
- **"the local template branch … and origin/template have diverged"** —
  another machine pushed the branch. The remote's version is the one every
  machine uses: `git branch --force template origin/template`.
- **"template is checked out in another worktree"** — a worktree you made
  holds the branch. Save what it holds, `git worktree remove <path>`, run
  again.

Never delete `origin/template`: it holds the commit the next merge is
based on. If it is gone, the tool stops and names this section.

## Trust

`just update` runs code from the template repository — cookiecutter's
hooks and the migration scripts — with your permissions. `_template` in
`.pyfr-answers.yml` must name a repository you trust; the same goes for
`--template`, the one-run override.
````

- [ ] **Step 4: Nav and glossary**

In `{{cookiecutter.project_slug}}/mkdocs.yml`, under `- Guides:`, after the `Outbound HTTP calls` line, add:

```yaml
      - Update from the template: guides/update-from-template.md
```

In `{{cookiecutter.project_slug}}/docs/glossary.md`, add rows to the table in alphabetical position (the table is alphabetical by term; place each where it sorts):

```
| `.pyfr-update-ignore` | The paths `just update` never touches, in `.gitignore` syntax. Yours to grow as the project diverges from the template. |
| `pyfr-cli` | The tool behind `just update` and `just update-check`, run from PyPI through `uvx`; nothing of it is installed in this project. |
| `template` branch | A branch holding pristine template output and nothing else, kept on `origin`; every update merges from it. Never delete it. |
```

Check the existing `.pyfr-answers.yml` row's wording still holds and that a `Vendor branch` row, if one exists in this glossary, points at the `template` branch row.

- [ ] **Step 5: Run the tests, build the site, regenerate**

Run: `uv run --group dev --group docs pytest tests/test_generation.py -k "update_guide or extreme_renders" -v`
Expected: PASS — `test_the_two_extreme_renders_build_their_sites` builds a render's MkDocs site with `--strict`, which catches a broken link in the new page.

Run: `just regen && uv run --group dev --group docs pytest tests/test_site_nav.py -v`
Expected: PASS (the example's nav now lists the page).

- [ ] **Step 6: Gates and commit**

Run: `just regen-check && just precommit`

```bash
git add '{{cookiecutter.project_slug}}/docs/guides/update-from-template.md' '{{cookiecutter.project_slug}}/mkdocs.yml' '{{cookiecutter.project_slug}}/docs/glossary.md' tests/test_generation.py examples/reference-service/docs/guides/update-from-template.md examples/reference-service/mkdocs.yml examples/reference-service/docs/glossary.md
git commit -m "docs(template): add the update-from-template guide

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: README and contributing — five workflows, the widened token, the sixth setting

**Files:**
- Modify: `{{cookiecutter.project_slug}}/README.md` ("Continuous integration and releases")
- Modify: `{{cookiecutter.project_slug}}/docs/contributing.md` ("Repository settings")
- Test: `tests/test_generation.py`
- Regenerate: `examples/reference-service/`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_generation.py`:

```python


def test_the_readme_documents_the_update_workflow_and_its_token(cookies) -> None:
    root = render(cookies, **EVERYTHING_ON)
    readme = (root / "README.md").read_text()
    section = readme.split("## Continuous integration and releases")[1].split("\n## ")[0]
    assert "Five workflows" in section
    assert "`template-update.yml`" in section
    # spec section 5.4: the token's documented permissions widen, and the
    # two consequences of leaving it out are stated.
    assert "Pull requests" in section and "Issues" in section
    assert "Allow GitHub Actions to create and approve pull requests" in section
    assert "Six settings" in section
    contributing = (root / "docs" / "contributing.md").read_text()
    assert "Six settings" in contributing
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --group dev --group docs pytest tests/test_generation.py -k readme_documents -v`
Expected: FAIL on `"Five workflows"`.

- [ ] **Step 3: Edit the README**

In `{{cookiecutter.project_slug}}/README.md`, section "Continuous integration and releases":

1. `Four workflows under `.github/workflows/` and a Dependabot schedule ship` → `Five workflows under `.github/workflows/` and a Dependabot schedule ship`.
2. After the `docs.yml` table row, add:

```
| `template-update.yml` | 06:23 UTC on Mondays, or by hand | asks whether a newer PyFr template version exists and, if so, runs `just update` on a branch: a clean merge becomes a pull request with the template's changelog in its body, a merge with conflicts becomes an issue naming the files — see [Update from the template](docs/guides/update-from-template.md) |
```

3. `Five settings live in the GitHub interface, not in this repository.` → `Six settings live in the GitHub interface, not in this repository.`
4. Replace the `RELEASE_TOKEN` bullet with:

```
- **A `RELEASE_TOKEN` secret, if a ruleset on `main` requires a pull
  request — or if the weekly template update should run CI.** The
  workflow token cannot pass such a ruleset (`GH013`), and on a
  user-owned repository GitHub does not let the Actions app be exempted;
  a fine-grained personal access token of an exempt admin (this
  repository only; Contents, Pull requests and Issues: read and write)
  stored as `RELEASE_TOKEN` is what `release.yml` pushes with and what
  `template-update.yml` opens its pull requests and issues with. Without
  it both fall back to the workflow token: releases still push where no
  ruleset forbids it, and the update pull request still opens — but
  GitHub starts no workflow for an event the workflow token caused, so
  CI does not run on that pull request until someone closes and reopens
  it (the workflow leaves a comment saying so).
```

5. After the `RELEASE_TOKEN` bullet, add a new bullet:

```
- **Settings → Actions → General → "Allow GitHub Actions to create and
  approve pull requests"**, only if `RELEASE_TOKEN` is not set: without
  it the workflow token may not open the weekly template-update pull
  request, and `template-update.yml` fails at `gh pr create`.
```

- [ ] **Step 4: Edit contributing.md**

In `{{cookiecutter.project_slug}}/docs/contributing.md`, "Repository settings": change `Five settings live in the GitHub interface` to `Six settings live in the GitHub interface`, and in the same sentence's list, after "a `RELEASE_TOKEN` secret when a ruleset on `main` requires pull requests," insert "the Actions permission to open pull requests when that secret is absent,". Then add one sentence at the end of the paragraph: "The weekly `template-update.yml` is described in [Update from the template](guides/update-from-template.md)."

- [ ] **Step 5: Run the tests, regenerate**

Run: `uv run --group dev --group docs pytest tests/test_generation.py -k "readme_documents or docs_carry" -v`
Expected: PASS.

Run: `just regen && just regen-check`

- [ ] **Step 6: Gates and commit**

Run: `just precommit`

```bash
git add '{{cookiecutter.project_slug}}/README.md' '{{cookiecutter.project_slug}}/docs/contributing.md' tests/test_generation.py examples/reference-service/README.md examples/reference-service/docs/contributing.md
git commit -m "docs(template): document the weekly template update and the token it needs

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: The end-to-end test learns that the body ships the ignore file

**Files:**
- Modify: `tests/test_update_e2e.py`

**Interfaces:**
- Consumes: the fixtures of PR 1's test (`template_remote`, `project`, `run`, `recorded_version`, `commit_all`, `git`).

The fixture copies this checkout's template body, so from Task 1 on every fixture project renders with `.pyfr-update-ignore`. Two consequences: the clean-update scenario no longer prints the built-in-default line, and spec 8.2's scenario 6 — a project *without* the file receives it — becomes testable for real.

- [ ] **Step 1: Change the clean-update assertion**

In `test_a_clean_update_merges_the_template_and_keeps_the_team_s_work`, replace

```python
    assert "ignore: no .pyfr-update-ignore; using the built-in default" in out
```

with

```python
    # The body ships the ignore file, so the built-in default is not used
    # and nothing is installed.
    assert "ignore:" not in out
    assert (project / ".pyfr-update-ignore").read_text().startswith("# Paths `just update` leaves")
```

- [ ] **Step 2: Add scenario 6**

Append to `tests/test_update_e2e.py`:

```python


def test_a_project_without_the_ignore_file_receives_it(
    project: Path,
    template_remote: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A project generated at v0.7.0–v0.11.0 has no .pyfr-update-ignore. The
    # update runs with the built-in default and brings the file (spec 5.2,
    # 8.2 scenario 6). The merge cannot deliver it -- the default ignores
    # the file itself -- so the tool installs it beside the answers file.
    git(project, "rm", "-q", ".pyfr-update-ignore")
    commit_all(project, "chore: pretend this project predates the ignore file")
    code, out, _ = run(
        project, monkeypatch, capsys, "update", "--template", str(template_remote), "--to", "v100.1.0"
    )
    assert code == 0, out
    assert "ignore: no .pyfr-update-ignore; using the built-in default" in out
    assert "ignore: installed .pyfr-update-ignore from the template" in out
    installed = project / ".pyfr-update-ignore"
    assert installed.read_text().startswith("# Paths `just update` leaves")
    assert "/src/reference_service/domain/" in installed.read_text()
    # It rode in the merge commit, like the answers file.
    assert ".pyfr-update-ignore" in git(project, "show", "--name-only", "--format=", "HEAD~1")
    assert git(project, "status", "--porcelain") == ""
```

(`reference_service` is the fixture project's `package_name`, from `tests/reference-answers.yaml`.)

- [ ] **Step 3: Run the e2e file**

Run: `uv run --group dev --group docs pytest tests/test_update_e2e.py -v`
Expected: 13 PASS (12 + the new one). If the clean scenario fails on `"ignore:" not in out`, the fixture's render lacks the file — Task 1 was not completed on this branch.

- [ ] **Step 4: Commit**

```bash
git add tests/test_update_e2e.py
git commit -m "test(pyfr-cli): a project without .pyfr-update-ignore receives it from the template

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Verify the workflow once, for real (spec 8.5)

**Files:** none in this repository. This task creates a throwaway GitHub repository under the maintainer's account — **ask the maintainer before creating it**, and name the repository so it is obviously disposable.

**Interfaces:**
- Consumes: the template body at this branch's HEAD; `pyfr-cli` on PyPI.

- [ ] **Step 1: Generate a project at the previous release and push it to a new repository**

Ask the maintainer to confirm the repository name (suggested: `pyfr-m8-verify`) and that it may be created public under `EmadMokhtar`. A project generated at `v0.10.0` is genuinely one release behind `v0.11.0`, so the update runs for real (`v0.11.0` changed nothing in the template body, so the merge is clean by construction — that is the path this task verifies; the conflict path needs two releases whose bodies differ, and is verified in PR 3 once `v0.12.0` exists). Then:

```bash
cd /tmp && rm -rf pyfr-m8-verify
uvx cookiecutter gh:EmadMokhtar/pyfr --checkout v0.10.0 --no-input \
  project_name="PyFr M8 Verify" github_org=EmadMokhtar database=postgres cache=redis object_storage=s3
cd pyfr-m8-verify
gh repo create EmadMokhtar/pyfr-m8-verify --public --source=. --push
```

(The post-generation hook already ran `git init` and the first commit. If SSH pushes fail from this environment, push over HTTPS: `git -c credential.helper='!gh auth git-credential' push https://github.com/EmadMokhtar/pyfr-m8-verify.git main`.)

- [ ] **Step 2: Give the old project the new workflow**

A `v0.10.0` project has no `template-update.yml` — this PR adds it. Copy the *rendered* one (it carries no cookiecutter variable) from this checkout's example into the throwaway project, commit and push:

```bash
cp /Users/emadmokhtar/Projects/pyfr/.claude/worktrees/m1-work-5c1a84/examples/reference-service/.github/workflows/template-update.yml .github/workflows/
git add .github/workflows/template-update.yml
git commit -m "ci: add the weekly template update"
git push
```

`.pyfr-answers.yml` records `"0.10.0"`; the newest tag is `v0.11.0`; `update-check` will say behind.

- [ ] **Step 3: Run the workflow by hand and observe**

```bash
gh workflow run template-update.yml --repo EmadMokhtar/pyfr-m8-verify
sleep 60
gh run list --repo EmadMokhtar/pyfr-m8-verify --workflow template-update.yml --limit 1
gh run watch --repo EmadMokhtar/pyfr-m8-verify $(gh run list --repo EmadMokhtar/pyfr-m8-verify --workflow template-update.yml --limit 1 --json databaseId --jq '.[0].databaseId')
```

Expected: the run succeeds; `gh pr list --repo EmadMokhtar/pyfr-m8-verify` shows `chore: update template v0.10.0 -> v0.11.0` from branch `pyfr/update-v0.11.0` with the changelog in its body and — since the throwaway repository has no `RELEASE_TOKEN` — the comment about CI; `git ls-remote --heads https://github.com/EmadMokhtar/pyfr-m8-verify template` shows the pushed branch. Run the workflow a second time: it must stop at "already has an open pull request", opening nothing. If `gh pr create` fails with a permissions error, enable Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests" on the throwaway repository and rerun — and confirm the README bullet from Task 5 describes exactly that.

- [ ] **Step 4: Amend spec 8.5**

In `docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md`, section 8.5, replace "Verified once by `workflow_dispatch` on a freshly generated project as the last step of PR 2." with "The clean-merge path is verified once by `workflow_dispatch` on a project generated at `v0.10.0` as the last step of PR 2; the conflict path needs two releases whose template bodies differ, and is verified the same way in PR 3, once `v0.12.0` exists." Commit as `docs(pyfr): split the workflow's manual verification across pr 2 and pr 3` with the trailer.

- [ ] **Step 5: Record and clean up**

Paste the run URLs, the pull request URL and the issue URL into the PR description's "Verification" section (Task 8). Then ask the maintainer whether to delete the throwaway repository (`gh repo delete EmadMokhtar/pyfr-m8-verify --yes`) or keep it; do not delete without their answer.

If anything in Steps 3–4 fails, fix the workflow in the template body (Task 3's file), `just regen`, commit as `fix(template): …`, push the branch, and repeat from Step 1 with a fresh generation.

---

### Task 8: Final verification and the pull request

- [ ] **Step 1: Every gate**

```bash
just lint
just check
just precommit
```
Expected: all green; `just check`'s test run includes the new generation tests and the 13 end-to-end scenarios; the golden diff reports `examples/reference-service matches the template.`

- [ ] **Step 2: Definition of done, PR 2's share**

Spec section 1: item 4 (every generated project carries `template-update.yml`, verified once by `workflow_dispatch` — Task 7) and item 5's generated side (the guide) are green; item 6's generation tests pass.

- [ ] **Step 3: Push and open the pull request**

The branch is `claude/m8-pr2-generated-side`; the tracking issue is #51 (already open — do not create another); assign with the bare login.

```bash
git -c credential.helper='!gh auth git-credential' push https://github.com/EmadMokhtar/pyfr.git claude/m8-pr2-generated-side
```

```bash
gh api --method POST repos/EmadMokhtar/pyfr/pulls -f title="feat: let a generated project update itself from the template (m8 pr 2)" -f head="claude/m8-pr2-generated-side" -f base="main" -F body=@<body file> --jq .html_url
gh api --method POST repos/EmadMokhtar/pyfr/issues/<PR number>/assignees -f 'assignees[]=EmadMokhtar'
```

The body: what the PR adds (the two recipes, `.pyfr-update-ignore`, `template-update.yml`, the guide, the docs), the spec amendment (5.3's token handling), the verification outputs of Step 1, Task 7's run/PR/issue URLs, `Refs #51` (not `Closes` — PR 3 closes M8), and the `🤖 Generated with [Claude Code](https://claude.com/claude-code)` footer. Use `gh api` (REST) if `gh pr create` times out on GraphQL from this environment.

- [ ] **Step 4: Verify the links registered**

```bash
gh api repos/EmadMokhtar/pyfr/pulls/<PR number> --jq '{assignees: [.assignees[].login], title: .title}'
```

---

## Self-review against the spec

- **5.1 recipes** — Task 2, verbatim; the `uvx` spellings verified against PyPI.
- **5.2 ignore file** — Task 1; equality with `default_text` pinned for all eight combinations.
- **5.3 workflow** — Task 3; the token handling amended (workflow token persisted, `RELEASE_TOKEN` in the push step only, `--no-push` + explicit pushes); idempotency (open PR/issue check); the `GITHUB_TOKEN` fallback comment.
- **5.4 token** — Task 5 (README and contributing).
- **7.1 generated docs** — Task 4 (guide, nav, glossary), Task 2 (commands rows), Task 5 (README, contributing).
- **8.2 scenario 6** — Task 6.
- **8.3 generation tests** — Tasks 1–5 each add one.
- **8.5 manual verification** — Task 7, gated on the maintainer's approval to create the throwaway repository.
- **9 PR 2 row** — everything listed is here; `Refs #51`, PR 3 closes.
- Not in this PR: ADR 0018, the root contributing guide, roadmap/index/README status — PR 3.
