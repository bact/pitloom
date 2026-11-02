---
Created: 2026-11-02
Last-Modified: 2026-11-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: behaviour-preserving refactors, proved by output equality

See also: [README.md](README.md) (index of these notes),
[process-lessons.md](process-lessons.md) (proving a test compaction),
[name-keyed-lookups-and-direct-references.md](name-keyed-lookups-and-direct-references.md)
(why the prefetch leaves a direct reference out),
[testing-traps.md](testing-traps.md),
[open-research-questions.md](open-research-questions.md).

Two PRs of 2026-11-02 changed code and promised the same behaviour: #416
(release checks and a lint split of the `scripts/` manual checks) and #418
(a split of the SPDX 3 document module, a prefetch fix and two lint fixes).
Both were checked by comparing outputs, not by reading the diff. This note
keeps what was compared, what the comparison could not show, and three small
lessons that came out of the lint work. Where a figure comes from the working
session and not from the repository, it is marked *session record*.

## 1. Splitting functions the linters flagged (#416)

- **What changed.** Five functions of `scripts/manual_cli_checks/` were split
  (commit `8824820c`, 5 files, 163 insertions, 69 deletions): cognitive
  complexity in `_order_invariants.py`, too many returns in the order verdict
  (`_checks_order.py`), too many locals in checks 14, 17 and 23
  (`_checks_core.py`, `_checks_lfs.py`, `_checks_model.py`). CI lints only
  `examples/ src/ tests/`; `scripts/` is linted by hand, and the five findings
  are what that hand run in the 0.22.1 release checks found.
- **The proof.** The record says the touched checks (14, 17, 23 and the `O*`
  cells) "give the same results and messages before and after"
  (`working-docs/design/known-bugs/process-tooling-and-release-checks.md`,
  "Release checks re-run"). The session compared the status lines of the
  manual checks before and after: **147 lines equal** (*session record*; the
  repository holds the claim, not the two outputs).
- **What equality of status lines does not show.** The check's *result* and
  *message* are equal, not its side effects (temporary files, the processes it
  starts), and not the order in which it prints when a check fails, since the
  run was clean. A refactor of a check that is only exercised when it fails
  is proved only on its passing path.
- **Skipped and "known" cells prove nothing.** The release-check run of
  2026-11-02 (on `main` at `06bb06c6`, before the split) had 22 checks in the
  state `known` (an allow-listed finding, "O2 random walks") and 37 skipped (23
  need `--network`; a root user skips check 25 and 7 `O4` cells; 6 `O6` cells
  need a case-insensitive file system). Equal output from a skipped check is
  not equal behaviour. The record names the touched checks (14, 17, 23 and
  `O*`) but does not say whether any touched `O*` cell was among the skipped
  ones, so the proof's reach over them is unstated.

## 2. Splitting a 516-line module (#418)

