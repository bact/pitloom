---
Created: 2026-07-05
Last-Modified: 2026-11-16
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Using Pitloom as a GitHub Action: implementation notes

See [docs/github-action.md](../../docs/github-action.md) for the
user-facing quick start, full inputs/outputs reference, and Configuration
page -- this file covers implementation detail (design rationale,
dogfooding) and CI recipes not covered there.

Pitloom ships a composite GitHub Action (`action.yml` at the repository
root) that wraps the `loom` CLI. It works for any Python project -- any
build backend, not just Hatchling -- because it drives the CLI the same
way a developer would from a terminal.

See [adoption-surfaces.md](adoption-surfaces.md) for how this
fits alongside Pitloom's other surfaces.

## Recipe: multiple creators

`--creator-name` is repeatable -- each occurrence starts a new creator, and
`--creator-type`/`--creator-email` bind to the most recently named one.
Pass them through `args` (the Action itself has no dedicated multi-creator
input):

```yaml
- uses: bact/pitloom@v0.24.0
  with:
    project-path: "."
    output: "sbom.spdx3.json"
    args: >-
      --creator-name "Acme Corp" --creator-type organization
      --creator-name Alice
```

## Recipe: attach the SBOM to a GitHub Release

```yaml
name: Release SBOM

on:
  release:
    types: [published]

jobs:
  sbom:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.x"
      - uses: bact/pitloom@v0.24.0
        id: pitloom
        with:
          project-path: "."
          output: "sbom.spdx3.json"
          pretty: "true"
      - name: Upload SBOM to the release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          gh release upload "${{ github.event.release.tag_name }}" \
            "${{ steps.pitloom.outputs.sbom-path }}"
```

## Recipe: matrix build across Python versions

```yaml
name: SBOM matrix

on: [push, pull_request]

jobs:
  sbom:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13", "3.14"]
    steps:
      - uses: actions/checkout@v7
      - uses: bact/pitloom@v0.24.0
        with:
          project-path: "."
          python-version: ${{ matrix.python-version }}
          artifact-name: "sbom-py${{ matrix.python-version }}"
```

## How Pitloom dogfoods this Action

`.github/workflows/action-selftest.yml` runs the Action against the
Pitloom repository itself (`uses: ./`, `install: false`, so it exercises
the checked-out code rather than a published release), then asserts that
the output file exists, parses as JSON-LD with an `@graph` array, and
contains both the `pitloom` package and a `pkg:pypi/pitloom@...` PURL.
Use the same assertions in your own CI if you want a smoke test beyond
"the step did not fail".

## Stderr-to-annotation translation

