---
Created: 2026-08-17
Last-Modified: 2026-08-27
SPDX-FileCopyrightText: 2026 Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

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

## File-size limits status (DRIFTED -- needs a follow-up pass)

As of 2026-08-21, both boundaries this doc previously reported clean are
still crossed by organic growth, none of it individually large enough to
trip review attention:

- **`src/`** (soft limit 400-500, hard cap 800): 6 files exceed 400 lines,
  worst is `deps_originator.py` at 438 (`_setuptools_cfg.py` 431,
  `_huggingface_fields.py` 426, `_pytorch_pt2.py` 417, `_loom_active_run.py`
  411, `export/spdx3_json.py` 401).
- **`tests/`** (excluding `tests/extract/huggingface/` mock fixture
  catalogs): 9 files exceed 415 lines, worst is `test_hdf5.py` at 552
  (`test_deps_enrichment_pypi_fallback.py` 460, `test_pytorch_pt2.py` 459,
  `test_assembly_edge_cases.py` 456, `test_annotation_provenance_emit.py`
  449, `test_pyproject.py` 436, `test_cli_options.py` 429,
  `test_setuptools_cfg.py` 426, `test_gguf.py` 423).

None have crossed the 800-line hard cap, so nothing is currently broken --
but per AGENTS.md, a file should be split *before* crossing the soft
limit. `deps_originator.py` and `_setuptools_cfg.py` are the best next
candidates: both were split once already (via the facade pattern used
throughout this pass) and have regrown past a third of their original
decomposed size.

Complexity has a CI gate (the ruff/flake8 ratchets above) that makes
regressions visible immediately; file size does not, which is how this
keeps drifting unnoticed. A `wc -l` CI check against the soft limit would
close that gap -- not yet implemented.

## Next steps towards target ceilings

The final target floors are:
- `[tool.ruff.lint.mccabe] max-complexity`: 15 -> target 10.
- `.flake8 max-cognitive-complexity`: 20 -> target 15.
- `[tool.pylint.design]`: `max-args` 6 -> target 5, `max-locals` 18 -> target 15.