- **What changed.** `assemble/spdx3/document.py` was 516 lines, over the
  soft limit (a ledger entry from #407 had flagged it). Commit `be65a8e0`
  moved the creation objects and the main-package builder to
  `_document_main_package.py` (115 lines); `document.py` is now 411 lines. The
  deployed route (`build_deployed()`) imports the new module directly, so a
  lazy import went away: the split removed a smell as well as lines.
- **The proof.** The commit message says "SBOM output is unchanged". The
  session ran **33 fixtures through the old and the new tree and compared the
  SBOM bytes and the stderr** (*session record*): identical. The repository
  does not hold the harness or the outputs; the `tests/fixtures` directory
  lists 18 entries, so "33" counts files or projects inside them, which I did
  not recount.
- **What this proof needs to be sound.** Two runs differ at the clock unless
  it is pinned (`--creation-datetime` or `SOURCE_DATE_EPOCH`; the project's
  determinism rule). How the harness pinned it is not recorded. If it did not,
  the bytes would differ in `created`, so equal bytes imply it did
  (*inference*). Stderr equality has the same need for any line that carries a
  path or a time; the harness's handling of those is not recorded either.
- **A follow-up that needed no proof.** Commit `4f29f262` turned one test into
  two cases (a version absent, and the placeholder `"unknown"`) for "no PURL
  without a real version". That is the tri-state of absent, placeholder and
  real, applied to the moved code. Why it was added after the split is not
  recorded.

## 3. A prefetch that resolved everything twice (#418)

- **The bug.** `document.build` prefetches PyPI release info for the
  dependencies it is about to build. The prefetch resolved every declared
  string itself, then the builder resolved them again: two routes to one
  entity, each with its own identity rule. Commit `8223e308`: "It now fetches
  the versions the groups already resolved, so one identity rule decides what is
  fetched and what is built, and each version is resolved once." The new
  `DependencyGroups.release_pairs()` returns the `(name, version)` pairs and
  leaves out a direct reference (`name @ URL`), because PyPI's record of that
  name may be another project (see the #405 note).
- **The count.** The new test (`tests/assemble/test_deps_prefetch_groups.py`)
  counts calls of `_resolve_version` and expects **5**: four declared strings
  and one that only the lock file names. On the old code the session counted
  **9** (*session record*). The arithmetic fits: 5 plus a second pass over the
  four declared strings is 9. The old run's warning count was not recorded.
- **A drift guard, not only a count.** The same test derives the keys a second
  way (`project_dependencies`, apart from `build()`) and asserts three sets
  equal: the pairs prefetched, the keys of the groups, and the packages in the
  built SBOM, each minus the direct reference. It also pins three outcomes: a
  declared pin beats the lock (`idna` 3.0, not 3.4), a range takes the locked
  version (`requests` 2.31.0), a lock-only package is fetched (`certifi`). This
  is the project's rule "every route that builds one entity shares its
  identity rule, plus a test comparing the routes' counts", written as code.
- **Why a count alone would not do.** A count of 5 proves each string is
  resolved once; it does not prove the *right* strings are fetched. The set
  equality does.

## 4. Two lint fixes and what they cost

- **A false positive through a proxy (E1101).** `logging_config.py` reads the
  stream behind a stderr proxy (`stderr_capture` swaps `sys.stderr` for an
  object with an `uncaptured_stderr` attribute) by attribute name, because
  `pitloom.extract` imports `logging_config`. `pylint` reported E1101 (no
  member) at line 251, apparently because it infers the value assigned
  (`sys.stderr`, a text stream) and not the `Any` annotation (*inference*; the
  commit message names the code only). The
  fix (commit `a6d57867`): a helper `_stream_behind(proxy: Any)` returns
  `cast("TextIO | None", proxy.uncaptured_stderr)`; the loop variable is typed
  `TextIO`. No suppression.
  - **Cost.** The `Any` parameter hides the attribute from `mypy` and `pylint`
    alike. The only remaining guard is the runtime test
    `hasattr(type(stream), "uncaptured_stderr")`. The helper moves the
    unchecked access into one named place instead of leaving it inline; it
    does not make it checked.
- **A weaker assertion (C1803).** In
  `tests/extract/project/test_poetry_extract.py` the lines
  `assert metadata.dependencies == []` and `... keywords == []` became
  `assert not ...`. `pylint` asked for it (an empty-literal comparison).
  The test is named for *empty declared dependencies*, a case the project
  separates from *absent* (`None`); `not x` passes for both. The next lines
  assert the provenance keys exist, which pins the "declared" half, so the
  change is probably harmless, but the assertion no longer distinguishes `[]`
  from `None` (*observation from the diff; no mutant run*). A lint rule
  that prefers truthiness collides with the project's own tri-state rule.
  Do: when a linter wants `== []` rewritten, write `is not None and not x`
  or `== []` with a disable-next that says why, or assert on the type.

## 5. What generalises

- **Prove a refactor on outputs, and say which outputs.** Status lines,
  SBOM bytes and stderr are three different proofs of different strengths.
- **A skipped or "known" case is an equal case.** Count them next to the
  passes, or the proof's coverage looks larger than it is.
- **A count catches "twice"; a set equality catches "wrong".** Use both when two
  routes must agree.
- **Fixing a lint finding is a design act when the rule encodes a distinction
  the code relies on** (a type, a tri-state). Read what the rule is protecting
  before choosing the rewrite.

## 6. Open

- Should the 33-fixture comparison be a script in the repository, so a
  reviewer can rerun it? It lived in session scratch; the same question was
  open for the patch-coverage script on 2026-10-30
  ([agent-work-lessons-oct30.md](agent-work-lessons-oct30.md), section 4).
- Should the manual checks print their pass/fail/known/skip status in one stable
  format that a `diff` can compare directly? The 147-line comparison was
  made by the session, not by a command in the repository.