The "Generate SBOM" step captures `loom`'s stderr into a temp file (while
still streaming it live via `tee`), then re-emits each `INFO:`/
`WARNING:`/`ERROR:` line (see `AGENTS.md`'s "CLI output" convention) as
a `::notice::`/`::warning::`/`::error::` GitHub Actions workflow command
-- giving them real annotations (PR "Checks" tab, job summary) instead of
just plain log text. A continuation line of a multi-line message (none
currently emitted by `loom`, but not forbidden by the convention) is
re-annotated at the same level rather than silently dropped. `set +e`
brackets the `loom` invocation so a failing run still gets its `ERROR:`
line annotated before the step's exit code is re-checked and propagated
explicitly. The raw echo of `loom`'s output is fenced with `::stop-commands::`
(random token) so a `::` line in it is logged, not run as a workflow command;
stdout is redirected to stderr for the rest of the step because the runner
does not order the two streams against each other.

## URL credentials: inputs and masks

`scripts/action/url-credentials.sh` (builtins only: no python, no external
program; bash 3.2 and Git Bash) is sourced first by the Generate step.

- `mask_url_secrets` prints one `::add-mask::` per credential-shaped piece of
  each URL word (`://` or `:/` after a scheme of two or more characters,
  once an option prefix such as `--model=` and a leading quote are
  dropped, one rule for both: the detector reads `https:/u:p@h` as a URL;
  `C:/x` and `123:/x` are paths) in
  `project-path`, `model`, `args` and `accept-url-credentials`: the user
  information up to the last `@` before the first `/` (as git reads it),
  its password, the query and fragment, each `name=value` pair and each
  value. A quote, bracket, `,` or `;` at either end of a piece is dropped
  (review: `--x "https://h/r?token=T"` masked `token=T"`, which matched no
  output printing the URL unquoted). A query value is masked whatever its
  name (a non-secret value of 6 or more characters is hidden too: the safe
  direction, no second copy of the detector's name list). A password
  holding a space is split by the word split and not masked whole (limit).
  These are the inputs that can hold a URL; `embed-wheel`,
  `output`, `config`, `id-registry` are paths and `pitloom-version` is
  prefixed `pitloom==` (no URL). A value is split into lines and then on
  space and tab (each mask is one line), `%` is written `%25` and a CR
  `%0D` (the runner decodes both). Pieces under 6 characters are not masked:
  a mask is a substring rule over the whole log, and `h=1` or `git` would
  hide every such run.
- Limits: the runner prints the step's `env:` (the inputs) before the step
  runs, so a mask covers loom's output and the later steps, never that echo.
  Only a credential given as `${{ secrets.X }}` is masked from the start.
  The decoded form of a percent-encoded password is not masked (Pitloom
  masks its own output).
- `add_url_credential_args` maps `url-credentials` (`warn` default or empty:
  no flag; `refuse`: `--refuse-url-credentials`; else `::error::`, exit 1)
  and `accept-url-credentials` (commas or line breaks; each entry trimmed,
  shape-checked as `sha256:` and 16 to 64 lowercase hex, the CLI's
  `FINGERPRINT_RE`, a drift test compares them) into `loom_args`, before the
  `args` words. A refused entry is masked and its position, never its
  value, is printed. Default `warn` matches the CLI; the docs recommend
  `refuse` in CI. `warn` cannot turn off a project's `refuse` (the flag
  only turns it on).
- Tests: `tests/scripts/action/test_url_credentials.py`; each decision was
  mutation-checked (10 mutants, all killed). `shellcheck -x` passes on
  `scripts/action/*.sh` and on the extracted `run:` block (one older
  SC2154 on `python_bin`, set by the sourced resolver); `actionlint` does
  not read action metadata, only `.github/workflows/` (clean).

## Version pinning and Python selection

**Pitloom version.** With `pitloom-version` empty,
`scripts/action/pitloom-install.sh` reads `__version__` from the pinned checkout
(`scripts/check_version_consistency.py --print-version`, the reader the CI
version check also uses) and installs `pitloom==<that>` from PyPI. Tag, SHA and
branch all work, since `GITHUB_ACTION_PATH` is the checkout of the pinned ref.
A version not on PyPI fails with a pin hint: there is no source-install
fallback, so "the pin means this release" always holds.

**Python.** With `python-version` empty, `scripts/action/python_probe.py`
checks the `python` on `PATH`: at least 3.10, pip present, not PEP 668
externally managed (unless in a venv or `PIP_BREAK_SYSTEM_PACKAGES`),
purelib/platlib/scripts writable, scripts dir on `PATH`. If not, the action
warns and runs `setup-python` `3.x`. `pip install --upgrade pip` is not run:
it is redundant on a fresh interpreter and mutates the user's own. The
scripts-dir check predicts where `loom` lands; it can reject a usable pyenv or
Homebrew Python (a warning and a fallback, the safe direction) and ignores
`pip.conf`.

`scripts/action/python-resolve.sh` is sourced by the probe step, the install
script and the Generate step: one definition of "which python" (first of
`python`, `python3` that runs as Python 3; skips a Windows Store stub), plus
`python_text` and `require_python`. Only the Generate paths that call Python
(embed-wheel, `args`) require one, so `install: "false"` with `loom` from pipx
still works.

**Windows and encoding.** Native Windows Python ends every line with CR, which
Git Bash `$(...)` keeps. `python_text` strips it and forces UTF-8 stdio; the
Generate step strips CR from `loom`'s output, and `GITHUB_ACTION_PATH` is
normalised to forward slashes. `check_version_consistency.py` reads
`__about__.py` as `utf-8-sig` and the JSON files as bytes (BOM-safe).
`.gitattributes` forces LF on `*.sh` and `action.yml`, and a test checks them
for BOM, CR and non-ASCII. Git Bash has no `/dev/stderr`, so the Generate step
tees `loom`'s stdout and stderr to files through pipeline members (fd 3), not
process substitutions, which `wait` would not cover. The `args` split uses a
read loop (macOS's bash 3.2 has no `readarray`) over records ended by an ASCII
record separator, so empty arguments and embedded newlines survive `$(...)`.

**Paths considered and rejected**

- `github.action_ref`: unreliable in composite steps and cannot map a SHA to a
  version. Parsing the ref out of `GITHUB_ACTION_PATH` has the same SHA problem.
- Installing from `GITHUB_ACTION_PATH` for an unreleased version: needs the
  self-referential `pitloom` build-requires bootstrap
  (`.github/actions/install-pitloom`), is slower, and differs from the PyPI
  wheel. Deferred.
- A fresh venv: hides the runner's build backend from
  `--allow-build --no-build-isolation`, which means to use it.
- `python -m pitloom` instead of `loom`: would change the `install: "false"`
  surface, which the self-test relies on.
- Try the install, then fall back, instead of a probe: would half-mutate the
  user's environment on a partial failure.

**Tests.** `.github/workflows/action-selftest-install.yml` runs copies of the
action whose `__about__.py` carries a fixed published version (`0.22.0`, older
than latest, so ignoring the pin cannot pass; override `0.22.1`), on ubuntu,
macOS and Windows. Both cap `licenseid` below 0.7; an older release takes
LicenseID 0.7 and fails to import.
`tests/scripts/` covers the probe, version reader, resolver, install script and
the Generate step's `run:` block against stub programs (POSIX only). PR #224's
runs confirmed the Windows and macOS legs.

## Design notes

- The Action is **composite** (`runs.using: "composite"`), not a Docker
  action -- faster to start, no image to publish, and Marketplace-friendly.
  A Docker variant (for hermetic or self-hosted-runner use) is tracked in
  [roadmap.md](../design/roadmap.md) as future work.
- Every `run:` block uses `set -euo pipefail` and quotes all inputs, so a
  malformed or empty input fails the step rather than silently doing the
  wrong thing.
- Third-party actions are pinned by full commit SHA, with the resolved
  version as a trailing comment (`actions/checkout@<sha> # v7.0.1`,
  `actions/setup-python@<sha> # v7.0.0`), not by a mutable major-version
  tag.
- Hardening still open: hash-pinned transitive dependencies, an isolated venv
  option, lint `scripts/` in CI, `args` edge cases.
