---
Created: 2026-08-13
Last-Modified: 2026-08-13
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Note: the test suite could use modular restructuring

**Status:** idea only, not scheduled. Nothing to implement yet.

## Observation

`tests/` is 32k+ lines across ~50 files, but size is concentrated in a
handful of monoliths:

- `test_extract_huggingface.py` -- 9,357 lines
- `test_generator.py` -- 3,050 lines
- `test_main_cli.py` -- 1,720 lines
- `test_hatch_hook.py` -- 1,445 lines
- `test_fragments.py` -- 1,063 lines

A single file this large covers many unrelated concerns at once (e.g.
`test_generator.py` spans project/wheel/model/env generation, content-type
detection, and file-header provenance all together), which makes it hard
to run just the tests relevant to one area of the code while iterating,
and hard to find the right place to add a new test.

## Why now

Came up while working the two largest open code-debt items --
`src/pitloom/__main__.py` (1,320 lines, arg-parsing mixed with mode
orchestration) and the `assemble/__init__.py`/`assemble/spdx3/document.py`
coupling (high fan-in hub, 12 files import through it). If/when those get
restructured into smaller, more focused modules, the tests that cover
them (`test_main_cli.py`, `test_generator.py`, `test_fragments.py`, ...)
would ideally split along the same lines, so test-file boundaries keep
tracking source-module boundaries.

## Possible direction (not decided)

Split by area rather than by one file per source module necessarily --
e.g. `test_main_cli_generate.py` / `test_main_cli_wheel.py` /
`test_main_cli_model.py` instead of one `test_main_cli.py`, so
`pytest tests/test_main_cli_wheel.py` selectively runs just that area.
`test_extract_huggingface.py`'s 9k+ lines in particular look like they'd
benefit from splitting by metadata category (base-model lineage, tags,
datasets, licensing, ...) rather than one flat file.

## Next step

Revisit alongside (or after) the `__main__.py` split and the
`assemble`/`document.py` decoupling work -- not before, since the right
test-file boundaries depend on what the new module boundaries end up
being.
