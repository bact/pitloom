---
Created: 2026-08-14
Last-Modified: 2026-08-14
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# CLI split, test-suite modularization, and coverage roadmap

**Status:** sequencing agreed, not yet executed. Supersedes and
absorbs the earlier `test-suite-modularization.md` sketch (deleted --
its content lives here now, extended with the `__main__.py` split it
was waiting on and the coverage work tied to both).

## Three tech-debt items, one sequencing problem

1. **Test coverage** is at 87.32% (Codecov); we want it maintained
   around 95%, with a 90% hard floor (OpenSSF baseline). Current
   `pyproject.toml` `fail_under` is 88.
2. **Test suite files are too big.** `tests/` is 32k+ lines across
   ~48 files, concentrated in a handful of monoliths. Splitting them
   makes it possible to selectively run just the tests relevant to
   one area, and keeps each file within a reasonable AI-agent context
   window.
3. **`src/pitloom/__main__.py` is too big** (1,320 lines) and its own
   coverage (71%) is well below everything else in the tree.
   `__main__`-shaped files aren't meant to carry this much logic.

These aren't independent: item 3 changes the module boundaries that
item 2's test-file boundaries should track, and both change what
"backfill coverage" even means for item 1. Order matters.

## Current state (measured 2026-08-14)

- **Coverage baseline mismatch**: local run (Python 3.10.18) shows
  89.51% total; Codecov shows 87.32%. Cause: CI
  (`.github/workflows/test.yml`) only runs `--cov` on the Python 3.14
  matrix leg, not 3.10. `__main__.py` branches on
  `sys.version_info >= (3, 11)` (`tomllib` vs `tomli`), and other
  version-gated paths elsewhere likely diverge similarly between the
  two interpreters. Treat Codecov's 87.32% as ground truth (it's the
  only number CI actually produces); a 3.10-only local run
  under-represents the gap.
- **Worst-covered files** (local 3.10 run; will differ somewhat on
  3.14, re-measure before acting): `__main__.py` 71% (491 stmts /
  115 miss -- worst by absolute miss count), `extract/sdist.py` 69%,
  `extract/wheel.py` 71%, `export/spdx3_json.py` 75%,
  `extract/pyproject.py` 77%, `extract/_hdf5.py` 83%,
  `extract/scanner.py` 84%, `assemble/__init__.py` 85%.
- **`__main__.py` shape** (1,320 lines): argparse construction
  (`_build_parent_parser`, `_build_parser`, `_add_ids_subparser`,
  3 custom `argparse.Action` classes) ~450 lines; creation-metadata /
  option resolution (`_Resolved*` dataclasses, `_resolve_creators`,
  `_resolve_tools`, `_resolve_creation_metadata`,
  `_resolve_generate_mode_settings`, `_resolve_output_path` and
  siblings) ~200 lines; verbose-print helpers (`_print_verbose`,
  `_build_creation_option_rows`) ~100 lines; the 7 mode handlers
  (`_run_generate_mode` ... `_run_merge_mode`) ~350 lines; the `ids`
  subcommand (`_run_ids_generate`, `_run_ids_import`, `_run_ids_cli`,
  `_load_or_create_registry`) ~200 lines.
- **Largest test files today**: `test_extract_huggingface.py` 9,357
  lines, `test_generator.py` 3,050 lines, `test_main_cli.py` 1,720
  lines, `test_hatch_hook.py` 1,445 lines, `test_fragments.py` 1,063
  lines. `test_generator.py` in particular spans project/wheel/model/
  env generation, content-type detection, and file-header provenance
  all in one file.
- **`tests/` layout today**: flat, ~48 files, no subfolders except
  `tests/fixtures/`. `test_extract_*` alone is already 23 files.

## Recommended order: cli split -> test modularization -> coverage

1. **Split `__main__.py` into `pitloom/cli/`** first. Pure structural
   refactor, no behaviour change.
2. **Modularize the test suite** once the new source boundaries exist,
   so test-file boundaries can mirror them.
3. **Backfill coverage and raise the floor** last, once code and
   tests are both in their final shape.

