---
Created: 2026-09-28
Last-Modified: 2026-09-28
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
- [ ] **Build workflow fails on spdx.org network errors** -- `loom
  validate-wheel`, `loom fragment validate` and `spdx3-validate` fetch
  the SPDX schema, ontology and context over the network on every run;
  a `Connection reset by peer` failed two of PR #226's runs. Cache or
  vendor them, or retry. The step then reports "The SBOM does not
  conform to SPDX specification" for what was a download error, and
  fail-fast cancels the other matrix jobs: tell a network failure apart
  from a real validation failure.
