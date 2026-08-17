# SPDX-FileCopyrightText: 2026 Arthit Suriyawongkul
# SPDX-FileType: DOCUMENTATION
# SPDX-License-Identifier: CC0-1.0
# Created: 2026-08-17
# Last-Modified: 2026-08-18

# Complexity and file-size roadmap

See also: [cli-test-coverage-roadmap.md](cli-test-coverage-roadmap.md) for
the sibling test-suite health effort this doc's structure follows.

**Status:** file-size refactoring complete across all `src/` (all files
$\le 417$ lines) and all `tests/` (all files $\le 415$ lines outside
Hugging Face mock fixture catalogs). Function-level McCabe and cognitive
complexity decomposition tracked below for future ratchet tightening.

## Why this exists

Activating McCabe (ruff `C90`) and cognitive-complexity (flake8
`flake8-cognitive-complexity`) linting surfaced real, pre-existing
violations against AGENTS.md's stated targets (McCabe$\le$10, Cognitive$\le$15).
Rather than block the tooling activation on refactoring all of them, both
were enabled at a **ratchet ceiling**: high enough that today's worst
offender still passes, low enough that no new violations can be added
without deliberately raising the ceiling again. This doc tracks what has
to shrink before the ceilings can drop toward the real targets, so a
future session can pick up decomposition work without re-deriving the
list.

## McCabe violations (ratchet: 35, target: 10)

Measured via `ruff check --select C90` with `max-complexity = 10`
(2026-08-18, after the full file-split refactor). 26 functions exceed the target.
Two of setuptools extraction (`read_setup_py` at 21 and
`_read_pitloom_config_from_cfg` at 32) are also branches-limit violators with
inline `# pylint: disable` suppressions.

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
  hoisting): `read_setup_py` (in `extract/_setuptools_py.py`),
  `_read_pitloom_config_from_cfg` and `read_setup_cfg` (in
  `extract/_setuptools_cfg.py`), `build_deployed` (in
  `assemble/spdx3/_document_deployed.py`), and `finalize` (in
  `_loom_active_run.py`, state-machine run-completion logic).

| Function | File:line | McCabe | Class |
| :--- | :--- | ---: | :--- |
| `_read_pitloom_config_from_cfg` | `src/pitloom/extract/_setuptools_cfg.py:263` | 32 | nested |
| `read_setup_py` | `src/pitloom/extract/_setuptools_py.py:74` | 21 | nested |
| `read_gguf` | `src/pitloom/extract/_gguf.py:82` | 21 | flat |
| `_build_ai_package` | `src/pitloom/assemble/spdx3/_ai_package.py:233` | 21 | flat |
| `read_wheel` | `src/pitloom/extract/wheel.py:18` | 20 | flat |
| `_build_extra_data` | `src/pitloom/extract/_huggingface_fields.py:306` | 16 | flat |
| `_build_dataset_package` | `src/pitloom/assemble/spdx3/dataset.py:54` | 16 | flat |
| `read_croissant` | `src/pitloom/extract/_croissant.py:133` | 15 | flat |
| `parse_file_header` | `src/pitloom/extract/_file_headers.py:114` | 15 | flat |
| `finalize` | `src/pitloom/_loom_active_run.py:243` | 15 | nested |
| `build_deployed` | `src/pitloom/assemble/spdx3/_document_deployed.py:39` | 15 | nested |
| `_read_pt2_zip` | `src/pitloom/extract/_pytorch_pt2.py:236` | 15 | flat |
| `read_onnx` | `src/pitloom/extract/_onnx.py:47` | 14 | flat |
| `read_setup_cfg` | `src/pitloom/extract/_setuptools_cfg.py:173` | 13 | nested |
| `add_ai_models` | `src/pitloom/assemble/spdx3/ai.py:56` | 13 | flat |
| `_parse_model_config` | `src/pitloom/extract/_hdf5.py:121` | 13 | flat |
| `metadata_from_hatchling` | `src/pitloom/extract/hatchling.py:95` | 12 | flat |
| `_read_pt2_extra_files` | `src/pitloom/extract/_pytorch_pt2.py:86` | 12 | flat |
| `scan_project_for_ai_models` | `src/pitloom/extract/scanner.py:32` | 11 | flat |
| `read_pyproject` | `src/pitloom/extract/_pyproject.py:39` | 11 | flat |
| `extract_poetry_metadata` | `src/pitloom/extract/_poetry.py:106` | 11 | flat |
| `build_model` | `src/pitloom/assemble/spdx3/_document_model.py:220` | 11 | flat |
| `_resolve_cfg_version` | `src/pitloom/extract/_setuptools_cfg.py:40` | 11 | flat |
| `_parse_pkg_info` | `src/pitloom/extract/_sdist.py:27` | 11 | flat |
| `_extract_card_description` | `src/pitloom/extract/_huggingface_fetch.py:239` | 11 | flat |
| `_emit_file_header_metadata` | `src/pitloom/assemble/spdx3/_document_files.py:68` | 11 | flat |

