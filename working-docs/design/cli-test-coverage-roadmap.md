---
Created: 2026-08-14
Last-Modified: 2026-08-17
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# CLI split, test-suite modularization, and coverage roadmap

**Status:** Phases 1-3 shipped. `src/pitloom/cli/` exists,
`tests/cli/`/`tests/core/`/`tests/extract/`/`tests/assemble/` exist,
`fail_under` is 90 (met, 91.83% measured). What's genuinely still
open: ~10 test files over the 800-line hard cap (see Phase 2), and
the 95% coverage stretch target (see Phase 3). See "Next step" at the
bottom for both.

## Three tech-debt items, one sequencing problem

1. **Test coverage** was at 87.32% (Codecov) when this doc was
   written; we want it maintained around 95%, with a 90% hard floor
   (OpenSSF baseline). `fail_under` was 88 at the time.
2. **Test suite files were too big.** `tests/` was 32k+ lines across
   ~48 files, concentrated in a handful of monoliths.
3. **`src/pitloom/__main__.py` was too big** (1,320 lines) and its
   own coverage (71%) was well below everything else in the tree.

These weren't independent: item 3 changed the module boundaries item
2's test-file boundaries needed to track, and both changed what
"backfill coverage" even meant for item 1. Order mattered -- see
"Recommended order" below for the rationale that was followed.

## Original baseline (measured 2026-08-14, historical)

See Phase 3 below for current numbers.

- **Coverage baseline mismatch**: local run (Python 3.10.18) showed
  89.51% total; Codecov showed 87.32%. Cause: CI
  (`.github/workflows/test.yml`) only ran `--cov` on the Python 3.14
  matrix leg, not 3.10.
- **Worst-covered files at the time**: `__main__.py` 71% (491 stmts /
  115 miss), `extract/sdist.py` 69%, `extract/wheel.py` 71%,
  `export/spdx3_json.py` 75%, `extract/pyproject.py` 77%,
  `extract/_hdf5.py` 83%, `extract/scanner.py` 84%,
  `assemble/__init__.py` 85%.
- **Largest test files at the time**: `test_extract_huggingface.py`
  9,357 lines, `test_generator.py` 3,050 lines, `test_main_cli.py`
  1,720 lines, `test_hatch_hook.py` 1,445 lines, `test_fragments.py`
  1,063 lines.
- **`tests/` layout at the time**: flat, ~48 files, no subfolders
  except `tests/fixtures/`.

## Recommended order: cli split -> test modularization -> coverage

1. **Split `__main__.py` into `pitloom/cli/`** first. Pure structural
   refactor, no behaviour change.
2. **Modularize the test suite** once the new source boundaries exist,
   so test-file boundaries can mirror them.
3. **Backfill coverage and raise the floor** last, once code and
   tests are both in their final shape.

Rationale: writing new tests against `__main__.py` first would mean
rewriting them again once the file split -- wasted work. Splitting
tests before splitting source would mean guessing at boundaries that
didn't exist yet. Source split, then test split, then coverage
backfill avoided doing anything twice.

