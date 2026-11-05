---
Created: 2026-09-15
Last-Modified: 2026-11-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# `--allow-build` build-and-read: real-world validation

See also:
[backend-file-discovery-validation.md](backend-file-discovery-validation.md)
for the static-discovery validation rounds this one builds on (same
`scripts/compare_allow_build.py` method, same fixture conventions) --
split out into its own file once this file's own two rounds pushed the
shared document past its size limit;
[../design/non-hatchling-file-discovery.md](../design/non-hatchling-file-discovery.md)
for the build-and-read design (Track A/B split, roadmap item #4).

## `--allow-build` build-and-read: with vs. without (2026-09-15)

First real-world validation of `_models_wheel_build_and_read.py`'s
build-and-read mechanism and its dispatch invariants
(`_models_wheel_dispatch.py`), using the `--allow-build`-variant method
above (`scripts/compare_allow_build.py`) against six already-vendored
fixtures: one from each of the four registered backends (flit,
setuptools, poetry, pdm) plus both `uv_build` fixtures, which have no
static discovery module at all.

| Fixture | Backend | Static discovery | Result |
| :--- | :--- | :--- | :--- |
| tomli-2.4.1 | Flit | Succeeds | Identical with/without `--allow-build`; real build never invoked |
| sniffio-1.3.1 | setuptools | Succeeds | Identical with/without; real build never invoked |
| pydocstyle-6.3.0 | Poetry | Succeeds | Identical with/without; real build never invoked |
| pdm-backend-2.4.9 | PDM | Succeeds | Identical with/without; real build never invoked |
| rendercv-2.8 | uv_build | No module | `--allow-build` exact match vs. real published wheel (139/139); fallback over-includes by 15 files -- see Findings |
| langfuse-4.15.1 | uv_build | No module | `--allow-build` exact match vs. real published wheel (674/674); fallback *also* exact match here (this project's layout happens to need no exclusions) |

### Findings

- **The "never build when static discovery already succeeded"
  invariant holds for all four registered backends tested.** Flit,
  setuptools, Poetry, and PDM each produced byte-identical SBOMs with
  and without `--allow-build`, and `build_and_read_wheel()` was never
  invoked (confirmed via its own `WARNING:` line's absence from
  stderr) -- exactly the behaviour `_models_wheel_dispatch.py`'s
  `_discover_included_files()` is designed to guarantee (a real build
  must never run when the fast, safe static rescan already worked).
- **`--allow-build` reproduced the real published wheel exactly for
  both uv_build fixtures** (139/139 files for rendercv, 674/674 for
  langfuse) -- the first empirical confirmation that build-and-read's
  file list matches ground truth, not just "a plausible-looking list".
- **The Hatchling-heuristic fallback (no `--allow-build`) over-includes
  for rendercv, never under-includes.** 15 extra files, all under
  `rendercv/renderer/rendercv_typst/` (a vendored Typst package's own
  `README.md`/`LICENSE`/`CHANGELOG.md`/`examples/**`/`template/**`/
  `thumbnail.png`) -- present on disk in the sdist, so Hatchling's
  generic heuristic includes them, but excluded from the real wheel by
  rendercv's own `[tool.uv.build-backend] wheel-exclude = [...]` table
  in `pyproject.toml`. That table is uv_build-specific syntax; nothing
  in Hatchling's `WheelBuilder.recurse_included_files()` (or Pitloom's
  own dispatch code, which just forwards whatever it returns) has any
  way to know about it. Not a bug in the fallback -- a structural limit
  of applying *any* other backend's static heuristic to a project it
  wasn't designed to introspect, which is exactly why `--allow-build`
  exists. Not fixed here: closing this gap properly would mean writing
  a real static `_models_wheel_uv_build.py` parser for
  `[tool.uv.build-backend]` (a genuine new Track A module, out of
  scope for this round -- see
  [../design/non-hatchling-file-discovery.md](../design/non-hatchling-file-discovery.md)).
  The fallback's failure direction here (over-inclusion, zero
  omissions) is the safer one for an SBOM's completeness guarantee even
  though it's imprecise.
