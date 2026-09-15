# Migration scripts

Some template changes cannot be expressed as a merge: a file that moves, a
setting that changes shape. When a release needs one, it ships a directory
here named after the version, and `pyfr update` runs its scripts for every
version greater than the project's recorded one and not greater than the
target, in ascending order.

```
updates/
  v0.13.0/
    before.py   # runs on the project's tree before the merge
    after.py    # runs after the merge is committed
```

Either file may be absent. Nothing here is rendered into a project:
`updates/` sits outside `{{cookiecutter.project_slug}}/`.

## The contract

- **Where and how they run.** `uv run --no-project python <script>`, with
  the project root as the working directory and `PYFR_UPDATE_FROM` and
  `PYFR_UPDATE_TO` (with the `v`, for example `v0.12.0`) in the
  environment. `--no-project` means the project's own dependencies are not
  installed first: **standard library only.**
- **`before.py`** makes the merge line up — typically `git mv` through
  `subprocess`, so a file the template moved is moved in the project too
  and git merges the two renames as one file. It may edit files. `pyfr
  update` commits what it leaves staged or modified as
  `chore: prepare for template <target>`.
- **`after.py`** rewrites contents once the template's version of a file
  is in place. `pyfr update` commits what it changed as
  `chore: finish template <target>`.
- **New files need `git add`.** Both commits stage with `git add --update`,
  which takes changed and deleted tracked files only. A file a script
  creates must be `git add`ed by the script itself, in `before.py` and in
  `after.py` alike.
- **Idempotent.** Running a script twice must equal running it once: a
  failed update is re-run, and a script that already did its work exits 0
  without doing it again. Check before you act (`if dst.exists(): exit(0)`).
- **Exit non-zero to stop the update.** Whatever the script prints to
  stderr is shown to the user, followed by "`git reset --hard HEAD` reverts
  what it changed".
- **A deleted file is not an error.** Teams delete example files; a script
  that finds its target missing exits 0.

## Testing one

`tests/test_update_e2e.py` builds a two-version template in a temporary
directory, with fixture scripts under `updates/v100.1.0/`, and asserts the
project's tree after the update. Copy that pattern: generate at the
previous version, edit the project the way a team would, update, assert.
