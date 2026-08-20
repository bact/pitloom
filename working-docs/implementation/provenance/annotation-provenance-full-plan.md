---
Created: 2026-08-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Full plan: Refocus provenance Annotations on non-native, high-signal facts

> Archived copy of the plan originally approved via Claude Code plan mode
> (source: `~/.claude/plans/annotation-statement-should-not-stateful-narwhal.md`,
> a path outside this repo and not guaranteed to exist in a future
> session). Saved here so the full Phase 1 design record travels with the
> repo. Phase 1 (this plan) is **complete and merged** — see
> [`phase2-native-backfill-handover.md`](phase2-native-backfill-handover.md)
> for current status and what to do next. This file is historical
> reference, not a live task list.

## Context

The provenance feature just implemented (branch `provenance-annotation`) emits an
SPDX 3 Core `Annotation` for **every** metadata field on nearly every element,
each carrying a `{source, location, method}` map. Much of that shadows what SPDX
already expresses natively: the license *value* lives in `hasDeclaredLicense`, the
version in `software_packageVersion`, the download URL in
`software_downloadLocation`, dependency edges in `dependsOn` relationships. A
`{"name": {"source": "pyproject.toml"}}` annotation on a package whose `name` is
already the native `Element.name` adds little and bloats the graph.

The user's directive: **the Annotation statement must not try to replace native
SPDX elements/relationships; limit it to things SPDX 3 cannot record natively.**

Key finding from code exploration (two Explore passes, see citations below): SPDX
3.0.1 has **no native field for "how a value was extracted"** — so *every* per-field
source string is technically non-native. A pure "non-native" test therefore keeps
everything. The real filter must be stronger: **non-native AND carrying decision-value
beyond the native value itself.** Two confirmed decisions:

- **Boundary = config-gated.** Default to high-signal-only; a `[tool.pitloom.provenance]`
  flag re-enables exhaustive per-field source annotations.
- **Scope now = doc + generation + aggregation.** Refine the emitter to the boundary,
  implement fragment-unification annotations (that code path exists today), implement
  artifact-metadata preservation for AI models (a generation-time concern, config-gated),
  and write the use-case catalog into working-docs. Enrichment-override annotations are
  captured as design only (the `enrich/` subpackage is unbuilt).

