---
Created: 2026-08-17
Last-Modified: 2026-10-21
SPDX-FileCopyrightText: 2026 Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Complexity and file-size roadmap

See also: [cli-test-coverage-roadmap.md](cli-test-coverage-roadmap.md) for
the sibling test-suite health effort this doc's structure follows.

**Status:**
- McCabe complexity ratchet: `max-complexity = 14` (`pyproject.toml` ruff
  `C90` and `.flake8`; target 10).
- Cognitive complexity ratchet: `max-cognitive-complexity = 20` (`.flake8`;
  target 15).
- File-size refactoring is **not** complete: files drift above the limits (see
  "File-size limits status"). Unlike complexity, file size has no CI gate, so
  nothing catches this drift automatically.

## Why this exists

Activating McCabe (ruff `C90`) and cognitive-complexity (flake8
`flake8-cognitive-complexity`) linting surfaced real, pre-existing
violations against AGENTS.md's ultimate targets (McCabe $\le$ 10, Cognitive $\le$ 15).
Rather than block the tooling activation on refactoring all of them in a single
step, both were ratcheted downwards progressively.

Following PR #161's decomposition passes, the ratchet ceilings are:
- **McCabe Complexity Ceiling**: 14 (Target: 10)
- **Cognitive Complexity Ceiling**: 20 (Target: 15)

## File-size limits status (DRIFTED -- needs a follow-up pass)

Snapshot of 2026-10-21 (`wc -l`). Organic growth keeps crossing the soft limit,
none of it individually large enough to trip review attention:

- **`src/`** (soft limit 400-500, hard cap 800): 42 files exceed 400 lines and
  11 exceed 500. Worst: `extract/lock/_common.py` (611),
  `assemble/spdx3/deps_license.py` (520), `extract/lock/uv.py` (518),
  `extract/ai_model/pytorch_pt2.py` and `export/spdx3_json.py` (515 each),
  `extract/remote/huggingface_field.py` and `core/ai_metadata.py` (508 each),
  `extract/_license.py` (507), `extract/ai_model/hdf5_config.py` (505),
  `assemble/spdx3/deps.py` (505) and `assemble/spdx3/_ai_package.py` (504).
- **`tests/`** (excluding the `hf_patches/` mock catalogs): files over 500 lines
  are `assemble/test_deps_enrichment_pypi_fallback.py` (691, the worst, near the
  hard cap), `extract/lock/test_common.py` (579), `cli/test_cli_option_reach.py`
  (565), `core/models_wheel/test_models_wheel_setuptools.py` (542),
  `extract/project/test_installed.py` (531) and
  `extract/ai_model/test_pytorch_pt2.py` (531). The `hf_patches/` catalogs run
  to 583 lines.
- **Docs** (same limits, ~30KB): over 500 lines are
  `working-docs/design/mlflow-extractor.md` (597),
  `working-docs/implementation/manual-cli-checks.md` (532) and
  `working-docs/design/canonical-output-followups.md` (529), and `action.yml`
  (604); `CHANGELOG.md` (551) is exempt by nature.

None of the code files have crossed the 800-line hard cap, so nothing is
currently broken -- but per AGENTS.md, a file should be split *before* crossing
the soft limit.

Complexity has a CI gate (the ruff/flake8 ratchets above) that makes
regressions visible immediately; file size does not, which is how this
keeps drifting unnoticed. A `wc -l` CI check against the soft limit would
close that gap -- not yet implemented.

## Next steps towards target ceilings

The final target floors are:
- `[tool.ruff.lint.mccabe] max-complexity`: 14 -> target 10.
- `.flake8 max-cognitive-complexity`: 20 -> target 15.
- `[tool.pylint.design]`: `max-args` 6 -> target 5, `max-locals` 17 -> target 15.
