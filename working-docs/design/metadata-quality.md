---
Created: 2026-09-28
Last-Modified: 2026-10-04
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
  Also a prerequisite for systematic licence rules:
  [license-layers.md](license-layers.md#prerequisites-conflict-resolution-provenance-and-taxonomy).
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

## Licence follow-ups (PR #276 review)

Recorded, not built. Context:
[license-typing.md](../implementation/license-typing.md).

- [ ] **Move licence content (`classify_license`) to py-spdx-license /
  licenseid; Pitloom keeps an adapter.** See
  [license-layers.md](license-layers.md).
- [ ] **No G2 second opinion for a wheel.** Its SBOM records the
  archive's declared licence only (predates #276). An sdist now runs the
  directory's detection; a wheel needs `License-File:` selection to pick
  its `.dist-info/licenses/` members (0.21.0).
- [ ] **A detected licence text differs by surface.** A `license.file`
  whose text `licenseid` identifies (e.g. an Apache `LICENSE` with centring
  spaces) is the id on a directory and the hook, the text from an sdist,
  wheel or installed metadata. Detection on those readers, or none on the
  directory, would align them; a content decision.
- [ ] **SPDX 3.1: exactly one concluded licence.** 3.1 requires one
  `hasConcludedLicense` per artifact. Pitloom targets 3.0.1 and emits none
  when no source concludes one (an absent licence gives no relationship), so
  moving to 3.1 needs a rule for that case.
- [ ] **`LicenseRef-` case.** SPDX matches licence ids case-insensitively,
  but `LicenseRef-Foo` and `LicenseRef-foo` are two elements, and the parser
  rejects a lower-case `licenseref-` prefix (recorded as text).
- [ ] **Per-file tag and copyright.** A file with two
  `SPDX-License-Identifier:` lines keeps only the first. The main package's
  `copyrightText` inferred from its authors
  (`Method: inferred_from_authors`) is not a copyright anyone stated.
