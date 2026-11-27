---
Created: 2026-11-10
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Recurring bug patterns: what the CI matrix shows and a local run does not (from PR #464)

See also: [recurring-bug-patterns-platform.md](recurring-bug-patterns-platform.md)
(the main platform and CI list; test-harness items are in
[recurring-bug-patterns-test-harness.md](recurring-bug-patterns-test-harness.md)),
[recurring-bug-patterns-platform-windows.md](recurring-bug-patterns-platform-windows.md)
(Windows-only findings), [recurring-bug-patterns.md](recurring-bug-patterns.md),
[recurring-bug-patterns-review-rounds-pr359-378.md](recurring-bug-patterns-review-rounds-pr359-378.md),
[CLAUDE.md](../../CLAUDE.md) ("Recurring bug patterns" -- the short summary),
[model-sbom-from-git.md](model-sbom-from-git.md) (the feature round).

Failures that only a CI leg showed, because the local environment was on a
different dependency release or interpreter patch version. Entries follow the
format of the platform list.

- **CI installs the newest release inside the declared range; the local
  environment lags.** `licenseid>=0.8.3,<0.9` gave 0.8.3 locally and 0.8.4 on
  CI. 0.8.4 reads `MIT/Apache-2.0` as `Apache-2.0 OR MIT`, so a test that
  pinned it as text failed on the 3.14 leg only (CI log, 2026-11-09). Before
  a push, compare the version the CI log installed with `pip list` (or
  `uv pip list`) and upgrade the local environment to it; rebuild the licence
  database after the upgrade. A test of a third-party reading either pins the
  floor's behaviour on purpose (say so in its docstring) or asserts only what
  holds for the whole range. Raising the floor in the same change, once the
  newer release is the one that is tested, keeps the floor honest.
- **The failure mode of a parser given hostile nesting changes with the
  interpreter patch version, and on 3.10 and 3.11 even valid deep JSON fails.**
  Extends the 3.14 finding of #270 in
  [sbom-generator-field-notes/determinism-and-parsing.md](sbom-generator-field-notes/determinism-and-parsing.md).
  `b"[" * 100_000` gave "nested too deeply" on Python 3.14.6 and "Expecting
  value" on 3.14.10; a valid 1,000-deep document, written by `json.dumps` or
  read by `json.loads`, raises `RecursionError` on 3.10 and 3.11, where
  nesting counts against `sys.getrecursionlimit()`. Assert a stable prefix
  (`"is not valid JSON ("`), build a valid deep value only to a depth every
  supported version accepts (about 300), and test the exact wording by
  forcing `RecursionError` with a stub on the module under test. Take the
  patch versions from the CI log, and read the cancelled legs: fail-fast hid
  the 3.10 and 3.11 results of the first failure.
- **A dependency's new answer shape can switch a rule off with every test
  green.** LicenseID 0.9.4 (inside `>=0.9.3,<0.10`) returns no match for a
  file of several licence texts and lists them through a new `texts()`;
  #554's rule read them off the first match and never fired again. The suite
  passed because its case used a text 0.9.4 still flagged, every fixture
  project had one licence file and the fakes lacked `texts()` (fixed in
  #563). On an upgrade, run a before/after sweep through the real library
  over multi-input cases, and make fakes answer every call the code makes.
- **A workflow's event payload is a snapshot.** A push and the `test-all-os`
  label within a second started two runs in one concurrency group; the push's
  run, queued last, cancelled the labelled one and, its payload predating the
  label, ran only the `platform` subset: #563 was green with about 21,000
  tests on macOS and Windows instead of 31,000. #566 reads the labels from
  the API at job time, failing open. Read mutable state when the job runs,
  and check each leg's test count before calling a PR merge-ready.
