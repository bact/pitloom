---
Created: 2026-08-14
Last-Modified: 2026-08-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# CLI split, test-suite modularization, and coverage roadmap

**Status:** Phases 1-3 shipped and the 95% stretch target has since been
reached and exceeded. As of 2026-08-21: `src/pitloom/cli/` exists,
`tests/cli/`/`tests/core/`/`tests/extract/`/`tests/assemble/` exist,
`fail_under` is **97** (raised further from 95 -- **99.89%** measured,
2270 passed / 24 skipped). File-size limits have since drifted back
above what this doc originally reported -- see
[complexity-and-file-size-roadmap.md](complexity-and-file-size-roadmap.md)
for the current offenders, tracked there rather than duplicated here.
What's genuinely still open: nothing from this doc's original scope --
see "Next step" at the bottom for what comes after it.

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
  `export/spdx3_json.py` 75%, `extract/_pyproject.py` 77%,
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

- `tests/extract/` (36 files, mirrors `src/pitloom/extract/`), with
  `tests/extract/huggingface/` (23 files after the further split pass
  below) as a further split of the 9,357-line
  `test_extract_huggingface.py`.
- `tests/assemble/` (29 files after the further split pass, covers
  `assemble/`, `embed.py`, `enrich/`).
- `tests/cli/` (13 files, mirrors `src/pitloom/cli/`): `shared.py`
  (helpers, not a `conftest.py`), `test_cli_enrich.py`,
  `test_cli_generate.py`, `test_cli_hf.py`, `test_cli_ids.py`,
  `test_cli_merge.py`, `test_cli_model.py`, `test_cli_options.py`,
  `test_cli_parser.py`, `test_cli_project.py`,
  `test_cli_project_creators.py`, `test_cli_verbose.py`,
  `test_cli_wheel.py`.
- `tests/core/` (32 files after the further split pass: `core/`,
  `ids.py`, `loom.py`, generator orchestration).
- Single-file areas stayed flat at `tests/` root
  (`tests/enrich_readme_test.py`-style singletons, `tests/ids_shared.py`
  for shared registry-test helpers, root `tests/conftest.py` for
  genuinely cross-cutting fixtures).

No `__init__.py` needed in any new folder --
`--import-mode=importlib` (`pyproject.toml:240`) allows same-named
test files across directories.

### Further split passes (COMPLETE 2026-08-18)

All oversized test suites across `tests/core/`, `tests/extract/`, and
`tests/assemble/` were split down to modular suites:
- `tests/core/test_generator_project.py` $\rightarrow$ `test_generator_project.py`
  (212 lines), `test_generator_project_creators.py` (395 lines).
- `tests/core/test_loom_registry.py` $\rightarrow$ `test_loom_registry.py`
  (238 lines), `test_loom_creators.py` (195 lines).
- `tests/core/test_loom.py` $\rightarrow$ `test_loom.py` (185 lines),
  `test_loom_hyperparameters.py` (195 lines).
- `tests/core/test_fragments_misc.py` $\rightarrow$ `test_fragments_misc.py`
  (234 lines), `test_fragments_models_datasets.py` (190 lines).
- `tests/assemble/test_assemble_ai.py` $\rightarrow$ `test_assemble_ai.py`
  (256 lines), `test_assemble_ai_metadata.py` (168 lines).
- `tests/assemble/test_embed_cli.py` $\rightarrow$ `test_embed_cli.py`
  (249 lines), `test_embed_overrides.py` (181 lines).
- `tests/extract/test_hatch_hook_hook_basic.py` $\rightarrow$ `test_hatch_hook_hook_basic.py`
  (252 lines), `test_hatch_hook_creators.py` (180 lines).
- `tests/extract/test_setuptools_cfg.py` $\rightarrow$ `test_setuptools_cfg.py`
  (274 lines), `test_setuptools_cfg_config.py` (157 lines).
- `tests/extract/test_setuptools_py.py` $\rightarrow$ `test_setuptools_py.py`
  (166 lines), `test_setuptools_integration.py` (258 lines).

Verified: `pytest --collect-only` count unchanged (1960), full-suite
pass/skip count unchanged (1936/24), coverage at 91.98%,
`ruff check`/`ruff format --check`/`mypy`/`flake8` clean across all of
`tests/`.