**Pre-1.0**: no backward-compatibility constraint applied to any of
this (`AGENTS.md`: "private alpha, one developer, no backward compat
needed yet"). Renames, moves, and deletions across all three phases
skipped deprecated re-export shims, aliasing, and migration warnings.

## Phase 1: split `__main__.py` into `pitloom/cli/` (COMPLETE)

Shipped layout (matches the flat-multi-module-package convention
`pitloom/core/`, `pitloom/assemble/`, `pitloom/extract/` already use;
differs from this doc's original prediction of a `cli/modes/`
subpackage -- actual is `cli/commands/`, and `ids.py` lives at the
`cli/` root rather than inside `commands/`):

- `cli/parser.py` -- `_build_parser`, `_build_parent_parser`, the
  custom `argparse.Action` classes.
- `cli/options.py` -- `_resolve_common_options`,
  `_resolve_creation_metadata`, `_resolve_output_path`, and the
  per-target output-path resolvers.
- `cli/verbose.py` -- `--verbose` effective-options report.
- `cli/constants.py` -- shared literals (`.spdx3.json` extension,
  source labels).
- `cli/commands/` -- one file per verb, each with a
  `_run_<verb>_command(args)` function and an `add_parser(subparsers,
  parent_parser)`: `generate.py`, `project.py`, `wheel.py`,
  `embed_wheel.py`, `model.py`, `enrich.py`, `env.py`, `merge.py`,
  plus a shared `utils.py` (`cli_error_handler` decorator, wheel-glob
  path collection).
- `cli/ids.py` -- `_run_ids_generate`, `_run_ids_import`,
  `_run_ids_command` (renamed from `_run_ids_cli` 2026-08-17, see
  "Naming pass" below), `add_parser`. Registry helpers
  (`_load_or_create_registry`, `_default_ids_generate_paths`) live in
  `pitloom.ids`, imported from there.
- `__main__.py` shrank to 46 lines: `_configure_logging()`, `main()`'s
  `args.func(args)` dispatch, `if __name__ == "__main__"` guard.

The test-patch risk originally called out here (`test_main_cli.py`
monkeypatching names in the `pitloom.__main__` namespace) was resolved
as part of the Phase 2 split below -- patch targets now point at each
command's own `pitloom.cli.commands.<verb>` module.

## Phase 2: test-suite modularization (COMPLETE)

### Folder-vs-flat decision

**Group by folder once an area reaches 3+ related test files,
otherwise stay flat.** Same threshold `AGENTS.md` already codifies
for `working-docs/`. Recorded as a standing rule in `AGENTS.md`'s
Testing section, not just here.

Shipped folders:

- `tests/extract/` (27 files, mirrors `src/pitloom/extract/`), with
  `tests/extract/huggingface/` (6 files) as a further split of the
  9,357-line `test_extract_huggingface.py`.
- `tests/assemble/` (15 files, covers `assemble/`, `embed.py`,
  `enrich/`).
- `tests/cli/` (11 files, mirrors `src/pitloom/cli/`): `shared.py`
  (helpers, not a `conftest.py`), `test_cli_enrich.py`,
  `test_cli_generate.py`, `test_cli_ids.py`, `test_cli_merge.py`,
  `test_cli_model.py`, `test_cli_options.py`, `test_cli_parser.py`,
  `test_cli_project.py`, `test_cli_verbose.py`, `test_cli_wheel.py`.
  **Gap**: no dedicated `test_cli_env.py` or `test_cli_embed_wheel.py`
  -- those command modules are only incidentally exercised via
  `test_cli_generate.py` and `tests/assemble/test_embed.py`. Not
  blocking (both modules are 88%/94% covered per Phase 3 below), but
  worth adding if either command grows.
- `tests/core/` (20 files: `core/`, `ids.py`, `loom.py`, generator
  orchestration).
- Single-file areas stayed flat at `tests/` root
  (`tests/enrich_readme_test.py`-style singletons, `tests/ids_shared.py`
  for shared registry-test helpers, root `tests/conftest.py` for
  genuinely cross-cutting fixtures).

No `__init__.py` needed in any new folder --
`--import-mode=importlib` (`pyproject.toml:240`) allows same-named
test files across directories.

### Still oversized (open follow-up, not this doc's scope to fix)

The split happened, but several resulting files are still over
AGENTS.md's ~800-line hard cap and would benefit from a further pass:

- `tests/extract/huggingface/conftest.py` -- 5,424 lines
- `tests/extract/huggingface/test_huggingface_misc.py` -- 3,124 lines
- `tests/core/test_generator_project.py` -- 1,260 lines
- `tests/assemble/test_deps_enrichment.py` -- 1,147 lines
- `tests/assemble/test_embed.py` -- 1,057 lines
- `tests/core/test_metadata.py` -- 987 lines
- `tests/core/test_generator_model.py` -- 918 lines
- `tests/assemble/test_annotation_provenance.py` -- 906 lines
- `tests/core/test_loom.py` -- 855 lines
- `tests/extract/test_setuptools.py` -- 829 lines

Plus roughly 10 more files over the 400-500 soft limit but under the
hard cap. Not urgent -- these are all functioning, organized-by-topic
files; the remaining split work is about AI-agent context economy,
not correctness.

### Naming pass (COMPLETE 2026-08-17)

- **`_run_ids_cli` renamed to `_run_ids_command`** in
  `src/pitloom/cli/ids.py`, aligning it with the `_run_<verb>_command`
  pattern every other `cli/commands/*.py` module already used.
  `tests/cli/test_cli_ids.py` updated to match (import + 2 call
  sites). `_run_ids_generate`/`_run_ids_import` (the sub-handlers
  `_run_ids_command` dispatches to) were left as-is -- they aren't
  the `set_defaults(func=...)` target, so the `_command` suffix
  doesn't apply to them.
- **`test_extract_project.py` vs `test_core_project.py` clash
  resolved**: the actual files were `tests/extract/test_project.py`
  (tests `pitloom.extract.project.read_project()`, the pyproject/
  setup.cfg/setup.py dispatcher) and `tests/core/test_project.py`
  (tests `pitloom.core.project.merge_project_metadata()`/
  `ProjectMetadata`, plus some `pitloom.extract._license` cases it
  happens to carry). Renamed `tests/core/test_project.py` ->
  `tests/core/test_project_metadata.py` (matches what it actually
  tests) and left `tests/extract/test_project.py` alone, since that
  one is a clean 1:1 mirror of `extract/project.py` matching every
  other file in that folder (`test_wheel.py`, `test_scanner.py`,
  etc.) -- renaming it would have broken the mirror convention
  instead of fixing an outlier.

### Underscore-prefix audit for `extract/` (and beyond)

`AGENTS.md`'s Naming section states the rule: a module gets a leading
underscore when nothing outside its own package directory imports it
(an internal adapter/parser/helper); no prefix when something outside
the package imports it (a stable entry point), with an explicit
`__all__`/public-API-docstring facade as a second signal that
overrides a zero-internal-importer reading.

The four likely outliers identified in the original audit --
`pyproject.py`, `sdist.py`, `poetry.py`, `setuptools.py` -- were
renamed to `_pyproject.py`, `_sdist.py`, `_poetry.py`,
`_setuptools.py`. `dataset.py` was confirmed a deliberate exception
(explicit `__all__` + public-API docstring) and kept unprefixed. The
follow-up check across `core/`, `assemble/`, `export/`, `enrich/`
found no further outliers -- those packages already followed the
rule.

## Phase 3: coverage backfill and floor raise (COMPLETE)

`fail_under` is **90** (`pyproject.toml:338`). Measured 2026-08-17
(Python 3.10.18, `pytest -n auto --dist=loadscope --cov=pitloom`):
**91.83% total, 1936 passed / 24 skipped, ~11s.** All of `cli/*` is
88-100% covered (`generate.py`/`project.py`/`ids.py` at 100%).

Current worst-covered files (re-measure on 3.14/Codecov before
treating as ground truth -- this is a 3.10 local run):

1. `extract/_sdist.py` -- 72%
2. `extract/wheel.py` -- 75%
3. `export/spdx3_json.py` -- 75%
4. `extract/_pyproject.py` -- 77%
5. `extract/_hdf5.py` -- 83%
6. `extract/scanner.py` -- 84%
7. `assemble/__init__.py` -- 85%

The 95% stretch target has not been reached (currently 91.83%). Not
a blocker -- it's an aim, not a second hard CI gate -- but the file
list above is where a future backfill pass should start.

## Test performance and caching

Measured 2026-08-17: 1936 passed / 24 skipped in ~11s using
`pytest -n auto --dist=loadscope --cov=pitloom` -- `pytest-xdist` is
in use (this doc originally flagged it as a future trigger-based
option; it was adopted along with the folder split). No known
test-order-dependency flakiness surfaced from parallelization so far.

- The Phase 2 folder split is itself a speed win for iteration
  regardless of parallelism: `pytest tests/extract/` collects ~30
  small files instead of one 9,357-line file, so working on one area
  no longer pays collection/parse cost for unrelated areas.
  `pytest --lf`/`--ff` and the default `.pytest_cache` give this for
  free once files are small enough that "the file being edited" and
  "the tests worth rerunning" line up 1:1.
- If suite time grows further, per-directory CI matrix legs
  (`-n auto --dist loadgroup` per folder) are the next lever -- not
  needed at ~11s total.

## Next step

Two genuinely open items, either can be picked up independently:

1. **Split the remaining oversized test files** listed under Phase
   2's "Still oversized" section, starting with
   `tests/extract/huggingface/conftest.py` (5,424 lines) and
   `tests/extract/huggingface/test_huggingface_misc.py` (3,124
   lines) -- the two furthest over the 800-line hard cap.
2. **Push coverage toward the 95% stretch target**, starting with the
   Phase 3 priority list (`extract/_sdist.py` 72% first).

### Pickup prompt for a new session

```text
Read working-docs/design/cli-test-coverage-roadmap.md in full. Phases
1-3 (the __main__.py -> cli/ split, test-suite modularization, and
coverage floor raise to 90) are all COMPLETE -- do not redo them.

Two items are still open, see "Next step":

1. Split the test files listed under Phase 2's "Still oversized"
   section (all over AGENTS.md's ~800-line hard cap), starting with
   tests/extract/huggingface/conftest.py (5,424 lines) and
   tests/extract/huggingface/test_huggingface_misc.py (3,124 lines).
   Mechanical relocation only -- no test-logic changes. Pick sub-area
   boundaries from each file's existing section/class structure, not
   guessed ahead of time.

2. Backfill coverage toward the 95% stretch target using Phase 3's
   priority list (extract/_sdist.py at 72% first). Re-measure current
   percentages before starting -- Phase 3's numbers are a 2026-08-17
   3.10-local snapshot and will have drifted.

Pre-1.0, so no backward-compat shims needed for any renames this
touches. Run the full test suite and the project's lint/type-check
commands (AGENTS.md "Linting and formatting") before considering
either item done.
```