Suggested order: tackle the "flat" group first (mechanical, low risk,
each one a short PR), leaving `read_setup_py` /
`_read_pitloom_config_from_cfg` / `finalize` / `build_deployed` /
`read_setup_cfg` for dedicated sessions since they need real design
thought about how to split branching logic without changing behaviour.

## Cognitive complexity (ratchet: 60, target: 15)

Measured via `flake8 --select=CCR001` with `max-cognitive-complexity=15`
(2026-08-18). Worst offenders overlap heavily with the McCabe list above
(same underlying branchy functions) plus a few additional ones the
cyclomatic count under-weights:

`extract/_setuptools_cfg.py:263` (57), `extract/wheel.py:18` (40),
`extract/_setuptools_py.py:74` (40), `_loom_active_run.py:243` (38),
`assemble/spdx3/ai.py:56` (38), `extract/_gguf.py:82` (37),
`assemble/spdx3/_document_deployed.py:39` (36),
`extract/_file_headers.py:114` (30), `extract/_hdf5.py:121` (27),
`extract/_huggingface_fetch.py:239` (26), `extract/scanner.py:32` (25),
`assemble/spdx3/_ai_package.py:233` (24),
`extract/_pytorch_pt2.py:236` (24), `export/spdx3_json.py:192` (23),
`_ids_types.py:93` (22), `extract/_sdist.py:78` (22),
`extract/_setuptools_cfg.py:40` (22), `assemble/spdx3/deps_supplier.py:95` (22),
`assemble/spdx3/deps_supplier.py:299` (22), `extract/_pyproject.py:39` (22).

No separate remediation plan for cognitive complexity beyond the McCabe
list above -- the same decomposition work drops both metrics together,
since both measure branching/nesting in the same functions. Track both
ceilings dropping together as the McCabe backlog shrinks.

## File-size limits status (COMPLETE)

All files across the entire codebase now strictly obey file-size limits:
- **`src/`**: Every file is $\le 417$ lines (well under the 500-line soft limit
  and 800-line hard cap).
- **`tests/`**: Every test file outside `tests/extract/huggingface/` shared
  mock fixture catalogs is $\le 415$ lines.

| Former oversized file | Split result | Max lines |
| :--- | :--- | ---: |
| `src/pitloom/ids.py` (601) | `_ids_types.py` (112), `ids.py` (317) | 317 |
| `src/pitloom/_loom_active_run.py` (633) | `_loom_caller.py` (128), `_loom_active_run.py` (395) | 395 |
| `src/pitloom/assemble/__init__.py` (688) | `_model_generator.py` (172), `_generators.py` (222), `__init__.py` (124) | 222 |
| `src/pitloom/core/config.py` (758) | `_config_types.py` (192), `_config_legacy.py` (88), `_config_parse.py` (377), `config.py` (59) | 377 |
| `src/pitloom/embed.py` (662) | `_embed_wheel.py` (356), `embed.py` (310) | 356 |
| `src/pitloom/assemble/spdx3/fragments.py` (758) | `_fragments_unify.py` (279), `fragments.py` (366) | 366 |
| `src/pitloom/assemble/spdx3/provenance.py` (634) | `_provenance_encoders.py` (275), `provenance.py` (374) | 374 |
| `src/pitloom/assemble/spdx3/ai.py` (593) | `_ai_package.py` (226), `ai.py` (363) | 363 |
| `src/pitloom/assemble/spdx3/deps.py` (519) | `deps_installed.py` (168), `deps_license.py` (391), `deps_pypi.py` (307), `deps_supplier.py` (264), `deps.py` (311) | 391 |
| `src/pitloom/extract/_setuptools.py` (786) | `_setuptools_cfg.py` (228), `_setuptools_py.py` (190), `_setuptools.py` (158) | 228 |
| `src/pitloom/extract/_license.py` (420) | `_license_detect.py` (178), `_license.py` (186) | 186 |
| `src/pitloom/core/models.py` (450) | `_models_wheel.py` (168), `models.py` (186) | 186 |

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
