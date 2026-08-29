---
Created: 2026-08-25
Last-Modified: 2026-08-25
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Use-case catalog

See also [annotation-provenance.md](annotation-provenance.md) (canonical
design rationale, start here),
[annotation-mechanism.md](annotation-mechanism.md),
[role-vocabulary.md](role-vocabulary.md),
[multi-source-conflict.md](multi-source-conflict.md),
[phase2-native-backfill-handover.md](phase2-native-backfill-handover.md).

The taxonomy of *why* an Annotation earns its place for each use case
(G1-G4/A1-A2/E1-E2/P1), plus the Phase 2 native-first backfill
checklist (N1-N6). G2's own implementation depth lives separately in
[multi-source-conflict.md](multi-source-conflict.md).

## Use-case catalog (why the Annotation earns its place)

- **Generation** — G1 inferred/detected/AI-generated qualifier (necessary,
  **implemented**: `licenseid_detection`, `inferred_from_authors` have no
  native assertedness marker); **G2 multi-source disagreement** (necessary
  on conflict, **implemented for license**, generalized beyond license — see
  [multi-source-conflict.md](multi-source-conflict.md) for the full
  mechanism); G3 declared constraint vs resolved version (useful,
  **implemented** — SPDX keeps only the resolved version); G4 sub-file
  location in opaque AI formats (useful, **implemented**).
- **Aggregation** — A1 unification rationale (necessary, **implemented**):
  `_merge_fragment_set` records `(survivor, criterion, dropped_id, fragment)`
  for a **SHA-256 content-equality** match — a genuinely distinct id folded
  into the survivor, which SPDX cannot express — and emits a
  `provenance/unification/1` Annotation on the survivor. A same-id registry
  match carries no such fact (nothing distinct was folded) and is not
  annotated; its fragment origin is Phase-2 `SpdxDocument.imports` territory
  (see N1 below). A2 superseded identity across builds (useful,
  **not implemented — design only**): when file content changes,
  [`ids.py`](../../../src/pitloom/ids.py) `register_file` mints a fresh
  `spdxId` and the old one is simply discarded — no supersedes/replaces
  record survives anywhere. Lower priority than A1: it's a cross-build fact
  (comparing this SBOM to a previous one), not something expressible within
  one SBOM generation.
- **Enrichment** — E1 override lineage, E2 AI-inferred-vs-non-inferred
  marker (both necessary; **implemented**, see the N3 row below for the
  `build_enrichment_annotation()` mechanism). E2's "non-inferred" pole is
  any of G2's `declared`/`detected`/`externalReported` roles (see
  [role-vocabulary.md](role-vocabulary.md)) — same vocabulary, reused
  rather than a separate "extracted" word (which would have collided with
  `extract/`, Pitloom's own name for the whole read-a-value pipeline
  stage). The `enrich/` subpackage itself so far has one source
  (`enrich/readme.py`, local frontmatter, always `"detected"`) --
  `"inferred"` is exercised by the AI-agent `sbom-enrich` Skill's
  fragment path, not yet by in-process code.
- **Preservation** — P1 verbatim original AI-model metadata
  (`provenance/artifact-metadata/1`), config-gated, complements the lossy
  native mapping when the artifact isn't shipped. `raw_metadata` captured
  verbatim by the safetensors & GGUF extractors; HF/others fall back to the
  retained `properties`/`extra_data`. **Extrinsic-assertion justification**
  (this is the one borderline case per the test in
  [annotation-mechanism.md](annotation-mechanism.md)): the blob payload
  looks intrinsic, but P1's role stays extrinsic — it is Pitloom witnessing
  and recording "here is what the source artifact's own header said at
  generation time," not Pitloom declaring a new native characteristic of
  the model. It exists precisely because the artifact won't travel with the
  SBOM and can't be re-read later to re-derive this; a shipped, re-extractable
  artifact gets no P1 blob at all (`preserve-source-metadata = "auto"`),
  which is itself evidence the role is "preserve what would otherwise be
  lost," not "hold a property."

  **Statement size, bounded (2026-08-26, resolved):** the P1 blob embeds
  `raw_metadata` verbatim, and a production LLM's GGUF kv-store can carry a
  32K–128K-entry tokenizer vocab (plus parallel `scores`/`token_type`
  arrays) in a single field — unbounded, that would inflate a single
  `Annotation.statement` into the multi-megabyte range. SPDX 3.0.1's
  `statement` is a plain `xsd:string` with no spec-mandated limit, so this
  was never a compliance violation, just a real scale gap. `[tool.pitloom.
  provenance] max-source-metadata-bytes` (default `0`, unlimited —
  unchanged behavior for existing users) now caps it: whole `metadata`
  keys are dropped, largest first, never a value cut mid-string, and the
  result carries an explicit `truncated`/`truncatedKeys`/
  `truncatedKeyCount`/`maxMetadataBytes` marker rather than silently
  losing data — see [annotation-mechanism.md](annotation-mechanism.md)'s
  "Size-bounded artifact-metadata preservation" section for the full
  design. `preserve-source-metadata = "never"` (or the size cap set to a
  small budget) both remain valid ways to keep a large model's SBOM small.

## Phase 2 (documented; built after this Annotation work): native-first backfill

Several facts still live only in an Annotation/comment but have a real SPDX
home Pitloom does not yet populate. Build the native construct, then **trim
the corresponding Annotation to the residual**.

- [x] **N1 — Fragment origin** → `SpdxDocument.imports` + `ExternalMap` (per
  source fragment). Residual in Annotation: the unification *criterion* only.
- [x] **N2 — Declared vs. concluded license** → distinct `hasDeclaredLicense`
  (author-stated) / `hasConcludedLicense` (Pitloom-detected). Residual: the
  detection evidence (see [multi-source-conflict.md](multi-source-conflict.md)).
- [x] **N3 — Who/when enriched** → a second `CreationInfo` per enrichment
  run, scoped to *new elements* an enrichment run creates. Residual (every
  field an enrichment run changed, new element or in-place fill alike):
  which field + before/after value + role, via the `provenance/enrichment/1`
  Annotation schema (E1/E2).
- [x] **N4 — External identifiers** (DOI, arXiv, repo / model-card URL) →
  `ExternalIdentifier` / `ExternalRef` on the AI package. Residual: none
  once mapped.
- [x] **N5 — Base-model lineage** (HF `base_model`) → `descendantOf`
  `Relationship`. Residual: raw relation subtype in comment.
- [x] **N6 — Dataset `creator`** → `Agent` + `publishedBy` relationship on the
  dataset package. Residual: none once mapped.

Every use case splits into a **native part** (Phase 2) and an **Annotation
part** (the mechanism above); e.g. G2 license = N2 relationships + Annotation
evidence, A1 unification = N1 `imports` + Annotation criterion.

All six items are complete, PR history, release readiness, and the
rationale behind each item's scope (especially N3's new-elements-only
limit) are in
[phase2-native-backfill-handover.md](phase2-native-backfill-handover.md) --
this is only the residual-vs-native checklist, not the status record.
