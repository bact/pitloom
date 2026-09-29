---
Created: 2026-09-28
Last-Modified: 2026-09-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Metadata quality

See also: [roadmap.md](roadmap.md) (the summary bullet this file expands
on), [provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md),
[sbom-enrichment.md](sbom-enrichment.md).

Split out of `roadmap.md` (2026-09-28) once this section grew past the
file-size guidance -- moved verbatim, no content changed.

- [ ] **Revise and publish the provenance/enrichment vocabulary reference**
  -- draft `docs/vocabulary.md` page reverted out of `docs/` pending a
  `role`/`method` taxonomy revision; once settled, publish and
  consolidate every place that documents this vocabulary ad hoc into
  one canonical source. See
  [provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md).
- [x] **Generalize multi-source conflict detection beyond license** --
  `build_conflict_annotation`/`ConflictCandidate` now also fires for
  dependency version, not just license. See
  [multi-source-conflict.md](../implementation/provenance/multi-source-conflict.md).
- [ ] **Generic multi-candidate field representation** -- today each
  multi-source field (license, dependency version) hand-builds its own
  `ConflictCandidate` list at its own assembly call site; there's no
  shared type carrying a labeled candidate set (declared/detected/
  concluded, or a richer vocabulary such as BSI TR-03183's original/
  distribution/effective) from extraction through assembly, nor a shared
  per-field policy for "which roles map to which native SPDX relationship
  (if any) vs. Annotation-only." Worth designing once a third field needs
  this. See
  [generic-multi-candidate-fields.md](generic-multi-candidate-fields.md).
- [ ] **Enhanced dependency analysis** -- transitive dependencies, optional
  extras, development dependencies.
- [ ] **Auto-discover default license files when `[project.license-files]`
  is undeclared** -- setuptools' `_finalize_license_files()` and
  Hatchling's `CoreMetadata.license_files` both fall back to the same
  glob (`LICEN[CS]E*`, `COPYING*`, `NOTICE*`, `AUTHORS*`, citing the
  `wheel` package's own documented convention) and bundle whatever
  matches into a real wheel's `.dist-info/licenses/`, even with no
  explicit field. Pitloom's `resolve_license_file_entries()`
  (`src/pitloom/extract/_license.py`) deliberately does *not* replicate
  this today -- both extraction paths only trust an explicit
  `[project.license-files]` declaration (see
  [license-pipeline.md](../implementation/license-pipeline.md)'s
  "License-files bundling" section) --
  because the default glob is a build-backend auto-bundling convenience,
  not something PEP 639 itself defines, and because `NOTICE`/`AUTHORS`
  matches don't obviously belong under a `hasDeclaredLicense` relationship
  the way `LICENSE`/`COPYING` do. If this is picked up, it needs its own
  design pass: which stems to trust, whether it holds for every backend
  (only setuptools and Hatchling are confirmed so far), and a provenance
  label that clearly distinguishes "inferred default" from "explicitly
  declared."
- [x] **SBOM enrichment from external sources** (the `enrich/` subpackage)
  -- MVP shipped: local README/model-card YAML frontmatter parsing,
  gated by `[tool.pitloom] enrich` (default off), code-level and
  deterministic -- distinct from the agent-facing `sbom-enrich` Skill
  above. Still not started: OpenSSF Scorecard, Hugging Face Hub and
  PyPI metadata sources, per-source enable/disable config.
  See [sbom-enrichment.md](sbom-enrichment.md).
- [ ] **OSV.dev vulnerability lookup** (`--enrich-cve` or similar) -- static
  enrichment only (no exploitability judgement); VEX generation under
  Medium-term is the follow-on triage step. See
  [osv-vulnerability-lookup.md](osv-vulnerability-lookup.md).
