# SPDX-FileCopyrightText: 2026 Arthit Suriyawongkul
# SPDX-FileType: DOCUMENTATION
# SPDX-License-Identifier: CC0-1.0
# Created: 2026-08-17
# Last-Modified: 2026-08-17

# Complexity and file-size roadmap

See also: [cli-test-coverage-roadmap.md](cli-test-coverage-roadmap.md) for
the sibling test-suite health effort this doc's structure follows.

**Status:** open. This is the deferred follow-up from the source-file-split
+ complexity-tooling change (4 hard-cap files split, McCabe/cognitive
complexity linting activated at ratchet ceilings). Not yet scheduled.

## Why this exists

Activating McCabe (ruff `C90`) and cognitive-complexity (flake8
`flake8-cognitive-complexity`) linting surfaced real, pre-existing
violations against AGENTS.md's stated targets (McCabe≤10, Cognitive≤15).
Rather than block the tooling activation on refactoring all of them, both
were enabled at a **ratchet ceiling**: high enough that today's worst
offender still passes, low enough that no new violations can be added
without deliberately raising the ceiling again. This doc tracks what has
to shrink before the ceilings can drop toward the real targets, so a
future session can pick up decomposition work without re-deriving the
list.

## McCabe violations (ratchet: 35, target: 10)

Measured via `ruff check --select C90` with `max-complexity = 10`
(2026-08-17, after the 4-file split). 26 functions exceed the target.
Two of `extract/_setuptools.py`'s (`read_setup_py`, worst here at 32) are
also branches-limit violators with inline `# pylint: disable` suppressions
-- see the suppressions added alongside this doc.

Classification:
- **Flat field-extraction** (low risk -- an obvious loop/helper-function
  decomposition, each branch just picks a field to populate): `read_gguf`,
  `_build_ai_package`, `read_wheel`, `_build_dataset_package`,
  `read_croissant`, `read_onnx`, `_parse_model_config`,
  `_build_extra_data`, `metadata_from_hatchling`, `_parse_pkg_info`,
  `_read_pt2_extra_files`, `_read_pt2_zip`, `add_ai_models`,
  `extract_poetry_metadata`, `read_pyproject`, `_resolve_cfg_version`,
  `_extract_card_description`, `scan_project_for_ai_models`,
  `parse_file_header`, `build_model`, `_emit_file_header_metadata`.
- **Genuine nested control flow** (needs careful extraction, not just
  hoisting): `read_setup_py`, `_read_pitloom_config_from_cfg` (both in
  `extract/_setuptools.py` -- config-format parsing with real branching on
  format variants), `read_setup_cfg`, `build_deployed`, `loom.py`'s
  `finalize` (state-machine-like run-completion logic).

| Function | File:line | McCabe | Class |
| :--- | :--- | ---: | :--- |
| `_read_pitloom_config_from_cfg` | `extract/_setuptools.py:662` | 32 | nested |
| `read_setup_py` | `extract/_setuptools.py:314` | 21 | nested |
| `read_gguf` | `extract/_gguf.py:82` | 21 | flat |
| `_build_ai_package` | `assemble/spdx3/ai.py:289` | 21 | flat |
| `read_wheel` | `extract/wheel.py:18` | 20 | flat |
| `_build_extra_data` | `extract/_huggingface.py:709`\* | 16 | flat |
| `_build_dataset_package` | `assemble/spdx3/dataset.py:54` | 16 | flat |
| `read_croissant` | `extract/_croissant.py:133` | 15 | flat |
| `parse_file_header` | `extract/_file_headers.py:114` | 15 | flat |
| `finalize` | `loom.py:446`\* | 15 | nested |
| `build_deployed` | `assemble/spdx3/document.py:912`\* | 15 | nested |
| `_read_pt2_zip` | `extract/_pytorch_pt2.py:236` | 15 | flat |
| `read_onnx` | `extract/_onnx.py:47` | 14 | flat |
| `read_setup_cfg` | `extract/_setuptools.py:210` | 13 | nested |
| `add_ai_models` | `assemble/spdx3/ai.py:429` | 13 | flat |
| `_parse_model_config` | `extract/_hdf5.py:121` | 13 | flat |
| `metadata_from_hatchling` | `extract/hatchling.py:95` | 12 | flat |
| `_read_pt2_extra_files` | `extract/_pytorch_pt2.py:86` | 12 | flat |
| `scan_project_for_ai_models` | `extract/scanner.py:32` | 11 | flat |
| `read_pyproject` | `extract/_pyproject.py:38` | 11 | flat |
| `extract_poetry_metadata` | `extract/_poetry.py:106` | 11 | flat |
| `build_model` | `assemble/spdx3/document.py:769`\* | 11 | flat |
| `_resolve_cfg_version` | `extract/_setuptools.py:468` | 11 | flat |
| `_parse_pkg_info` | `extract/_sdist.py:27` | 11 | flat |
| `_extract_card_description` | `extract/_huggingface.py:411`\* | 11 | flat |
| `_emit_file_header_metadata` | `assemble/spdx3/document.py:172`\* | 11 | flat |