- **The langfuse fixture shows the fallback isn't always wrong** -- its
  layout happens to need no uv_build-specific exclusions, so the
  heuristic already matches the real wheel exactly, and `--allow-build`
  reaches the identical, correct answer via a completely different
  mechanism (a real build). Useful as a non-regression check: adding
  `--allow-build` support changed nothing about the already-correct
  case.
- **Fixed as a follow-up**: the fallback's `WARNING:` now names this
  specific divergence risk when it's actually present, rather than
  leaving it as a general "may be inaccurate" caveat. A new
  `has_uv_build_backend_overrides()` (`_models_wheel_types.py`) checks
  the parsed `pyproject.toml` for a non-empty `[tool.uv.build-backend]
  wheel-exclude`/`wheel-include` -- the two keys confirmed above to
  actually filter the wheel's file set, deliberately narrower than
  every key that table can hold. langfuse's own `[tool.uv.build-backend]
  module-root = ""` was the reason for that narrowing, not a
  hypothetical: it's present there and makes zero difference to the
  resolved file set, so a presence-only check would have produced a
  false-alarm warning on a project where the fallback is already
  correct -- the same "empty-but-real vs. absent" class of mistake
  CLAUDE.md's "Recurring bug patterns" section warns about, just for a
  boolean signal instead of a data field. Verified against both
  fixtures: rendercv (has `wheel-exclude`) gets the sharpened warning,
  langfuse (has the table but only `module-root`) does not.

## `--allow-build` wider sweep: 9 more real uv_build packages (2026-09-15)

Extends the round above from 2 to 11 real `uv_build` packages, using
`scripts/compare_allow_build.py` against candidates found via GitHub
code search (`build-backend = "uv_build"` in `pyproject.toml`, filtered
to packages actually published on PyPI with both a real sdist and a
real wheel available) -- specifically to stress-test whether rendercv's
`wheel-exclude` divergence and the `has_uv_build_backend_overrides()`
warning-sharpening (previous round) generalise, or were a one-off.

| Package | Version | `[tool.uv...]` config | Result |
| :--- | :--- | :--- | :--- |
| asynckivy | 0.11.0 | None (`[tool.uv] default-groups` only, unrelated to build-backend) | `--allow-build` exact match (11/11); fallback identical |
| compress-pptx | 1.3.1 | None | `--allow-build` exact match (5/5); fallback identical |
| ffmpeg-normalize | 1.42.0 | `[tool.uv_build]` (old flat schema, not `[tool.uv.build-backend]`) `src-layout = true`, `package-data` | `--allow-build` exact match (14/14); fallback identical despite overrides -- see Findings |
| pytest-accept | 0.3.0 | `[tool.uv.build-backend] module-name = "pytest_accept"` (redundant -- matches what Hatchling would guess anyway) | `--allow-build` exact match (21/21); fallback identical |
| pyzotero | 1.15.1 | `[tool.uv.build-backend] source-include` only (sdist-level, not wheel-level) | `--allow-build` exact match (18/18); fallback identical |
| qasync | 0.28.0 | None | `--allow-build` exact match (5/5); fallback identical |
| streamlit-folium | 0.27.4 | `[tool.uv.build-backend] module-root = "."` (no-op default), `source-include`/`source-exclude` (sdist-level) | `--allow-build` exact match (15/15); fallback identical |
| textual-canvas | 1.1.0 | None | `--allow-build` exact match (4/4); fallback identical |
| django-model-import | 0.9.0 | `[tool.uv.build-backend] module-name = ["djangomodelimport"]` (does NOT match what Hatchling would guess from `django_model_import`) | `--allow-build` exact match (15/15); fallback returns **zero files**, loudly `WARNING:`-logged -- new, more severe failure mode, see Findings |

All nine vendored as regression fixtures where a divergence was found
(django-model-import only -- see below); the other eight were
throwaway comparisons, not vendored, since they showed nothing a
sibling package didn't already cover (`--allow-build` exact match, no
gap to pin).

### Findings

- **`--allow-build` remains byte-exact across all 11 packages tested so
  far** (2 from the original round + 9 here) -- zero exceptions. This is
  now a reasonably broad confirmation, not just two data points.
- **`wheel-exclude`/`wheel-include` really are the only
  wheel-file-filtering keys that matter, confirmed by contrast.**
  `source-include`/`source-exclude` (pyzotero, streamlit-folium) control
  what goes into the **sdist**, not the wheel -- Pitloom's discovery
  always runs against an already-extracted sdist tree, so these two keys
  can never affect a wheel-file comparison by construction, not just
  empirically. `module-name`/`module-root` (pytest-accept,
  streamlit-folium, langfuse from the prior round) change *where*
  uv_build looks for the package, and in every case tested here the
  declared value matched what Hatchling's own zero-config guess would
  have found anyway -- redundant, not divergence-causing.
  `has_uv_build_backend_overrides()`'s narrow scoping (previous round)
  holds up: no false alarm on any of these five override-bearing
  packages, and the real divergence case (rendercv) is still the only
  one with `wheel-exclude` actually populated.
- **django-model-import is a NEW, more severe failure shape**: a
  `module-name` override that genuinely does NOT match Hatchling's
  guess doesn't just cause imprecision (rendercv's over-inclusion) --
  Hatchling's own `WheelBuilder` cannot find *any* directory to
  package at all, and fails outright (`discover()` returns `None`,
  which `get_wheel_files()` correctly treats as a discovery failure,
  not an authoritative empty result -- see the "None vs `[]`" rule in
  CLAUDE.md's "Recurring bug patterns"). Already loudly reported: both
  the generic "not yet backend-aware" `WARNING:` and Hatchling's own
  specific "no directory that matches the name of your project"
  `WARNING:` fire, so this was never a silent failure -- just a
  previously-undiscovered *shape* of the same known gap. Vendored as
  `tests/fixtures/real-world-projects/uv_build/django-model-import-0.9.0/`
  with a fast, offline regression test pinning the exact warning text
  (`test_default_discovery_fails_loudly_for_module_name_mismatch` in
  `test_models_wheel_uv_build_real_world.py`) plus the existing slow
  `--allow-build`-exact-match parametrized test (picked up automatically
  via the fixture directory, no test code change needed for that half).
- **`has_uv_build_backend_overrides()` does not detect this case, and
  correctly so given the evidence available -- but it's a real, named
  limitation, not an oversight.** `module-name` mismatching Hatchling's
  guess is a real, confirmed divergence trigger (django-model-import),
  yet also confirmed *not* to trigger divergence when it merely restates
  the guessed value (pytest-accept). Distinguishing the two would need
  actually running Hatchling's own name-guessing logic against the
  declared `module-name` -- a materially bigger check than a presence
  test, and not attempted here. The sharpened warning still fires for
  every case with `wheel-exclude`/`wheel-include` populated (the one
  reliably-precise signal found so far); a `module-name`-mismatch case
  still only gets the generic "may be inaccurate" wording plus
  Hatchling's own specific error -- both already informative, just not
  as targeted as the `wheel-exclude` case's pointer to `--allow-build`.
- **A second, distinct `[tool.uv...]` schema exists and is currently
  invisible to `has_uv_build_backend_overrides()`.**
  ffmpeg-normalize declares `[tool.uv_build]` (flat, not nested under
  `[tool.uv]`) with `src-layout = true` and a `[tool.uv_build.package-data]`
  table -- an older or alternate uv_build config location, distinct from
  `[tool.uv.build-backend]`. `has_uv_build_backend_overrides()` only
  ever checks the latter, so this table is invisible to the
  warning-sharpening logic entirely. No practical bug resulted here
  (the fallback matched exactly regardless), but the helper's coverage
  claim is narrower than "every uv_build config surface" -- worth
  noting for whoever eventually writes the real static
  `_models_wheel_uv_build.py` discoverer (roadmap item), which would
  need to handle both schemas, not just `[tool.uv.build-backend]`.
- **Method note**: candidates were found via `gh api search/code`
  (GitHub's code-search API, authenticated) for
  `"build-backend = \"uv_build\"" filename:pyproject.toml`, then
  cross-checked against PyPI directly (not `pip download`, which
  requires the backend importable to resolve metadata even for
  `--no-deps`) -- fetch `https://pypi.org/pypi/<pkg>/json`, download the
  sdist and wheel URLs directly, discard the wheel after extracting its
  file list. One GitHub search hit (`flake8-comprehensions`) had
  already migrated back to `setuptools.build_meta` since being indexed
  -- confirmed and discarded before running the comparison, per the
  existing Method section's "confirm the declared build backend"
  caution.