Rationale: writing new tests against `__main__.py` now (for item 1)
means rewriting them again once the file splits (item 3 above) --
wasted work. Splitting tests before splitting source means guessing
at boundaries that don't exist yet. Source split, then test split,
then coverage backfill avoids doing anything twice. This was already
the direction the original `test-suite-modularization.md` sketch
pointed at ("revisit alongside or after the `__main__.py` split...
not before"); this doc just makes it the actual plan.

**Pre-1.0**: no backward-compatibility constraint on any of this
(`AGENTS.md`: "private alpha, one developer, no backward compat
needed yet"). Free to rename, move, and delete without deprecated
re-export shims, aliasing, or migration warnings across all three
phases -- worth restating here because a refactor this size otherwise
invites reflexively adding compat shims out of habit.

## Phase 1: split `__main__.py` into `pitloom/cli/`

Target layout (matches the flat-multi-module-package convention
`pitloom/core/`, `pitloom/assemble/`, `pitloom/extract/` already use):

- `cli/parser.py` -- `_build_parent_parser`, `_build_parser`,
  `_add_ids_subparser`, the 3 custom `argparse.Action` classes.
- `cli/options.py` -- the `_Resolved*` dataclasses and
  `_resolve_creators` / `_resolve_tools` / `_resolve_creation_metadata`
  / `_resolve_generate_mode_settings` / `_resolve_output_path` and
  siblings.
- `cli/verbose.py` -- `_print_verbose`, `_build_creation_option_rows`.
- `cli/modes/` -- one file per mode handler
  (`generate.py`, `project.py`, `wheel.py`, `model.py`, `enrich.py`,
  `env.py`, `merge.py`), each holding its `_run_<verb>_mode` function.
  One file per mode keeps each under the size limit on its own and
  gives Phase 2's test split an exact 1:1 file to mirror.
- `cli/ids.py` -- `_run_ids_generate`, `_run_ids_import`,
  `_run_ids_cli`, `_load_or_create_registry`,
  `_default_ids_generate_paths`.
- `__main__.py` shrinks to `_configure_logging()`, `main()`'s dispatch
  table, and the `if __name__ == "__main__"` guard.

**Test-patch risk, must move in lockstep, not as a follow-up**:
`tests/test_main_cli.py` does
`monkeypatch.setattr(__main__, "generate_project_sbom", ...)` (and
`generate`, `generate_model_sbom`, `enrich_model`, etc.) throughout --
patching names in the `pitloom.__main__` module namespace. Moving mode
handlers into `pitloom/cli/modes/*.py` moves where those names are
imported, so every such patch site needs its target module updated in
the same change that moves the code, or the test suite silently stops
testing what it claims to.

## Phase 2: test-suite modularization

### Folder-vs-flat decision

**Group by folder once an area reaches 3+ related test files,
otherwise stay flat.** Same threshold `AGENTS.md` already codifies
for `working-docs/` -- reuse an agreed rule rather than invent a
second one. Now recorded as a standing rule in `AGENTS.md`'s Testing
section, not just here.

Target folders:

- `tests/extract/` (23+ files today, mirrors `src/pitloom/extract/`)
- `tests/assemble/` (~9 files today: `test_assemble_ai.py`,
  `test_fragments.py`, `test_creation_info.py`,
  `test_spdx3_dataset.py`, `test_spdx3_compliance.py`,
  `test_deps_enrichment.py`, `test_provenance*.py`,
  `test_generator.py` split further -- see below)
- `tests/cli/` (new, mirrors the new `src/pitloom/cli/` from Phase 1)
- `tests/core/` (candidate: `test_config.py`, `test_core_project.py`,
  `test_models.py`, `test_metadata.py` -- confirm each maps to
  `core/` before moving)
- Areas with 1-2 files stay flat at `tests/` root (e.g.
  `test_enrich_readme.py`, `test_ids.py`, `test_loom.py`).

No `__init__.py` needed in the new folders --
`--import-mode=importlib` (`pyproject.toml:240`) already allows
same-named test files across directories.

### File-by-file split targets

- `tests/cli/`: `test_cli_parser.py`, `test_cli_options.py`,
  `test_cli_verbose.py`, `test_cli_generate.py`, `test_cli_project.py`,
  `test_cli_wheel.py`, `test_cli_model.py`, `test_cli_enrich.py`,
  `test_cli_env.py`, `test_cli_merge.py`, `test_cli_ids.py` -- 1:1
  with the Phase 1 module list above, each within the 400-500 line
  soft limit.
- `test_extract_huggingface.py` (9,357 lines) -- split by metadata
  category rather than staying one flat file: base-model lineage,
  tags, datasets, licensing, and whatever other categories the file's
  current section structure already implies.
- `test_generator.py` (3,050 lines) -- split by generation target:
  project / wheel / model / env / content-type detection /
  file-header provenance (it currently spans all of these in one
  file).
- `test_hatch_hook.py` (1,445 lines) and `test_fragments.py` (1,063
  lines) -- split by the sub-area each already organizes its test
  classes/functions around; exact boundaries to be determined when
  the file is opened for the split (not guessed here).

Mechanical relocation only -- no test-logic changes. Shared fixtures
move to `conftest.py` (cross-cutting) or a new per-folder
`conftest.py` (area-scoped).

### Naming pass rides along with Phases 1-2

Since pre-1.0 removes the backward-compat tax, the cheapest time to
fix a name is the same commit that's already moving the file.

- **Resolve `test_extract_project.py` vs `test_core_project.py`**
  during the `tests/core/` vs `tests/extract/` split -- same basename
  tail, different source modules, easy to grab the wrong one by grep.
  Rename one to make the source package unambiguous from the filename
  alone; check what each file actually covers before renaming.
- **Align the `ids` subcommand's names** to the `_run_<verb>_mode` /
  `_add_<verb>_subparser` pattern the other six verbs already use,
  while it's being extracted into `cli/ids.py` anyway (currently
  `_run_ids_cli`/`_run_ids_generate`/`_run_ids_import` have no
  `_mode` suffix, and `_add_ids_subparser` is the only
  `_add_*_subparser`).
- Land naming fixes as part of the commit that already touches the
  file -- not a repo-wide find-and-rename pass, which would bloat the
  diff and make review harder without adding safety.

### Underscore-prefix audit for `extract/` (and beyond)

`AGENTS.md`'s Naming section now states the rule: a module gets a
leading underscore when nothing outside its own package directory
imports it (an internal adapter/parser/helper); no prefix when
something outside the package imports it (a stable entry point), with
an explicit-`__all__`/public-API-docstring facade as a second signal
that overrides a zero-internal-importer reading.

Checked `extract/`'s current names against actual import statements
(not domain guesses) while writing this doc:

- **Confirmed correctly public** (imported from outside `extract/`):
  `wheel.py` (`assemble/__init__.py`), `hatchling.py`
  (`plugins/hatch.py`), `env.py`, `scanner.py`, `binary.py`,
  `ai_model.py` (`assemble/__init__.py`), `project.py` (`__main__.py`
  and `assemble/__init__.py`).
- **Confirmed correctly underscored** (only 1-2 internal call sites,
  no `__all__`): `_gguf.py`, `_hdf5.py`, `_pytorch.py`,
  `_pytorch_pt2.py`, `_onnx.py`, `_keras.py`, `_numpy.py`,
  `_safetensors.py`, `_fasttext.py`, `_croissant.py`,
  `_croissant_keys.py`. These are per-format parsers only their
  aggregator (`ai_model.py` or `dataset.py`) imports -- confirms the
  split tracks "internal adapter vs. stable entry point", not an
  AI-vs-Python-packaging domain split as it first appeared.
- **Likely outliers -- underscore missing** (only imported from
  inside `extract/`, no `__all__`/public-API marker found):
  `pyproject.py` (only `hatchling.py` and `project.py` import it),
  `sdist.py` (only `project.py` imports it), `poetry.py` (only
  `pyproject.py` imports it), `setuptools.py` (only `project.py`
  imports it). These four look like an internal parsing chain
  `project.py` dispatches through (source archive -> build-backend
  config -> `pyproject.toml`/`setup.cfg` section), mirroring
  `ai_model.py`'s dispatch to the underscored format parsers -- if
  so, all four should probably become `_pyproject.py`, `_sdist.py`,
  `_poetry.py`, `_setuptools.py`.
- **Deliberate exception, not an outlier**: `dataset.py` has zero
  internal importers but carries an explicit `__all__` and a
  "Dataset metadata extraction public API" docstring with a usage
  example for external callers -- correctly unprefixed despite
  looking like an outlier by import count alone. This is why the
  `AGENTS.md` rule needs the second signal, not import count in
  isolation.

**Not resolved in this doc** -- the four likely outliers need the
same check repeated one more time right before renaming (confirm no
`__all__`/docstring-marker override applies, confirm nothing external
imports them either), and the same check needs to run once across
`core/`, `assemble/`, `export/`, `enrich/` too (this pass only
covered `extract/`). Do this as part of Phase 2 when those files are
already open for the test-folder move.

## Phase 3: coverage backfill and floor raise

Priority order (by current miss count / percentage, re-measure after
Phases 1-2 land since the `cli/` split changes what "cover
`__main__.py`" even means):

1. `cli/*` -- the post-split pieces of the old 71%-covered
   `__main__.py`.
2. `extract/sdist.py` (69%), `extract/wheel.py` (71%).
3. `export/spdx3_json.py` (75%).
4. `extract/pyproject.py` (77%).
5. `extract/_hdf5.py` (83%), `extract/scanner.py` (84%).
6. `assemble/__init__.py` (85%).

Sequencing for the floor itself:

- Re-measure on Python 3.14 (or read Codecov's number) before
  treating any baseline as current -- the 3.10-vs-3.14 gap found
  while writing this doc means a 3.10-only local run is optimistic.
- Raise `pyproject.toml`'s `fail_under` from 88 to 90 only once
  comfortably past that floor on the CI-measured (3.14) number --
  raising it before the backfill would just start failing CI on
  unrelated PRs.
- Keep pushing toward the 95% target after the floor is safely raised;
  95% is a target to aim for, not a second hard gate to add to CI
  immediately.

## Test performance and caching (forward-looking, not a change now)

Current baseline: 1,856 passed / 24 skipped in 9.77s locally, single
process, no `pytest-xdist` in `pyproject.toml`'s `test` extra (only
`pytest`, `pytest-cov`, `stav`). Not a bottleneck today.

- The Phase 2 folder split is itself a speed win for iteration
  regardless of parallelism: `pytest tests/extract/` collects ~20
  small files instead of one 9,357-line file, so working on one area
  no longer pays collection/parse cost for unrelated areas.
  `pytest --lf`/`--ff` and the default `.pytest_cache` already give
  this for free once files are small enough that "the file being
  edited" and "the tests worth rerunning" line up 1:1.
- If suite time later becomes a real cost (CI minutes, local iteration
  drag), `pytest-xdist` (`-n auto`) is the standard next step -- a
  trigger-based follow-up, not a preemptive add. The folder split
  doesn't block it: folders shard cleanly by `-n auto --dist
  loadgroup` or per-directory CI matrix legs, and `pytest-cov` is
  xdist-compatible out of the box (each worker's coverage data is
  combined automatically).
- Before ever adopting xdist, check for hidden test-order dependencies
  (shared mutable fixtures, global registry/singleton state such as
  `pitloom.ids.IdRegistry` module-level defaults) -- xdist runs tests
  in unpredictable order across workers and will surface any such
  coupling as flaky failures.

## Next step

Execute Phase 1 (the `pitloom/cli/` split) in a dedicated session,
including the monkeypatch-target migration in `test_main_cli.py` in
the same change. Phase 2 and Phase 3 follow once Phase 1 has landed
and the new module boundaries are settled.

### Pickup prompt for a new session

A fresh agent with no memory of this doc's discussion can start
Phase 1 with:

```text
Read working-docs/design/cli-test-coverage-roadmap.md in full, then
execute Phase 1: split src/pitloom/__main__.py into a new
src/pitloom/cli/ package per the "Phase 1: split __main__.py into
pitloom/cli/" section's target layout (cli/parser.py, cli/options.py,
cli/verbose.py, cli/modes/<verb>.py per mode, cli/ids.py).
__main__.py should shrink to _configure_logging(), main()'s dispatch
table, and the `if __name__ == "__main__"` guard.

Pure structural refactor -- no behaviour change. Pre-1.0, so no
backward-compat shims or re-exports are needed (see the doc's
pre-1.0 note).

Critical: tests/test_main_cli.py monkeypatches names in the
pitloom.__main__ namespace (e.g. `monkeypatch.setattr(__main__,
"generate_project_sbom", ...)`). Update every such patch target to
the new cli/ module it moves to, in the same change -- do not leave
this for a follow-up, or the tests will silently stop testing what
they claim to (see the doc's "Test-patch risk" callout).

Do not start Phase 2 (test-suite modularization) or Phase 3
(coverage backfill) in this session -- they depend on Phase 1's
module boundaries being settled and reviewed first. Run the full
test suite and the project's lint/type-check commands (AGENTS.md
"Linting and formatting") before considering the split done.
```
