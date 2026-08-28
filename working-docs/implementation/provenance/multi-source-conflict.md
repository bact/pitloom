---
Created: 2026-08-25
Last-Modified: 2026-08-25
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# G2: multi-source disagreement

See also [annotation-provenance.md](annotation-provenance.md) (canonical
design rationale, start here),
[annotation-mechanism.md](annotation-mechanism.md),
[role-vocabulary.md](role-vocabulary.md),
[use-case-catalog.md](use-case-catalog.md) (G2's short catalog summary).

This file is the implementation depth behind G2 -- the largest and
most fleshed-out use case in the catalog. The `role` vocabulary G2
relies on is documented once, generally, in
[role-vocabulary.md](role-vocabulary.md) rather than repeated here.

## G2 — multi-source disagreement (2026-08-10, generalized, license implemented)

License is the first field this fires for, but the *mechanism* — several
sources reporting different values for the same field — applies to any
field. Built as a generic schema from the start so a future field or
candidate source never requires another schema redesign.

**Where it lives.** [`provenance.py`](../../../src/pitloom/assemble/spdx3/provenance.py)
`ConflictCandidate` (a `TypedDict`) + `build_conflict_annotation`. Schema
URL `https://pitloom.dev/provenance/conflict/1`, envelope:

```json
{
  "schema": "https://pitloom.dev/provenance/conflict/1",
  "kind": "conflict",
  "field": "license",
  "candidates": [
    {"value": "MIT", "role": "declared", "source": "Source: pyproject.toml | Field: project.license", "ref": "<spdxId of hasDeclaredLicense target>"},
    {"value": "Apache-2.0", "role": "detected", "source": "Source: LICENSE | Method: licenseid_detection | Tool: licenseid==0.3.0", "ref": "<spdxId of hasConcludedLicense target>"}
  ]
}
```

Only emitted when candidates actually disagree after normalization
(`_license.py` `normalize_license_expression`, built on the
[`py-spdx-license`](https://github.com/JPEWdev/py-spdx-license) parser —
a plain `.strip()` comparison alone would false-positive not just on
casing differences (declared `"mit"` vs. detected `"MIT"`) but on
equivalent-yet-differently-spelled compound expressions too (`"MIT AND
MIT"` vs. `"MIT"`; `"MIT OR Apache-2.0"` vs. `"Apache-2.0 OR MIT"`) — so
both candidate values are parsed, deduplicated, and canonically reordered
before both the comparison and the license-element lookup/creation. A
value that fails to parse as a valid SPDX expression at all falls back to
`canonicalize_license_id`'s bare-id casing lookup, then to the raw string
unchanged. Full agreement emits no Annotation — both native relationships
still get built, just pointing at the same license element, and there's nothing
extrinsic left to assert.

**File-level exception:** a `software_File`'s own `SPDX-License-Identifier`
header tag always maps to `hasDeclaredLicense`, never
`hasConcludedLicense`, regardless of the general `declared`/`detected`
split in [role-vocabulary.md](role-vocabulary.md). There is exactly one
candidate at file granularity (the file's own header, if any) and its
role is `declared` by construction — nothing to disambiguate, so the
concluded-vs-declared classification heuristic used at project/dependency
level doesn't apply. See `build_file_declared_license` in
[`deps_license.py`](../../../src/pitloom/assemble/spdx3/deps_license.py) and
[file-headers.md](../file-headers.md) for the full per-file
extraction design.

**What's actually built (v1, license only).**
[`_license.py`](../../../src/pitloom/extract/_license.py)
`detect_independent_license` — independently scans the project directory
(`CITATION.cff`, `codemeta.json`, license files), *ignoring* any declared
value, so there's a genuine second opinion to compare against. Previously,
a declared value that already looked like a valid SPDX id short-circuited
before the `LICENSE` file was ever read, so there was nothing to disagree
with; now the independent scan always runs alongside it.

`resolve_license_concluded` (also in `_license.py`) is the single, shared
G2 entry point every project-metadata extractor calls — not just
`_pyproject.py`'s `[project]` path. It exists because the extraction
paths (CLI's [`_pyproject.py`](../../../src/pitloom/extract/_pyproject.py)
`read_pyproject` -- including its poetry-only fallback through
[`_poetry.py`](../../../src/pitloom/extract/_poetry.py)
`extract_poetry_metadata` -- the
[`hatchling.py`](../../../src/pitloom/extract/hatchling.py) build-hook
path, and the setuptools-only
[`_setuptools.py`](../../../src/pitloom/extract/_setuptools.py)
`read_setuptools`) were each written and evolving independently. G2 first
shipped wired only into the CLI path; a later review found the Hatchling
build hook called `detect_license_for_project` directly and never ran the
independent scan at all, so G2 silently never fired for any Hatchling-built
project. Rather than patch that one path, all four now call the same
`resolve_license_concluded` (and, for the poetry-only and setuptools-only
paths, the same directory-detection fallback when nothing is declared) so
a future fifth extraction path can't reintroduce the same gap by omission.
Cross-path regression tests
(`test_metadata_from_hatchling_matches_read_pyproject_for_license_conflict`
in `tests/extract/test_hatch_hook_metadata.py`,
`test_read_poetry_matches_read_pyproject_fallback_for_license_conflict` in
`tests/extract/test_poetry_pyproject.py` -- paths since renamed and moved,
see `cli-test-coverage-roadmap.md`) assert the paths agree on the same
project. The
same review also found the Hatchling and CLI paths each hand-listed their
own `[tool.poetry]`-gap-fill field merge (`_merge_with_poetry` in
`_pyproject.py`, `merge_metadata` in `_setuptools.py`); both were replaced
by [`core/project.py`](../../../src/pitloom/core/project.py)'s
`merge_project_metadata`, which iterates `dataclasses.fields()` instead of
naming every field by hand, so a newly added `ProjectMetadata` field
merges automatically without a call site needing to be updated (see its
own docstring for the field-drift history that motivated this).
[`deps_license.py`](../../../src/pitloom/assemble/spdx3/deps_license.py)
`build_license_elements` gained `concluded_license_id`/
`concluded_license_provenance` params (`None` default — the three other
call sites, dependency and AI-model licenses, are unaffected, since
neither has a local second source to detect from today): when given, both
candidates are run through `normalize_license_expression` before both the
comparison and the license-element lookup/creation, then both
`hasDeclaredLicense` and `hasConcludedLicense` are always built, and a G2
conflict Annotation is added on disagreement.

`normalize_license_expression` (also in `_license.py`) is the new,
stronger canonicalization step: operator casing (`AND`/`OR`/`WITH`/`NOT`)
is normalized first — but only when the operator stands alone as its own
whitespace/paren-delimited token, never when it's hyphen-glued into an
identifier (`GPL-2.0-or-later`, a custom `LicenseRef-my-or-license`) —
then the result is parsed and canonically sorted via `py-spdx-license`
(a new base dependency). This both canonicalizes bare-id casing (same as
`canonicalize_license_id`, which it falls back to on a parse failure) and
dedupes/reorders compound expressions, which `canonicalize_license_id`
alone never handled.

**Real-world validation.** This is not a hypothetical gap:
[Trivy discussion #10139](https://github.com/aquasecurity/trivy/discussions/10139)
reports scanning the same package and getting the same license expression
back with and without a redundant outer paren
(`GPL-3.0-or-later WITH GCC-exception-3.1` vs.
`(GPL-3.0-or-later WITH GCC-exception-3.1)`), breaking policy rules that
compare against one fixed string. Checked `normalize_license_expression`
against all four of that report's example pairs — every pair normalizes
to an identical string. Separately verified the harder case, where a
paren is *not* redundant: for mixed `AND`/`OR` expressions,
`MIT AND Apache-2.0 OR BSD-3-Clause` (no parens, relies on `AND` binding
tighter than `OR` per the SPDX spec) and
`(MIT AND Apache-2.0) OR BSD-3-Clause` (explicit parens matching that
same default precedence) both normalize to `Apache-2.0 AND MIT OR
BSD-3-Clause`, while `MIT AND (Apache-2.0 OR BSD-3-Clause)` (parens
*overriding* default precedence, semantically different) correctly stays
distinct and keeps its now-necessary paren. So the normalization strips
parens exactly when they're redundant and keeps them exactly when they're
load-bearing — not a blanket strip-all-parens heuristic.

**Future candidate sources (not built — `enrich/`-territory network or
agent work, cross-referenced to
[`sbom-enrichment.md`](../../design/sbom-enrichment.md)'s existing source
table):** HF Hub API (`externalReported`), GitHub via `ExternalRef`
(`detected` if Pitloom runs its own scan on the fetched file,
`externalReported` if relaying GitHub's own license badge), a linked
paper (`externalReported`), README/source-comment agent inference
(`inferred`). The schema already has the `role` slots waiting for all of
these — no further schema change needed when they land.
