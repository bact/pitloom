---
Created: 2026-09-28
Last-Modified: 2026-10-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Testing / CI follow-ups

See also: [roadmap.md](roadmap.md) (the summary bullet this file expands
on), [windows-macos-ci.md](../implementation/windows-macos-ci.md),
[ci-install-composite-action.md](../implementation/ci-install-composite-action.md),
[allow-build-termination.md](../implementation/allow-build-termination.md).

Split out of `roadmap.md` (2026-09-28) once this section grew past the
file-size guidance -- moved verbatim, no content changed.

- [x] **Real Windows and macOS CI runs** -- `test.yml`/`build.yml` now
  cover `windows-latest`/`macos-latest`, not just `ubuntu-latest`. The
  first Windows run immediately surfaced 7 real test failures (all
  test-fixture bugs, no production code changed). See
  [windows-macos-ci.md](../implementation/windows-macos-ci.md).
  ([PR #220](https://github.com/bact/pitloom/pull/220))
- [x] **`fasttext` Windows/macOS + Python 3.14 gap** -- resolved upstream
  ([fasttext-community#13](https://github.com/munlicode/fasttext-community/pull/13)).
  See [windows-macos-ci.md](../implementation/windows-macos-ci.md).
  ([PR #222](https://github.com/bact/pitloom/pull/222))
- [x] **CI workflow step duplication** -- two shared composite actions
  replace hand-copied boilerplate across 10 of the 17
  `.github/workflows/*.yml` files: `setup-python` for the
  actions/setup-python version/cache config
  ([PR #221](https://github.com/bact/pitloom/pull/221)) and
  `install-pitloom` for the Hatchling-pin/dependency-group/
  editable-install bootstrap. See
  [ci-install-composite-action.md](../implementation/ci-install-composite-action.md)
  ([PR #222](https://github.com/bact/pitloom/pull/222)). `checkout` stays
  inline in each file (a local composite action can't check itself out).
  `version-consistency.yml` (no cache/pip-install step) and the two
  intentionally-different `licenseid update` steps were left untouched.
- [ ] **Verify `--allow-build` termination on real platforms** -- the
  Windows paths (Ctrl-Break/SIGBREAK, `taskkill /F /T` tree kill) and
  Pitloom as PID 1 in a container without `--init` are covered by mocks
  only; the Linux child-subreaper e2e test runs only on Linux CI. See
  [allow-build-termination.md](../implementation/allow-build-termination.md).
- [x] **Build workflow fails on spdx.org network errors** -- `build.yml`'s
  `loom validate-wheel` and `spdx3-validate` steps now run through
  `scripts/retry_network.py`: up to 3 attempts (10 s, 30 s back-off, 300 s
  per attempt), retrying only a failure `tests/_network_classify.py`
  classifies as network, or a timeout. All attempts on the network exit
  75, which the step maps to `failure=network` and a distinct
  "Network Failure" `::error::` and summary row; the job still fails, never
  skips. Any other failure is final on the first attempt. Fail-fast still
  cancels the other matrix legs once retries are exhausted.
- [ ] **Network retry for the other validating workflows** -- same
  failure mode, not yet wrapped: `pypi-publish.yml` (`loom validate-wheel`,
  `spdx3-validate`; a retry keeps the strict gate, since exhausted retries
  still fail), `hatch-integration.yml` (`loom validate-wheel`) and
  `action-selftest.yml` (`pitloom fragment validate`). Caching or vendoring
  the schema/context remains an alternative to retrying.
- [ ] **Manual-check matrix: standalone `embed-wheel` on `gated-wheel`** --
  add a cell for `--trust-wheel-model` in `scripts/manual_cli_checks/_matrix_plan.py`
  (today only `wheel` runs it live; the other cells are inert).

## CI workflow review (0.20.0)

Found reviewing `.github/` before tagging v0.20.0 (2026-10-05); none
blocked the release. Highest first.

- [ ] **`codemeta2cff.yml` runs third-party code with a write token
  (high).** The `contents: write` job keeps checkout credentials and runs
  `caltechlibrary/codemeta2cff` (downloads and runs a datatools release
  zip, no checksum) and `dieghernan/cff-validator` (builds `FROM` a mutable
  `rocker/tidyverse` tag). `push:` has no `branches:`, and path filters do
  not apply to tag pushes, so it runs on every tag. Split a read-only
  generate+validate job (`persist-credentials: false`) from a small commit
  job; limit to `branches: [main]`.
- [ ] **Dependabot misses the composite actions (medium).** The
  `github-actions` entry scans `/` only; `.github/actions/*/action.yml`
  (the `actions/setup-python` pin nearly every workflow uses) gets no
  bumps. Use `directories: ["/", "/.github/actions/*"]`.
- [ ] **Docs build only after merge (medium).** `docs.yml` runs `mkdocs
  build --strict` on push to `main` only; add a `pull_request` trigger and
  gate the deploy job.
- [ ] **Action self-test is Linux-only (medium).** The embed-wheel branch,
  the `args` parsing loop and `--allow-build` in `action.yml` never run on
  Windows Git Bash or macOS bash 3.2; `action-selftest-install` covers plain
  project mode only. Add a Windows and a macOS leg.
- [ ] **Release re-runs (medium, process).** After `publish` has run, use
  "Re-run failed jobs" only, within the 3-day artifact retention: "Re-run
  all jobs" rebuilds a wheel with a new `created` time, which PyPI refuses
  and the release assets would no longer match. Setting `SOURCE_DATE_EPOCH`
  ([known-bugs.md](known-bugs.md#p3-after-0200)) would make a rebuild
  identical.
- [ ] **`ubuntu-latest` becomes Ubuntu 26 from 2026-10-19 (medium).**
  Every Linux job moves with the label
  ([runner-images#14748](https://github.com/actions/runner-images/issues/14748)).
  Watch the first runs after that date; pin `ubuntu-24.04` on the release
  path (`pypi-publish.yml`) if anything breaks.
- [ ] **`release: published` fires for a pre-release too (low).** A
  GitHub pre-release goes to PyPI; skip it or document it.
- [ ] **`changelog-check.yml` uses a two-dot diff (low).** A PR whose base
  is behind `main` sees `main`'s own CHANGELOG edits and passes vacuously;
  use `base...head`, SHAs through `env:`.
- [ ] **Raw tool output in the Action (low).** `scripts/action/pitloom-install.sh`
  echoes pip output and `action-selftest-install.yml` the script's output
  without a `::stop-commands::` fence; `action.yml` puts the probe's
  `reason` into `::warning::` without `%` escaping.
- [ ] **Unvalidated or spliced inputs (low).** `fuzz.yml` splices
  `inputs.duration_seconds` into `run:` (no integer check); `build.yml`
  splices step outputs (`wheel_name`, `sbom_path`) into `run:`. Pass
  through `env:`.
- [ ] **No `timeout-minutes` (low).** `pypi-publish.yml`'s publish, attach
  and sign jobs and every other reviewed workflow use the 6-hour default.
- [ ] **`install-pitloom` env var `GROUPS` (low).** A bash special
  variable (works today since the inherited value wins); rename
  `DEP_GROUPS`.
- [ ] **Coverage gaps (low).** `test.yml` has no Python 3.12 leg;
  `build.yml` builds the wheel from the tree, the release from the sdist.
- [ ] **Small hygiene (low).** `actionlint.yml` `curl` without `-f` and no
  binary checksum; `bandit.yaml` has no SPDX header or branch filter;
  `version-consistency.yml` paths omit the workflow itself;
  `ms-sbom-tool.DISABLED` pins actions by tag and has no `permissions:`.