A second Annotation role emerged beyond provenance-of-extraction: **metadata
preservation** — keeping the original artifact metadata (e.g. an AI model's own header)
verbatim, config-gated, precisely when the artifact isn't shipped and can't be
re-extracted later. This complements native encoding rather than replacing it, so it sits
squarely inside the boundary principle.

Symmetrically, several facts currently living only in a comment/Annotation actually **do**
have a native SPDX home that Pitloom does not yet populate (declared-vs-concluded license,
fragment `imports`, external identifiers, enrichment `CreationInfo`). Moving those to
native constructs is a **documented Phase 2** (built after this Annotation work — see the
"Phase 2" section) so we don't forget them and can see, per use case, which half is native
and which half is genuinely Annotation-only.

## Boundary principle (native-first)

1. **Never put a value in an Annotation that has a native SPDX home.** Values go to
   native fields/relationships; the Annotation only ever describes *how the value came
   to be*, never restates it.
2. **Never annotate a native relationship redundantly.** Drop the current annotation on
   the `dependsOn` relationship (`deps.py`, `document.py` deployed path) — the
   relationship *is* the record; extraction-source belongs once on the package, not
   duplicated on its edges.
3. **Emit a field-level Annotation only when it adds signal the native value can't
   convey** (default/minimal mode). Otherwise (full mode) emit all, for exhaustive audit.
4. **Process-level facts that have no native anchor at all** (fragment unification,
   enrichment override) are the highest-value Annotation content and are emitted
   regardless of detail level.

## Native vs. non-native (condensed)

| Provenance fact | Native SPDX home? | Annotation role |
| --- | --- | --- |
| name / version / description / download URL / homepage | Yes (`Element.name`, `software_packageVersion`, `description`, `software_downloadLocation`, `software_homePage`) | none in minimal; source-only in full |
| license *value* | Yes (`hasDeclaredLicense` + `SimpleLicensingText`) | never the value; only "detected vs declared" (G1) |
| dependency edge | Yes (`dependsOn`) | never on the edge; see G3 on the package |
| hashes / files / relationships / PURL / ExternalRef | Yes | never |
| **inferred / detected / AI-generated** qualifier | Partly — see N2 | **G1 — necessary** (assertedness beyond N2) |
| **declared vs. concluded license** (author-stated vs Pitloom-detected) | **Yes, native, but NOT built** — `hasDeclaredLicense` / `hasConcludedLicense` are currently mirrored (`deps.py:246-252`, "no inference yet") | **Phase 2 → N2**; Annotation keeps only the evidence/why |
| **multi-source disagreement / which source won** | Partly (license → N2) | **G2 — necessary on conflict** |
| **declared constraint vs resolved version** | **No** (`software_packageVersion` holds only the resolved value) | **G3 — useful** |
| **sub-file extraction location** (safetensors `__metadata__`, GGUF kv, pt2 `extra/*`) | **No** | **G4 — useful** |
| **DOI / arXiv / repo & model-card URLs** (from HF `extra_data`) | **Yes, native, but NOT built** — `ExternalIdentifier` (doi) / `ExternalRef` | **Phase 2 → N4**; today only in provenance/`extra_data` |
| **element came from fragment document F** | **Yes, native, but NOT built** — `SpdxDocument.imports` + `ExternalMap` (doc-level; flagged unbuilt in `sbom-fragments.md:146,698-701`) | **Phase 2 → N1**; Annotation keeps the *criterion* |
| **why two fragments were unified** (criterion: registry-id / sha256 / structural) | **No** (merged-away ids vanish; `imports` can't say *why*) | **A1 — necessary** |
| **who/when enriched** | **Yes, native, but NOT built** — a second `CreationInfo` per enrichment run | **Phase 2 → N3**; Annotation keeps which-field + before/after |
| **field overridden A→B by enrichment source Y** | **No** (`CreationInfo` is element-level, no before/after) | **E1/E2 — necessary (design only now)** |
| **verbatim original artifact metadata blob** (GGUF kv-store, safetensors `__metadata__`, HF `config.json` + model card) | **No** (native mapping is a lossy subset; `ExternalRef` is only a *pointer* that can dangle) | **P1 — useful; necessary when the artifact is not shipped** |

Citations: native inventory — `document.py:60-97,173-281`, `ai.py:124-357`,
`dataset.py:104-235`, `deps.py:75-347`, `creation_info.py:84-210`. Provenance vocabulary —
`pyproject.py:147-345`, `_huggingface.py:453-768`, `_gguf.py:135-198`,
`_safetensors.py:77-120`, `_pytorch_pt2.py:132-297`, `deps.py:52-54,116,302`,
`document.py:609,646`. Aggregation — `fragments.py:423-464` (`_merge_fragment_set` holds
`remap` + matched criterion, discards both), `ids.py:240-331` (registry overwrites prior
identity). Enrichment — `skills/enrich/SKILL.md:40-60` (`Source: AI agent | Method: inference`
rides only in `comment`), `sbom-enrichment.md:145-169`.

## Use-case catalog (the deliverable the user asked for)

### Generation

- **G1 — Inferred / detected / AI-generated value qualifier — NECESSARY.**
  SPDX stores `software_copyrightText`, the license, `ai_typeOfModel` as bare values with
  no marker of whether they were *read* or *guessed*. Pitloom already computes this
  distinction: `copyright_text = "... | Method: inferred_from_authors"` (`pyproject.py:183`),
  license via `Method: licenseid_detection` (`pyproject.py:285`, `_huggingface.py:485`),
  fastText `type_of_model` inferred from internal args. A compliance auditor **must** know
  an `Apache-2.0` was heuristically detected from a LICENSE file vs. declared by the author.
  SPDX has no assertedness/confidence field → Annotation is the only home.

- **G2 — Multi-source disagreement / selection — NECESSARY on conflict, else useful.**
  The same field can come from several sources with priority resolution (setuptools
  primary/secondary merge; license from `project.license` OR detected LICENSE OR licenseid).
  SPDX records only the winning value — not that alternatives existed, which won, or whether
  they agreed. A declared-vs-detected license *disagreement* is a compliance red flag with
  no native representation.

- **G3 — Declared constraint vs. resolved version — USEFUL.**
  `dependencies` provenance keeps the PEP 508 constraint (`requests>=2.28.0`, `deps.py:302`)
  and a build-time-resolution note (`deps.py:52`). SPDX stores only the resolved
  `software_packageVersion=2.28.1`; there is no native field for the original constraint or
  the fact resolution happened from the build environment. Needed to reproduce/re-resolve or
  analyze version drift; the SBOM should be self-contained rather than sending readers back to
  `pyproject.toml`.

- **G4 — Sub-file extraction location for opaque binary formats — USEFUL.**
  For AI model files, provenance pinpoints the internal origin: safetensors `__metadata__`,
  GGUF `general.architecture`, ONNX `producer_name`, pt2 `extra/license`. SPDX stores the value
  (`ai_typeOfModel`) but not that it came from a specific byte-region vs. inference. Valuable for
  extraction debugging, reproducibility, and trust in messy AI formats where extractors can
  disagree.

- **(Not a use case) Trivial 1:1 field source** ("name came from `pyproject.toml project.name`").
  Low signal; the value is already the native `Element.name`. Suppressed in minimal mode; available
  in full mode.

### Aggregation (fragment merge / unification — implemented today)

- **A1 — Unification rationale — NECESSARY.**
  `_merge_fragment_set` (`fragments.py:433-464`) unifies two elements when their `spdxId` matches
  a registry entry, their SHA-256 `verifiedUsing` matches, or (Agent/Tool) they are structurally
  equal — and it holds the exact `remap` (dropped-id → survivor-id) plus which branch fired. All of
  it is discarded; the output shows one element with no trace. For a merged AI-pipeline SBOM the
  central question — "is this the same model file the training script produced *and* the wheel
  packaged, matched by content hash, or merely by a name guess?" — is unanswerable from output. The
  nearest native anchor (`SpdxDocument.imports`/`ExternalMap`) is document-level and unbuilt; it can't
  express per-element "these N ids were unified by criterion C." An element-level process Annotation on
  the survivor is the right home.

- **A2 — Superseded identity across builds — USEFUL.**
  On changed content, `register_file` mints a new `spdxId` and discards the old (`ids.py:300`); the
  "identity superseded old id X (hash H1)" fact survives only as a transient log line. SPDX has no
  native supersedes/replaces link. Cross-build (not within one SBOM), so lower priority — documented,
  not built now.

### Enrichment (design only — `enrich/` subpackage unbuilt)

- **E1 — Override lineage (field changed A→B by source Y) — NECESSARY.**
  Enrichers update fields in-place; the current `{field:{source,method}}` schema records the winning
  source but not the prior value, the fact of an override, or a per-field enrichment time. SPDX's
  element-level `CreationInfo` can say "an enrichment run happened" but not "it changed *this field*
  from A to B." Required to audit any enrichment that overwrites authoritative-looking values.

- **E2 — AI-inferred vs. extracted marker — NECESSARY (flagship).**
  The single most important trust fact — `Source: AI agent | Method: inference`
  (`skills/enrich/SKILL.md`) — today rides only in a free-text `comment` and survives fragment merge
  only incidentally (comments get concatenated, `fragments.py` `_merge_comment`). It deserves a
  structured, first-class home so a consumer can reliably separate LLM-inferred assertions from
  extracted facts. Structurally identical to G1; specced now, wired when the enricher lands.

### Artifact-metadata preservation (fidelity / archival)

Distinct from the G/A/E provenance-of-*extraction* cases above: this preserves the **original source
metadata itself**, verbatim, regardless of what Pitloom mapped. Complements native encoding — the
relevant subset is still emitted as SPDX classes/properties/relationships — rather than replacing it.

- **P1 — Verbatim original artifact metadata blob — USEFUL; NECESSARY when the artifact is not shipped.**
  Pitloom's native mapping is deliberately lossy and selective: it lifts a chosen subset of a model's
  GGUF kv-store / safetensors `__metadata__` / ONNX `metadata_props` / HF `config.json` + model-card
  YAML into `ai_typeOfModel`, `ai_hyperparameter`, `ai_domain`, etc. (`ai.py:124-200`), normalizing or
  dropping everything else. When the artifact does **not** travel with the SBOM — a remote HF model
  referenced by URL, a large weights file excluded from the wheel, a model pulled at deploy time — the
  original metadata can never be re-extracted from the artifact, and an SPDX `ExternalRef` (used today
  for the Croissant URL, `dataset.py:156`) is only a *pointer* that can dangle. Embedding the original
  metadata as-is (in the model's own encoding) in a config-gated Annotation makes the SBOM a
  self-contained, durable record. No native SPDX construct can hold an arbitrary vendor metadata blob.
  Config-gated because blobs can be large and are redundant when the artifact is bundled and
  re-extractable. Precedent for the extractors already retaining most of this: `properties` /
  `extra_data` maps in `_gguf.py`, `_safetensors.py`, `_huggingface.py` — see step below on retaining
  the *complete* raw map.

## Phase 2 (documented now, built after the Annotation work): native-first backfill

Several facts above have a real SPDX 3 home that Pitloom does not yet populate — it records
them only in a comment/Annotation, or mirrors/normalizes them away. The native-first principle
says the *fact/value* belongs in the native construct; the Annotation should then shrink to only
the non-native residual. Building these is deferred to a next phase, but documenting the target
now keeps the two halves coherent and prevents the Annotation from ossifying as the permanent home
for things that ought to be native. **For each item: build the native construct, then trim the
corresponding Annotation content.**

| # | Fact | Native construct to build | Currently | Residual left to Annotation |
| --- | --- | --- | --- | --- |
| **N1** | Element originates from fragment document F | `SpdxDocument.imports` + `ExternalMap` (one per source fragment) | Fragment origin discarded at merge (`fragments.py:461-464`); `imports` unbuilt (`sbom-fragments.md:146,698-701`) | Unification *criterion* only (registry-id/sha256/structural) — A1 |
| **N2** | Declared vs. concluded license | Distinct `hasDeclaredLicense` (author-stated) and `hasConcludedLicense` (Pitloom-detected from LICENSE/licenseid evidence) | Concluded is set equal to declared, "no inference yet" (`deps.py:246-252`) | The *evidence* (which file/heuristic) behind the concluded license — G1/G2 |
| **N3** | Who/when enriched | A second `CreationInfo` (createdBy = enricher agent, createdUsing = enricher tool, created = enrichment time) attached to enriched elements | Enrichers mutate in-place under the original `CreationInfo`; agent path only tags a comment | Which field + before/after value + inferred-marker — E1/E2 |
| **N4** | External identifiers (DOI, arXiv, repo URL, model-card URL) | `ExternalIdentifier` (type `doi`, …) / `ExternalRef` on the AI package | Captured into `extra_data`/provenance only (`_huggingface.py:710-764`) | none once mapped (fully native) |
| **N5** | Base-model lineage (HF `base_model` / `base_model_relation`) | A `Relationship` to a base-model element if a suitable `relationshipType` exists, else `ExternalRef` | In `extra_data` only | none once mapped, or the raw relation string if no native type fits |
| **N6** | Dataset `creator` | `Agent` + a creation/attribution relationship on the dataset package | Extracted (`_croissant.py:208`) but not wired onto the `dataset_DatasetPackage` | none once mapped |

Relationship to Phase 1 (this plan): every use case splits into a **native part** (Phase 2 above)
and an **Annotation part** (this plan). E.g. G2 license = N2 native relationships + Annotation
evidence; A1 unification = N1 native `imports` + Annotation criterion; E1/E2 enrichment = N3 native
`CreationInfo` + Annotation before/after. Phase 1 deliberately does **not** pre-empt these — where a
native home is coming in Phase 2, the Phase-1 Annotation still carries the whole fact for now and is
trimmed to the residual when N-x lands. Track each N-item as a checklist in
`working-docs/implementation/annotation-provenance.md` so the trim is not forgotten.

## Design changes

### Config (`[tool.pitloom.provenance]`)

Add two keys alongside the existing `format` / `schema`:

- `detail = "minimal" | "full"` — default `"minimal"`.
  - `minimal`: field Annotations only for G1–G4 signals; process Annotations (A1) always.
  - `full`: also emit the plain per-field source map (current behavior) for exhaustive audit.
- `preserve_source_metadata = "auto" | "always" | "never"` — default `"auto"` (P1).
  - `auto`: embed the verbatim artifact-metadata blob **only when the artifact is not shipped**
    with the distribution (remote HF model, model referenced by URL, weights excluded from the
    wheel) — i.e. exactly when it can't be re-extracted later. Skip it when the artifact is
    bundled (re-extractable, blob would be redundant).
    Decidable from data Pitloom already has: an AI model with `format_info.file_path_relative`
    present in the packaged file set is "shipped"; a HF/URL-sourced model with no local file is not.
  - `always` / `never`: explicit overrides.

Parsed and validated in `src/pitloom/core/config.py` next to `_read_provenance_settings`
(new `PitloomConfig.provenance_detail` and `provenance_preserve_source_metadata` fields; mirror the
`_VALID_PROVENANCE_FORMATS` literal-set + fail-fast pattern already there).

### Statement schema

- **Field-level (extraction):** keep the `pitloom/1` envelope
  `{schema, fields: {field: {source, location, method, note}}}`. No shape change; minimal mode
  simply *filters* which fields appear (see high-signal test below). Formalize the `method`
  vocabulary already produced by extractors: `dynamic_extraction`, `licenseid_detection`,
  `inferred_from_authors`, `inspect_caller`, `file_directive`, `attr_directive`, plus the
  enrichment-reserved `inference`.
- **Process-level (new):** a distinct envelope, e.g.
  `{schema: "https://pitloom.dev/provenance/unification/1", event: "unification",
  criterion: "registry-id"|"sha256"|"structural", unified: [dropped ids...], fragments: [paths...]}`,
  carried by the same `Annotation` machinery (annotationType `other`, contentType
  `application/json`) via a new `build_unification_annotation()` in
  `src/pitloom/assemble/spdx3/provenance.py`. Reuse `generate_spdx_id("Annotation", ...)`,
  `sort_keys=True` for byte-stability, and sorted id/fragment lists for determinism.
- **Preservation blob (new, P1):** envelope
  `{schema: "https://pitloom.dev/provenance/artifact-metadata/1", format: "gguf-kv"|
  "safetensors-metadata"|"hf-config"|"onnx-metadata"|..., metadata: <original JSON>}`, on the
  `ai_AIPackage`, via a new `build_source_metadata_annotation()`. `contentType = "application/json"`
  (the raw map is re-encoded as JSON; genuinely-binary values base64'd). Emitted only when the P1
  gate says so. Deterministic via `sort_keys=True`.

### High-signal test (minimal mode) — **denylist, as built**

> **Decision (2026-07-21):** implemented as a *denylist*, not the allowlist this
> section originally proposed. For a provenance feature the failure direction
> matters more than precision: an allowlist ("keep only recognized high-signal
> patterns") fails **closed** — a new extractor emitting genuinely useful
> non-native provenance is silently dropped until someone extends the allowlist.
> A denylist fails **open** — new sources are kept by default; you only lose the
> provenance if you *explicitly* mark a source transparent. Fail-open is correct
> for provenance (never silently lose it), and the denylist is also lower
> maintenance: transparent manifests are few and stable (pyproject.toml,
> hatchling build backend, setup.cfg/py, wheel metadata, Hugging Face Hub),
> whereas high-signal patterns proliferate. Denylist chosen.

`_is_high_signal(entry)` in `provenance.py`: an entry is **low-signal (dropped in
minimal)** only when it was read *verbatim* from a transparent, re-readable
manifest (`_TRANSPARENT_SOURCES`) with **no** extraction `method`. Everything
else is kept — any recorded `method` (G1 inference/detection/dynamic/caller/
directive), a non-manifest `source` (pipdeptree scan, a binary artifact's
internal key G4, a synthesized/phantom package, an enrichment), and the raw
`declared_constraint` (G3, parsed as a note with no manifest source). Applied as
a filter in `emit_provenance` when `detail == "minimal"`. See §10 of the
implementation doc for the as-built write-up.

### Emitter wiring

- Thread `provenance_detail` through `emit_provenance` (`provenance.py`) and the assemble call sites
  exactly as `provenance_format`/`encoder` are already threaded (`document.py`, `ai.py`, `dataset.py`,
  `deps.py`, `assemble/__init__.py`, `plugins/hatch.py`, `loom.py`).
- **Remove** the redundant relationship annotations: the `emit_provenance(subject=dep_rel, ...)` calls
  in `deps.py add_dependencies` and `document.py build_deployed` (dependency-edge provenance now lives
  only on the package).
- **Aggregation:** in `fragments.py _merge_fragment_set`, when a unification fires (the `by_id`,
  `by_hash`, `structural_dup` branches), accumulate `(survivor_id, criterion, dropped_id,
  fragment_path)` and after the merge emit one `build_unification_annotation` per survivor onto the
  exporter. Needs the fragment file path already threaded into the merge loop (`merge_fragments`,
  ~`fragments.py:575-607`).
- **Preservation (P1):** ensure the AI extractors retain the **complete** raw metadata map (they
  already retain most via `properties`/`extra_data`; add a `format_info.raw_metadata` capture where
  incomplete). In `ai.py add_ai_models`, after the `ai_AIPackage` is built, evaluate the P1 gate
  (`preserve_source_metadata` × whether the model file is in `file_spdx_ids`) and, if preserving, emit
  `build_source_metadata_annotation`. Thread `provenance_preserve_source_metadata` alongside
  `provenance_detail`.

### Enrichment (design only)

Document in the plan/design docs the process envelope for E1/E2, e.g.
`{schema: "https://pitloom.dev/provenance/enrichment/1", event: "enrichment", field, previous_value,
source, method}` on the enriched element, plus who/when via the annotation's own `CreationInfo`. Note
the fragment-merge caveat: a fragment can only *fill* an empty scalar today (canonical wins on
conflict, `fragments.py`), so structured override needs the enricher to run in-process (the designed
`enrich/` subpackage) rather than via fragment. No code now.

## Files to modify (Phase 1 — historical, already applied)

- `src/pitloom/assemble/spdx3/provenance.py` — `_is_high_signal`, minimal-mode filter in the
  `pitloom/1` encoder, new `build_unification_annotation`, `build_source_metadata_annotation`,
  `detail` param on `emit_provenance`.
- `src/pitloom/core/config.py` — `provenance_detail` + `provenance_preserve_source_metadata` fields
  + validation.
- `src/pitloom/assemble/spdx3/fragments.py` — record unification events in `_merge_fragment_set`,
  emit annotations; thread fragment path.
- `src/pitloom/assemble/spdx3/ai.py` — P1 gate + preservation-blob emission; possibly
  `src/pitloom/core/ai_metadata.py` + AI extractors (`_gguf.py`, `_safetensors.py`, `_onnx.py`,
  `_huggingface.py`) to retain the complete raw metadata map.
- `src/pitloom/assemble/spdx3/{document,dataset,deps}.py`, `assemble/__init__.py`,
  `plugins/hatch.py`, `loom.py` — thread `provenance_detail` (+ preserve flag where AI models flow);
  drop the two relationship annotations.
- Docs: `working-docs/implementation/annotation-provenance.md` (boundary + use cases + `detail` +
  the **Phase 2 native-backfill checklist N1–N6** with per-item "trim the Annotation to residual"
  notes), `working-docs/design/metadata-provenance.md` (native-first principle), `CHANGELOG.md`.
- Tests: extend `tests/test_annotation_provenance.py` (high-signal filter, minimal vs full,
  unification + preservation annotation shapes + determinism); update `tests/test_provenance.py`,
  `tests/test_spdx3_compliance.py` for minimal-mode default (fewer annotations); add a
  `tests/test_fragments.py` case asserting a unification annotation on a hash-merged survivor; add an
  AI-model case asserting P1 `auto` embeds the raw blob for a URL/HF model but not a bundled one.
  (All of these test files have since moved under `tests/assemble/` or
  `tests/core/` and split further -- see `cli-test-coverage-roadmap.md`
  for current paths. Not updated inline above since this section is an
  archived plan snapshot, not a living reference.)

## Verification (Phase 1 — historical)

- `python3 -m pytest tests/ -q` (pyenv `pitloom310`); mypy + ruff clean.
- Generate an SBOM at default `detail="minimal"`: assert annotations exist ONLY for inferred/detected
  fields (e.g. `copyright_text`, a detected license) and none for trivially-native fields (name,
  version); assert no annotation on any `dependsOn` relationship.
- Generate with `detail="full"`: assert the per-field source map returns for all fields.
- Generate a HF/URL-sourced AI-model SBOM at `preserve_source_metadata="auto"`: assert an
  `artifact-metadata/1` Annotation embeds the verbatim source map; generate a bundled-model SBOM and
  assert no such blob (re-extractable); confirm `always`/`never` override both.
- Build a two-fragment scenario where a model file unifies by SHA-256; assert one
  `unification` Annotation on the survivor naming the criterion and the dropped id, and that output is
  byte-identical across two runs.
- Confirm the `enrich` skill's `Source: AI agent | Method: inference` marker is documented as the
  E2 target shape (no code change expected to pass).

## Outcome

Phase 1 shipped as PR [#102](https://github.com/bact/pitloom/pull/102), merged to `main`.
Phase 2 (the N1-N6 table above) is tracked separately — see
[`phase2-native-backfill-handover.md`](phase2-native-backfill-handover.md) for
current status (N1, N2, N4, N5, N6 merged via PRs #108, #105, #106, #109, #107;
N3 blocked on `enrich/` subpackage) and next steps.
