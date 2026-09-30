---
Created: 2026-08-17
Last-Modified: 2026-09-30
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

As of 2026-09-14, both boundaries this doc previously reported clean are
still crossed by organic growth, none of it individually large enough to
trip review attention:

- **`src/`** (soft limit 400-500, hard cap 800): 15 files exceed 400 lines,
  worst is `extract/lock/_common.py` at 610 -- new since the lock-hash-
  preservation work (PR #212; see
  [lock-hash-preservation.md](../implementation/lock-hash-preservation.md)),
  which consolidated shared lock-parsing helpers here rather than
  duplicating them per format. `assemble/spdx3/deps.py` also grew past the
  soft limit in the same PR (525, was under 500 before it). Next worst:
  `extract/project/pyproject.py` 530, `assemble/spdx3/deps_license.py` 500,
  `extract/project/setuptools_cfg.py` 471, `extract/lock/uv.py` 462,
  `extract/ai_model/pytorch_pt2.py` 457, `assemble/spdx3/deps_installed.py`
  441, `assemble/spdx3/provenance.py` 440, `cli/options.py` 438,
  `assemble/spdx3/deps_originator.py` 438,
  `extract/lock/pylock.py` 431, `extract/project/poetry.py` 428,
  `extract/remote/huggingface_field.py` 426. `embed.py` (489 after the
  Loom ID registry rework, PR #235) is split: `_resolve_embed_registry`,
  `_settle_build_options`, `_settle_embed_options`,
  `_generate_embed_sbom_json` and `_build_sbom_standalone_wheel` moved to
  a private `pitloom/_embed_generate.py` (278), leaving `embed.py` (243)
  with `embed_filename`/`_enforce_sbom_name_version`/`embed_wheel_sbom`
  and the re-exports. The batch-settle helpers moved too:
  `_generate_embed_sbom_json` calls them, and leaving them in `embed.py`
  would make the two modules import each other.
  `_build_sbom_from_project_and_wheel` was already in
  `_embed_build_sbom.py`.
- **`tests/`** (excluding `tests/extract/huggingface/` mock fixture
  catalogs): 9 files exceed 415 lines, worst is `test_hdf5.py` at 552
  (`test_pytorch_pt2.py` 459, `test_assembly_edge_cases.py` 456,
  `test_annotation_provenance_emit.py` 449, `test_cli_options.py` 429,
  `test_gguf.py` 423; not in that count, also over 500 as of 2026-09-30:
  `assemble/test_embed_overrides.py` 561, whose regression docstring
  still names `embed.py` for `_build_sbom_from_project_and_wheel` (it
  lives in `_embed_build_sbom.py`), and `cli/test_cli_option_reach.py`
  557 -- `test_deps_enrichment_pypi_fallback.py`,
  `test_setuptools_cfg.py`, `test_pyproject.py`, `test_hatch_hook_metadata.py`,
  and `test_poetry_parsing.py` have since been split under this limit, see
  `test_deps_license.py`, `test_setuptools_cfg_backend.py`,
  `test_pyproject_license.py`, `test_hatch_hook_metadata_parity.py`, and
  `test_poetry_extract.py` respectively).

- **Docs** (same limits, ~30KB): as of 2026-09-21,
  `working-docs/design/roadmap.md` is at 799 lines but 48KB, past the
  byte cap -- move completed items' detail out per AGENTS.md's roadmap
  rule. `docs/cli.md` grew to 564 lines in PR #231 (the "Options with no
  effect" table and `--config`); a candidate split is a separate
  `docs/cli-options.md` for the shared-options section. `CHANGELOG.md`
  (1010 lines) is exempt by nature but could archive released versions.
  As of 2026-09-30, after PR #235, three more docs are over the
  ~500-line soft limit and are split candidates: `docs/cli.md` (633,
  grown further by the Loom ID registry rename/hint work), `README.md`
  (553) and `action.yml` (539). `skills/sbom-generate/SKILL.md` was
  split below it in PR #235 (now guarded by
  `tests/test_skill_frontmatter.py`). In `src/`,
  `core/_config_parse.py` was 603; it is now 479, split into the
  `core/_config_read.py` leaf (read primitives) and
  `core/_config_parse_scan.py` (file/model scanning key readers, where
  the `max-model-extract-bytes`/`scan-model-usage` readers belong).

None of the code files have crossed the 800-line hard cap, so nothing is currently broken --
but per AGENTS.md, a file should be split *before* crossing the soft
limit. `deps_originator.py` and `setuptools_cfg.py` are the best next
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
