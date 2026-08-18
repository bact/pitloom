# SPDX-FileCopyrightText: 2026 Arthit Suriyawongkul
# SPDX-FileType: DOCUMENTATION
# SPDX-License-Identifier: CC0-1.0
# Created: 2026-08-17
# Last-Modified: 2026-08-18

# Complexity and file-size roadmap

See also: [cli-test-coverage-roadmap.md](cli-test-coverage-roadmap.md) for
the sibling test-suite health effort this doc's structure follows.

**Status:**
- McCabe complexity ratchet tightened: `max-complexity = 15` (down from 35).
  All functions in `src/` are now $\le 15$ (verified, zero current violations).
- Cognitive complexity ratchet tightened: `max-cognitive-complexity = 20`
  (down from 60). All functions in `src/` are now $\le 20$ (verified, zero
  current violations).
- File-size refactoring is **not** complete -- it drifted back above the
  limits this doc previously reported clean; see "File-size limits status"
  below for the current offenders. Unlike complexity, file size has no CI
  gate, so nothing catches this drift automatically.

## Why this exists

Activating McCabe (ruff `C90`) and cognitive-complexity (flake8
`flake8-cognitive-complexity`) linting surfaced real, pre-existing
violations against AGENTS.md's ultimate targets (McCabe $\le$ 10, Cognitive $\le$ 15).
Rather than block the tooling activation on refactoring all of them in a single
step, both were ratcheted downwards progressively.

Following PR #161's decomposition passes, the ratchet ceilings are now lowered to:
- **McCabe Complexity Ceiling**: 15 (Target: 10)
- **Cognitive Complexity Ceiling**: 20 (Target: 15)

## Progress and decomposed functions

The following 25 complexity offenders were refactored and decomposed into cohesive
helper functions:

| Function | File | Prior McCabe | Prior Cognitive | New McCabe | New Cognitive | Status |
| :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `_read_pitloom_config_from_cfg` | `src/pitloom/extract/_setuptools_cfg.py` | 32 | 57 | $\le 10$ | $\le 10$ | Fixed |
| `read_setup_py` | `src/pitloom/extract/_setuptools_py.py` | 21 | 40 | $\le 10$ | $\le 15$ | Fixed |
| `read_wheel` | `src/pitloom/extract/wheel.py` | 20 | 40 | $\le 10$ | $\le 15$ | Fixed |
| `finalize` | `src/pitloom/_loom_active_run.py` | 15 | 38 | $\le 10$ | 17 | Fixed |
| `add_ai_models` | `src/pitloom/assemble/spdx3/ai.py` | 13 | 38 | $\le 10$ | $\le 15$ | Fixed |
| `read_gguf` | `src/pitloom/extract/_gguf.py` | 21 | 37 | $\le 10$ | $\le 15$ | Fixed |
| `build_deployed` | `src/pitloom/assemble/spdx3/_document_deployed.py` | 15 | 36 | $\le 10$ | $\le 15$ | Fixed |
| `parse_file_header` | `src/pitloom/extract/_file_headers.py` | 15 | 30 | $\le 10$ | $\le 15$ | Fixed |
| `_parse_model_config` | `src/pitloom/extract/_hdf5.py` | 13 | 27 | $\le 10$ | $\le 15$ | Fixed |
| `_extract_card_description` | `src/pitloom/extract/_huggingface_fetch.py` | 11 | 26 | $\le 10$ | $\le 15$ | Fixed |
| `scan_project_for_ai_models` | `src/pitloom/extract/scanner.py` | 11 | 25 | $\le 10$ | $\le 15$ | Fixed |
| `_build_ai_package` | `src/pitloom/assemble/spdx3/_ai_package.py` | 21 | 24 | $\le 10$ | $\le 15$ | Fixed |
| `_read_pt2_zip` | `src/pitloom/extract/_pytorch_pt2.py` | 15 | 24 | $\le 10$ | $\le 15$ | Fixed |
| `_annotate_relationships` | `src/pitloom/export/spdx3_json.py` | 10 | 23 | $\le 10$ | $\le 15$ | Fixed |
| `_iter_files` | `src/pitloom/_ids_types.py` | 10 | 22 | $\le 10$ | $\le 15$ | Fixed |
| `_read_tar_sdist` | `src/pitloom/extract/_sdist.py` | 11 | 22 | $\le 10$ | $\le 15$ | Fixed |
| `_resolve_cfg_version` | `src/pitloom/extract/_setuptools_cfg.py` | 11 | 22 | $\le 8$ | $\le 10$ | Fixed |
| `_apply_originator` / `_find_license_copyright` | `src/pitloom/assemble/spdx3/deps_supplier.py` | 10 | 22 | $\le 10$ | $\le 15$ | Fixed |
| `read_pyproject` | `src/pitloom/extract/_pyproject.py` | 11 | 22 | $\le 10$ | $\le 15$ | Fixed |
| `read_onnx` | `src/pitloom/extract/_onnx.py` | 14 | 21 | $\le 10$ | $\le 15$ | Fixed |
| `metadata_from_hatchling` | `src/pitloom/extract/hatchling.py` | 12 | 21 | $\le 10$ | $\le 15$ | Fixed |
| `read_croissant` | `src/pitloom/extract/_croissant.py` | 16 | 16 | $\le 10$ | $\le 15$ | Fixed |
| `_build_extra_data` | `src/pitloom/extract/_huggingface_fields.py` | 16 | 16 | $\le 10$ | $\le 15$ | Fixed |
| `_build_dataset_package` | `src/pitloom/assemble/spdx3/dataset.py` | 16 | 16 | $\le 10$ | $\le 15$ | Fixed |

## File-size limits status (DRIFTED -- needs a follow-up pass)

As of 2026-08-18, both boundaries this doc previously reported clean have
been crossed again by organic growth (new tests, new fields), none of it
individually large enough to trip review attention:

- **`src/`** (soft limit 400-500, hard cap 800): 6 files now exceed 400
  lines; two exceed the previous $\le 417$ high-water mark:
  - `src/pitloom/extract/_setuptools_cfg.py` -- 431 lines
  - `src/pitloom/extract/_huggingface_fields.py` -- 426 lines
- **`tests/`** (excluding `tests/extract/huggingface/` mock fixture
  catalogs, which are exempted separately): 4 files now exceed the previous
  $\le 415$ high-water mark:
  - `tests/extract/test_hdf5.py` -- 540 lines (also the largest test file
    outside the exempted Hugging Face catalogs)
  - `tests/extract/test_pytorch_pt2.py` -- 455 lines
  - `tests/assemble/test_assembly_edge_cases.py` -- 440 lines
  - `tests/extract/test_pyproject.py` -- 419 lines

None of these have crossed the 800-line hard cap, so nothing is currently
broken -- but per AGENTS.md, a file should be split *before* crossing the
soft limit, not after. `_setuptools_cfg.py` and `deps_supplier.py`
(407 lines, under the old high-water mark but still growing) are the
best next candidates: both were split once already (see the table below)
and have regrown past a third of their original decomposed size.

Complexity has a CI gate (the ruff/flake8 ratchets above) that makes
regressions visible immediately; file size does not, which is how this
drifted unnoticed. A `wc -l` CI check against the soft limit would close
that gap -- not yet implemented.

| Former oversized file | Split result (at time of split) | Max lines |
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

## Next steps towards target ceilings

The final target floors are:
- `[tool.ruff.lint.mccabe] max-complexity`: 15 -> target 10.
- `.flake8 max-cognitive-complexity`: 20 -> target 15.
- `[tool.pylint.design]`: `max-args` 6 -> target 5, `max-locals` 18 -> target 15.