All files in `tests/` outside `tests/extract/huggingface/` fixture catalogs
are $\le 415$ lines.

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

The internal modules across the codebase now cleanly follow this rule:
- `extract/`: `_croissant.py`, `_croissant_keys.py`, `_extract_utils.py`,
  `_fasttext.py`, `_file_headers.py`, `_gguf.py`, `_hdf5.py`,
  `_huggingface.py`, `_huggingface_fetch.py`, `_huggingface_fields.py`,
  `_keras.py`, `_license.py`, `_license_detect.py`, `_numpy.py`, `_onnx.py`,
  `_poetry.py`, `_pyproject.py`, `_pytorch.py`, `_pytorch_pt2.py`,
  `_safetensors.py`, `_sdist.py`, `_setuptools.py`, `_setuptools_cfg.py`,
  `_setuptools_py.py`.
- `assemble/spdx3/`: `_ai_package.py`, `_document_deployed.py`,
  `_document_files.py`, `_document_model.py`, `_fragments_unify.py`,
  `_provenance_encoders.py`.
- `core/`: `_config_legacy.py`, `_config_parse.py`, `_config_types.py`,
  `_models_wheel.py`.
- Root package: `_embed_wheel.py`, `_ids_types.py`, `_loom_caller.py`,
  `_loom_active_run.py`.

## Phase 3: coverage backfill and floor raise (COMPLETE, then exceeded)

`fail_under` was raised 90 -> 95 -> **97** (`pyproject.toml:368`) as
PR #164 and later #176/#177 backfilled coverage across `extract/`,
`assemble/`, and `cli/`. Re-measured 2026-08-21: **99.89% total, 2270
passed / 24 skipped.** Worst-covered files are now `assemble/spdx3/document.py`
(98%) and `extract/_setuptools.py` (98%) -- everything else is 99-100%.
Nothing left worth a dedicated backfill pass.

## Test performance and caching

Re-measured 2026-08-21: 2270 passed / 24 skipped in ~35s using
`pytest -n auto --dist=loadscope --cov=pitloom` -- `pytest-xdist` is
in use. No known test-order-dependency flakiness surfaced from parallelization.
Runtime has stayed roughly flat since the 2119-test measurement (also
~35s), still comfortably fast enough that per-directory CI matrix
legs aren't warranted yet (see below).

- The Phase 2 folder split is itself a speed win for iteration
  regardless of parallelism: `pytest tests/extract/` collects ~36
  small files instead of one 9,357-line file, so working on one area
  no longer pays collection/parse cost for unrelated areas.
  `pytest --lf`/`--ff` and the default `.pytest_cache` give this for
  free once files are small enough that "the file being edited" and
  "the tests worth rerunning" line up 1:1.
- If suite time grows further, per-directory CI matrix legs
  (`-n auto --dist loadgroup` per folder) are the next lever -- not
  needed at ~9s total.

## Next step

Nothing from this doc's original scope (CLI split, test modularization,
coverage floor) remains open -- Phase 3's stretch target was reached
and exceeded. What's open now lives in the sibling doc instead: see
[complexity-and-file-size-roadmap.md](complexity-and-file-size-roadmap.md)
for the file-size drift that's resumed since Phase 2 completed (this
doc's Phase 2 status above still accurately describes the *split
work itself* as complete -- it's organic regrowth since, not a
reopening of Phase 2).

### Pickup prompt for a new session

```text
Read working-docs/design/cli-test-coverage-roadmap.md in full. Phases
1-3 (the __main__.py -> cli/ split, test-suite modularization incl.
the further split pass, and coverage floor raise to 90, later 95) are
all COMPLETE, and the 95% stretch target has been reached and
exceeded (99.89% as of 2026-08-21) -- do not redo any of this.

This doc's own scope is closed. If you're here for file-size or
coverage follow-up, check complexity-and-file-size-roadmap.md first --
that's where the currently-open item (file-size drift) is tracked.

Pre-1.0, so no backward-compat shims needed for any renames this
touches. Run the full test suite and the project's lint/type-check
commands (AGENTS.md "Linting and formatting") before considering it
done.
```
