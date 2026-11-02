---
Created: 2026-11-02
Last-Modified: 2026-11-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Known bugs: process, tooling and release checks

See also: [known-bugs.md](../known-bugs.md) (index, severity scale,
rules for adding an entry), [roadmap.md](../roadmap.md),
[testing-ci-followups.md](../testing-ci-followups.md),
[release-checklist.md](../../implementation/release-checklist.md).

CI, test layout, linters, release reproducibility and the release-check
records. Entries are ranked by priority tier, then by size tag; see the
severity scale in the index. Open entries come first; fixed entries stay in
the last section for history.

## Open

### P3: after 0.20.0

- [ ] Pin one CI leg to an unpatched `zipfile` (pre CVE-2025-8291).
- [ ] The signed release wheel and SBOM are not reproducible: `created`
  and `builtTime` come from the clock. Set `SOURCE_DATE_EPOCH` (last
  commit time) in `pypi-publish.yml`'s build job so anyone can rebuild and
  compare against the signed bytes.

### Found in review rounds, not yet prioritised

- [ ] **`assemble/spdx3/document.py` is 516 lines (doc).** Over the soft
  limit; split it.
  *Found 2026-10-30, from #407 (registry package key).*
- [ ] **The skills and example floors at 0.22.0 do not install until 0.22.0 is
  on PyPI (doc).**
  *Found 2026-10-30, from #407 (registry package key).*
- [ ] **Top-level test files share a prefix (doc).** `provenance`, `build` and
  `network` each have 3 or more; group them in subfolders after 0.22.0, with a
  lint that fails at 3 or more.
  *Found 2026-10-30, process and tooling.*
- [ ] **CI repeats itself (doc).** The push run after a merge repeats a green
  PR tree, and a markdown-only follow-up commit re-runs the matrix because
  `paths-ignore` is judged on the whole PR diff.
  *Found 2026-10-30, process and tooling.*
- [ ] **Two pylint findings exist on `main` (doc).** E1101 at
  `logging_config.py:251` and C1803 at
  `tests/extract/project/test_poetry_extract.py:151`.
  *Found 2026-10-30, process and tooling.*
- [ ] **pyright cannot resolve `magika` in the dev venv (doc).**
  *Found 2026-10-30, process and tooling.*

## Fixed

Kept for history, with the PR. A fixed entry moves to
[roadmap-completed.md](../../implementation/roadmap-completed.md) once its
release ships.

### Fixed, P2: 0.21.0 and later

- [x] **`test_member_order_does_not_change_the_sbom` is flaky (S).** Fixed by
  #279. It runs `generate_project_sbom` three times without `SOURCE_DATE_EPOCH`,
  so a second boundary between runs changes `created` (failed once locally under
  load, 2026-10-04). Pin the epoch in the test.

### Fixed, Found in review rounds, not yet prioritised

#### Release checks re-run (2026-11-02)

The 0.22.0 checks that were left to CI, run on `main` at `06bb06c6` (Python
3.10, Linux, 4 CPUs). The leftover `0.21.2` review was not part of this run.

- [x] **Full manual CLI checks:** 610 checks, 551 pass, 0 fail, 22 known, 37
  skip. The 22 known are the allow-listed Harvest finding (O2 random walks,
  `_order_known.py`). Of the 37 skips: 23 need `--network` (4b, 10 and 21
  matrix cells of `validate-wheel`, `fragment validate` and `embed-wheel
  --validate`); they are skipped by design unless the flag is given, not for a
  missing tool or extra, and all 23 pass with `--network`. Check 25 and the 7
  O4 cells skip as root; run as `nobody` (a copy of the tree and interpreter
  outside `/root`), 25 passes and the 7 O4 end `KNOWN` as above. The 6 O6
  cells skip on a case-sensitive file system; they need a case-insensitive
  one (macOS or Windows CI) and were not run.
- [x] **CHANGELOG against merged PRs, `v0.21.1..v0.22.0`:** 42 merged; 21
  have an entry. The other 21 are docs, design and paper notes (#367, #368,
  #373, #379, #380, #383, #388, #393, #394, #397, #398, #406, #409),
  Dependabot bumps (#369 to #372), a test-only split (#377), the 0.21.2 and
  0.22.0 release PRs (#403, #411) and #391. After the tag only the `Model
  usage scan plan` commit (`06bb06c6`, docs) is on `main`. #391 (the internal
  `Fact` evidence type) needs no entry: nothing it adds is exported or
  user-visible.
- [x] **Coverage snapshots:** the four `0.22.0` snapshots (`g7ai`, `cisa2026`,
  `fsct3`, `bsi`) equal fresh output of `scripts/g7_coverage_report.py` apart
  from `header.pitloom` (the sandbox venv's installed metadata says 0.21.1).
- [x] **`scripts/` lint:** `ruff` (check, format), `mypy`, `pyright`,
  `bandit`, `shellcheck -x scripts/action/*.sh` and `actionlint` are clean;
  `flake8` and `pylint` had five findings (CCR001 in `_order_invariants.py`,
  R0911 in `_checks_order.py`, R0914 in `_checks_model.py`, `_checks_lfs.py`
  and `_checks_core.py`), fixed by splitting the functions; the touched
  checks (14, 17, 23, O*) give the same results and messages before and after.
