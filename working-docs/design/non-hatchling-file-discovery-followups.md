---
Created: 2026-11-06
Last-Modified: 2026-11-06
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Non-Hatchling file discovery: open follow-ups

See also:
[non-hatchling-file-discovery.md](../implementation/non-hatchling-file-discovery.md)
(the built backend-agnostic discovery, the backend priority table and the
dependency packaging strategy these follow-ups refer to),
[roadmap.md](roadmap.md) (Open follow-ups by area: "File discovery"),
[build-backend-improvements.md](build-backend-improvements.md),
[allow-build-validation.md](../implementation/allow-build-validation.md).

Split from the built page on 2026-11-06: what remains open after the
backend-agnostic discovery closed (2026-09-15).

## Open follow-up tech debt (from PR #215's `--allow-build` review)

The priority table (in the built page) is closed for every backend, but the
PR #215 review that landed the build-and-read mechanism (item #4/#5) surfaced
five smaller, independently-fixable follow-ups. None block the closed
work; each is its own reviewed change. The first, the blanket-except
`WARNING:` duplicated across every backend discoverer, is done: all five
(Hatchling included) call `warn_discovery_failed()` in
`_models_wheel_types.py`, which also collapses a multi-line exception to
one line. Four remain:

- **Factor out the hand-rolled `tool` -> `tool.X` -> nested-table walk
  repeated across 6+ modules** -- `has_uv_build_backend_overrides()`
  (`_models_wheel_types.py`) reimplements the same isinstance-guarded
  chain `_load_pitloom_tool_section()` and every `extract/project/*.py`
  metadata producer (`poetry.py`, `pdm.py`, `setuptools_cfg.py`,
  `pyproject.py`, `pyproject_dynamic.py`) already does independently --
  the "pattern hand-copied across 3+ call sites drifts" class AGENTS.md
  calls out by name. A shared `get_tool_table(data, *keys)`-style helper
  would touch several stable, already-tested producer modules.
- **`scripts/compare_allow_build.py` duplicates sdist extraction already
  in `tests/fixtures/real_world.py`** -- `_extract_archive()`
  reimplements `extract_sdist()`'s tar/zip-open, `filter="data"`,
  single-top-level-dir logic, generalised to accept any archive path.
  Dev-only script, not shipped code, no user-facing risk -- low priority.
- **`--allow-build`-sourced files never match a `loom id
  generate`-pinned registry entry** -- `IdRegistry.generate()` (`id_registry/_registry.py`)
  keys every entry by physical, project-root-relative path; a
  build-and-read-sourced `ProjectFile.physical_path` is an ephemeral
  temp path instead, so neither of `_document_files.py`'s two lookup
  attempts (`physical_path`, then `distribution_path`) can ever match a
  pre-pinned entry for such a file -- a new spdxId is silently minted
  instead. Harvest-to-harvest id stability (a normal `loom project` run
  finding ids a *previous* `loom project` run wrote) is unaffected --
  both write and read sides key by `distribution_path` there. Real fix
  needs `_document_files.py`'s registry lookup to gain a third candidate
  (`project_dir`-relative `distribution_path`, checked for existence),
  which needs threading `project_dir` into a currently filesystem-free
  assembly function -- a real design change, not a quick patch.
  **Partially addressed** (2026-09-15, a later PR #215 review round): a
  *separate* AI-model registry lookup, `_ai_package.py`'s
  `_lookup_ai_model_entity`, was found with the identical hazard but no
  guard at all -- it offered the raw ephemeral `physical_path` as its
  only path-based candidate, guaranteed to never match anything, unlike
  `_document_files.py`'s two-attempt (still-insufficient) lookup above.
  Fixed by adding a `file_path_relative` fallback via the new shared
  `pitloom.core.project.project_relative_or_fallback()` helper (also now
  used by `_document_files.py`'s determinism fix and
  `enrich._resolve_model_search_dir`, consolidating what had been three
  independent inline implementations of the same "prefer a
  project-relative stand-in over an absolute physical_path" check -- see
  AGENTS.md's "Recurring bug patterns" section). This closes the
  guaranteed-never-match case for AI models but does **not** fully solve
  the general problem above: `file_path_relative` still won't match an
  entry `loom id generate` pinned under the *original*
  project-relative `physical_path` for a `src/`-layout project, so the
  real fix (a third, existence-checked candidate) described above still
  applies equally here.
- **Real static `uv_build` discoverer for `[tool.uv.build-backend]`** --
  validated empirically (2026-09-15, see
  [allow-build-validation.md](../implementation/allow-build-validation.md#--allow-build-build-and-read-with-vs-without-2026-09-15))
  that the Hatchling-heuristic fallback over-includes files a project's
  own `wheel-exclude`/`wheel-include`/`module-name` directives in
  `[tool.uv.build-backend]` would drop (15 extra files for the
  rendercv-2.8 fixture, all correctly excluded by `--allow-build`'s real
  build). `--allow-build` already closes this gap exactly, so this is a
  precision improvement for the *default* (no-flag) path only --
  parsing `[tool.uv.build-backend]` statically, the same shape of work
  as the existing setuptools/Poetry/PDM/Flit modules. **Partially
  addressed** (2026-09-15): the fallback's `WARNING:` now names this
  specific divergence risk and points at `--allow-build` when
  `wheel-exclude`/`wheel-include` is actually present
  (`has_uv_build_backend_overrides()` in `_models_wheel_types.py`).
  **Wider sweep** (2026-09-15, 9 more real packages, see
  [allow-build-validation.md](../implementation/allow-build-validation.md#--allow-build-wider-sweep-9-more-real-uv_build-packages-2026-09-15))
  found a second, more severe failure shape: a `module-name` that
  doesn't match Hatchling's zero-config guess (django-model-import)
  makes the fallback fail outright with zero files, not just
  over-include -- already loudly `WARNING:`-logged, and a future real
  discoverer would need to handle two distinct config schemas, not one:
  `[tool.uv.build-backend]` (current) and an older flat
  `[tool.uv_build]` (found on ffmpeg-normalize, currently invisible to
  `has_uv_build_backend_overrides()` too, though no practical divergence
  was observed for it).

Also open:

- setuptools gives an absolute `physical_path` for a project directory named
  in another letter case (macOS, Windows; #257, in
  [known-bugs.md](known-bugs/extraction-and-fragments.md#p3-after-0200)).
- scikit-build-core is checked only through `--allow-build`
  ([#61](https://github.com/bact/pitloom/issues/61)).
