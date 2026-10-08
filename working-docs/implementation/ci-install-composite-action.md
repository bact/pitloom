---
Created: 2026-09-18
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# CI workflow bootstrap: the `install-pitloom` composite action

See also: [hatchling-build-hook.md](hatchling-build-hook.md) (the
Hatchling 1.32.3 compatibility fix bundled in the same PR),
[windows-macos-ci.md](windows-macos-ci.md) (the Windows/macOS matrix this
action's callers run under), [wheel-sbom-verification.md](wheel-sbom-verification.md)
(`loom verify-wheel`/`validate-wheel` background).

**Status (2026-09-18):** shipped on `main` via PR
[#222](https://github.com/bact/pitloom/pull/222).

## What was built

- `.github/actions/install-pitloom/action.yml`: a composite action
  wrapping the pip-install bootstrap every CI workflow needs (Hatchling
  version pin, extra packages, dependency groups, the local package
  itself, editable or not, working around Pitloom's self-referential
  `[build-system] requires = [..., "pitloom"]`). Used by 10 of Pitloom's
  16 `.github/workflows/*.yml` files -- see the roadmap's "CI workflow
  step duplication" item.
- `loom verify-wheel`/`loom validate-wheel` calls added or consolidated
  in `build.yml`, `hatch-integration.yml`, and `pypi-publish.yml`,
  replacing three independently hand-rolled zipfile-inspection scripts.
- `hatch-integration.yml` gained a `hatchling-version: ["1.29.0", ""]`
  matrix axis (floor + latest) so a future undocumented Hatchling break
  -- like the one this same PR fixes -- is caught by CI instead of a
  user bug report.

## Traps discovered this round

### GitHub Actions substitutes `${{ }}` even inside a shell comment

A `run:` block's entire text -- including anything after a `#` -- is
scanned for `${{ }}` and substituted **before** the shell ever parses it
as a comment. A step-level comment that mentions literal `${{ }}` syntax
(to explain *why* the code doesn't use a direct splice) is safe only
**above** `env:`/`run:`; once it's inside the `run: |` block scalar, an
empty `${{ }}` becomes a malformed GitHub Actions expression and the
whole composite action fails to load with an unhelpful
`An expression was expected` parse error, reported at the *block's* own
line/col rather than the actual offending line. One such doc-comment
typo broke 10 workflows at once (every caller of `install-pitloom`).
Never write literal `${{ ... }}` inside a `run: |` block's comments, even
to describe the syntax -- reword around it (e.g. "a GitHub expression
splice") instead.

### `action-validator`'s `patterns` input is newline-, not comma-, separated

`mpalmer/action-validator`'s GitHub Action splits `patterns` via
`xargs -I{}` **per line**. A comma-joined value
(`"action.yml,.github/actions/**/action.yml"`) is treated as one literal,
non-matching pathspec and silently validates zero files -- no error, the
step just does nothing useful. Use a YAML block scalar, one pattern per
line:

```yaml
patterns: |
  action.yml
  .github/actions/**/action.yml
```

### `actions/upload-artifact`'s `if-no-files-found` applies to the *combined* glob

When `path:` lists multiple lines, `if-no-files-found: warn` (the
default) only fires if **none** of the lines match anything -- a missing
file on one line is silently absorbed as long as at least one other line
matches. A two-line `path: |` of a wheel glob plus an SBOM filename won't
warn even if the SBOM was never produced, as long as the wheel exists.
Don't rely on this default to catch a partial-artifact bug; check the
specific file's existence in its own step if that matters.

### pip's `--no-build-isolation` is invocation-global, not per-package

There is no `pip install --no-build-isolation-package <name>` (that flag
exists in `uv`, not `pip`). Combining a self-referential local-package
install (which needs `--no-build-isolation` to avoid fetching a stale
copy of itself from PyPI as its own build dependency) with unrelated
`--group`/extras packages **in the same `pip install` call** forces *all*
of them through `--no-build-isolation` -- harmless for anything with a
prebuilt wheel, but a real risk for a package that needs to build from
source (e.g. `atheris`, which has no wheel below Python 3.12 and needs a
real Clang/libFuzzer toolchain). `install-pitloom/action.yml` deliberately
keeps `--group` installs in their **own**, normally-isolated
`pip install` call, accepting the tradeoff that `--group` and the local
package now resolve independently (two passes) instead of jointly -- see
the action's own comments for the full reasoning.

## Decisions made

- **`--fail-on-mismatch` added to every `loom verify-wheel` call.**
  Without it, a wheel/SBOM name-version mismatch is only a `WARNING:`,
  not a failing check -- silent for exactly the kind of bug (wrong SBOM
  embedded) this check exists to catch, especially right before a PyPI
  release.
- **`build.yml` gained its own `loom validate-wheel` step, distinct from
  "Generate SBOM"/"Validate SBOM with spdx3-validate".** The latter
  validates a *separately generated* standalone SBOM (`loom project .`,
  the CLI's `read_project()` path) -- not the SBOM the Hatchling hook
  actually embeds in the wheel (`metadata_from_hatchling()`, a different
  code path -- see `AGENTS.md`'s "Usage surfaces" note). A green
  "SBOM validated" checkmark from the standalone check says nothing about
  whether the *shipped, embedded* SBOM is schema-valid. Verify and
  validate the wheel-embedded copy directly
  (`loom verify-wheel`/`validate-wheel <whl>`), not a stand-in generated
  a different way.
- **A "success" job-summary step must be gated on every check that can
  fail, not just the ones it originally shipped with.** Adding a new
  failing check without adding it to an existing summary step's `if:`
  let a self-contradictory step summary through (a "Build completed
  successfully" block next to a "Build Failed" block) even though the
  job's actual exit code was correct. Audit every summary/gate `if:`
  when adding a new failure mode, not just the dedicated failure-summary
  step.

## Local verification gotcha: pyright can silently resolve the wrong Python environment

Running `pyright` from a shell where a different Python is ahead of the
intended venv on `PATH` makes it analyze against that other
environment's installed packages -- it produced two false-positive
"errors" here (about a Hatchling-version-specific generic signature) that
vanished once the venv was actually activated (or `--pythonpath` was
passed explicitly). If `pyright` disagrees with `mypy --strict`/
`pyrefly check` on the same file, check environment resolution before
trusting the diff.

## Revision 2026-10-08: installs with `uv pip`

- `setup-python` now also runs `astral-sh/setup-uv`, with the uv version
  pinned in `.github/uv/requirements.txt` (setup-uv's `version-file`; a
  requirements file so Dependabot's pip ecosystem bumps it -- a plain
  `version:` input would never be updated);
  `install-pitloom` runs every install as `uv pip install --system` into
  the setup-python interpreter. Local measurement, lint job inputs on
  Python 3.10: pip 29 s cold / 12 s warm, uv 4 s / under 1 s, with the
  same resolved package set.
- The call structure is unchanged. uv's `--no-build-isolation` is also
  invocation-global, so `--group` stays in its own isolated call (uv's
  `--no-build-isolation-package` would allow one call; not taken, to keep
  the two resolves identical to the pip version).
- pip is still upgraded (through uv): `pip-audit` and the
  `pip install --dry-run` wheel checks run the interpreter's own pip.
- Cache: uv's download cache replaces setup-python's pip cache. The input
  defaults to setup-uv's `auto`, which skips the cache on release,
  tag-push, `pull_request_target` and `workflow_run` events and on
  self-hosted runners, so `pypi-publish.yml` never restores one. The cache key
  hashes only the root `pyproject.toml`; setup-uv's default glob would
  also hash every fixture `pyproject.toml` under `tests/`. The key suffix
  includes the job id: jobs with the same OS and Python install different
  groups/extras, and the first to finish saves the shared key, so without
  it a light job (Ruff) would leave every heavier job a partial cache.
- `package-spec` is optional: empty installs only `extra-packages` and
  `groups`, skipping hatchling, setuptools and the local build. The Ruff
  job uses it, since ruff and flake8 never import Pitloom. Pylint runs as
  its own job (`-j` rejected: a parallel run reported a C1803 that a
  serial run does not).
- The env var `GROUPS` was renamed `INSTALL_GROUPS`: `GROUPS` is a bash
  special variable (shellcheck SC2128). The environment value happened to
  win, but nothing guaranteed it.
- Still pip, by design: the user-facing action's
  `scripts/action/pitloom-install.sh` (a user's runner may have no uv),
  `action-selftest.yml`'s `pip install --dry-run`, and tests that check a
  wheel installs with pip.
- Interpreter: `setup-python` writes its `python-path` output to
  `UV_PYTHON` (via `GITHUB_ENV`, with `printf` so a Windows path's
  backslashes stay literal). Without it `--system` takes the first
  non-venv Python on `PATH`, and every runner image has its own (Windows:
  a registry 3.12 and Miniconda; macOS: Homebrew; Ubuntu:
  `/usr/bin/python3`, externally managed); setup-python's comes first
  today, but only by `PATH` order. No workflow calls uv directly, so the
  variable reaches nothing else.
- `UV_LINK_MODE=copy` (install step only): on Windows uv's cache (`D:`) and
  the toolcache Python (`C:`) are on different drives, where a hardlink
  fails with a warning and falls back to a copy.
- Trap: `--system` skips virtual environments, even one first on `PATH`.
  To try the script locally, set `UV_PYTHON=<venv>/bin/python` (it wins
  over `--system`'s lookup and still accepts a venv), or it installs into
  whatever non-venv Python comes next (here: a pyenv interpreter with the
  developer's editable installs).

## Where

- `.github/actions/install-pitloom/action.yml`,
  `.github/actions/setup-python/action.yml`
- `.github/workflows/{build,hatch-integration,pypi-publish,test,lint,
  typecheck,pip-audit,docs,fuzz,action-selftest,actionlint}.yml`
- `working-docs/design/roadmap.md`: "CI workflow step duplication" item,
  marked done.
