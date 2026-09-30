---
Created: 2026-09-28
Last-Modified: 2026-09-30
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
