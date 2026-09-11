---
Created: 2026-09-12
Last-Modified: 2026-09-12
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Generic multi-candidate field representation (not built)

See also
[multi-source-conflict.md](../implementation/provenance/multi-source-conflict.md)
(G2's implementation depth -- both concrete examples below live there) and
[role-vocabulary.md](../implementation/provenance/role-vocabulary.md) (the
current `role` vocabulary this doc's open question would extend or
complement).

This is a parked design question, not a solution -- raised while planning
G2's dependency-version field, deliberately not designed further at that
time to keep that change small.

## The question

Two fields now hand-build a G2 `ConflictCandidate` list, each at its own
assembly call site, with no shared representation carrying the underlying
labeled values from extraction through assembly:

- **License**: `ProjectMetadata` carries two separate named fields
  (`license` = declared, `license_concluded` = detected), each extracted
  independently; `deps_license.py::build_license_elements` takes exactly
  those two named parameters and builds exactly `hasDeclaredLicense`/
  `hasConcludedLicense`.
- **Dependency version**: no extraction-stage field at all --
  `deps_installed.py::build_dependency_version_conflict` re-derives both
  candidate values (declared specifier, lock-resolved version) from
  already-resolved data, on demand, inside the assembly layer.

Neither carries a general "here is a field with N labeled candidate
values" shape. The open question: is it worth introducing one -- e.g. a
`FieldCandidates`-style type (a mapping of role -> value) threaded from
extraction through assembly -- plus a shared per-field export policy
answering "which roles map to which native SPDX relationship, if any, and
which are Annotation-only"? License's policy is "declared ->
hasDeclaredLicense, detected -> hasConcludedLicense, always build both,
Annotation only on disagreement." Dependency version's policy is "no
native slot for a second candidate at all, Annotation only." A generic
representation would let a third field's policy be expressed the same way
instead of hand-written again.

## BSI TR-03183 as a candidate richer vocabulary

The current `role` vocabulary (`declared`/`detected`/`externalReported`/
`inferred`/`sbomAuthorSupplied`, see role-vocabulary.md) is an
epistemic-process label -- *whose* determination a value is. BSI
TR-03183 uses a different three-way split for version-like fields:
`original`/`distribution`/`effective` -- roughly, the value as the
upstream project stated it, the value as a distribution/packaging step
changed it, and the value actually in effect. That's a different axis
(lifecycle stage a value was captured at, not who determined it) and
might not replace `role` so much as compose with it. Worth comparing the
two vocabularies properly once a concrete field needs more than the
binary declared/detected split -- not decided here.

## Two concrete motivating examples (already built, hand-rolled)

Both are implemented in full in
[multi-source-conflict.md](../implementation/provenance/multi-source-conflict.md)
-- read that file for the actual mechanics, normalization, and code
locations. This doc only records that they're two independent, structurally
different instances of the same underlying shape:

- License: two named extraction fields, two native relationships, a
  strict normalize-then-equality conflict test.
- Dependency version: no extraction field, one native relationship slot,
  a specifier-containment conflict test, and an asymmetric candidate
  shape (one side a concrete version, the other a specifier expression).

## Not decided here

- Whether a shared type is worth the migration cost of rewriting
  license's `build_license_elements` onto it.
- Whether `role` and a BSI-style lifecycle-stage label should be two
  separate fields on a candidate, or whether one subsumes the other.
- What the export-time policy type/interface would look like.

Revisit once a third multi-source field is proposed for G2.