\* Line numbers are pre-split; after the `document.py`, `_huggingface.py`,
and `loom.py` splits landed, these live in `_document_model.py`,
`_document_deployed.py`, `_document_files.py`, `_huggingface_fields.py`
/ `_huggingface_fetch.py`, and `_loom_active_run.py` (`finalize`, now a
method of `_ActiveRun`) respectively -- re-measure with `ruff check
--select C90` against current paths before starting decomposition.

Suggested order: tackle the "flat" group first (mechanical, low risk,
each one a short PR), leaving `read_setup_py` /
`_read_pitloom_config_from_cfg` / `finalize` / `build_deployed` /
`read_setup_cfg` for dedicated sessions since they need real design
thought about how to split branching logic without changing behaviour.

## Cognitive complexity (ratchet: 60, target: 15)

Measured via `flake8 --select=CCR001` with `max-cognitive-complexity=1`
(2026-08-17). Worst offenders overlap heavily with the McCabe list above
(same underlying branchy functions) plus a few additional ones the
cyclomatic count under-weights:

`extract/_setuptools.py:662` (57), `extract/wheel.py:18` (40),
`extract/_setuptools.py:314` (40), `loom.py:446`\* (38),
`assemble/spdx3/ai.py:429` (38), `extract/_gguf.py:82` (37),
`assemble/spdx3/document.py:912`\* (36), `extract/_file_headers.py:114`
(30), `extract/_hdf5.py:121` (27), `extract/_huggingface.py:411`\* (26),
`extract/scanner.py:32` (25), `extract/_pytorch_pt2.py:236` (24),
`assemble/spdx3/ai.py:289` (24), `export/spdx3_json.py:192` (23),
`ids.py:492` (22), `extract/_setuptools.py:468` (22),
`extract/_sdist.py:77` (22), `extract/_pyproject.py:38` (22),
`assemble/spdx3/deps.py:519`\* (22), `assemble/spdx3/deps.py:444`\* (22).

\* Same caveat as above -- re-measure against post-split paths
(`deps_pypi.py`/`deps_license.py`/`deps_supplier.py`,
`_document_deployed.py`, `_huggingface_fetch.py`) before use.

No separate remediation plan for cognitive complexity beyond the McCabe
list above -- the same decomposition work drops both metrics together,
since both measure branching/nesting in the same functions. Track both
ceilings dropping together as the McCabe backlog shrinks.

## Remaining files over the 500-line soft limit (under the 800 hard cap)

Not touched by the 4-file split. None require action yet -- soft limit
only, no CI gate -- but flagged here so growth is deliberate, not
accidental:

| File | Lines | Note |
| :--- | ---: | :--- |
| `extract/_setuptools.py` | 786 | Will shrink once `read_setup_py` / `_read_pitloom_config_from_cfg` are decomposed (see above). |
| `core/config.py` | 758 | |
| `assemble/spdx3/fragments.py` | 758 | |
| `assemble/__init__.py` | 687 | |
| `embed.py` | 662 | |
| `assemble/spdx3/provenance.py` | 634 | |
| `ids.py` | 600 | |
| `assemble/spdx3/ai.py` | 593 | |

## Ratchet ceiling ownership

Both ceilings below are documented as "interim" in `pyproject.toml` /
`.flake8` with inline comments pointing back here. As functions in the
McCabe list get decomposed, whoever does that work should also tighten
the corresponding ceiling in the same PR (don't let the ceiling sit at
its ship-day value once the violations it was protecting against are
gone):

- `[tool.ruff.lint.mccabe] max-complexity`: 35 -> target 10.
- `.flake8 max-cognitive-complexity`: 60 -> target 15.
- `[tool.pylint.design]`: `max-args` 6 -> target 5, `max-locals` 18 ->
  target 15. `max-branches` (20) and `max-statements` (80) are
  pylint-specific knobs not stated in AGENTS.md; tighten opportunistically
  as violations clear, no hard target set.

## Pickup prompt

"Continue the complexity-and-file-size roadmap: pick the next 'flat'
McCabe violation from the table, decompose it into a loop or helper
functions without changing behaviour, add a regression test if the
existing suite doesn't already cover every branch, then tighten
`max-complexity` in `pyproject.toml` if that was the worst remaining
offender."
