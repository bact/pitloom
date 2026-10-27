---
Created: 2026-09-17
Last-Modified: 2026-10-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# G7 SBOM for AI field coverage (1.0 headline)

See also: [roadmap.md](roadmap.md) (1.0 target -- this is 1.0's headline
item), [minimum-elements.md](../../skills/sbom-enrich/references/minimum-elements.md)
(the G7 checklist this file works against), [loom-sdk-and-notebooks.md](sbom-fragments/loom-sdk-and-notebooks.md)
(the SDK expansion this depends on),
[g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md) (what
Pitloom does not claim).

Split out of `roadmap.md` (2026-09-17) once this item's detail grew
past a summary.

> **Gating hazard: closed 2026-10-16.** G7 #3 part 1 landed with the registry
> path keys: `ai_AIPackage.verifiedUsing` carries the model file's SHA-256
> (with its SHA-512 since 2026-10-18) and every model lookup (project, wheel, `loom model`, embed) is gated by it, so a
> retrained model no longer gets the old id (G7 blockers 1 and 2 of
> [id-registry-followups.md](id-registry-followups.md) are closed). See
> [id-registry-path-keys.md](../implementation/id-registry-path-keys.md).

## Regression tests (2026-10-17)

Each field below is held by a table of expected G7 outcomes that the checker
produces from Pitloom's own SBOMs; see
[g7-conformance-tests.md](../implementation/g7-conformance-tests.md). An item
is done when its cells flip from `missing` to `present` in the same change.

## Honesty (decided 2026-10-17)

Coverage never outranks accuracy: a field stays absent when the source does
not state it, and a value keeps the strength its source gave it. What Pitloom
cannot extract or tell apart, the G7 elements SPDX 3.0.1 cannot record, and the
notice for information read but not recordable:
[g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md).

## Scope split (decided 2026-09-17)

Deterministic field population (anything a file format, a structured
API response, or explicit `loom`-decorator/SDK input can supply)
belongs in core CLI/API, since it must stay reproducible per "SBOM
output" in CLAUDE.md. Fuzzy mapping that core can't do deterministically
-- e.g. turning a free-text "producer" string into a properly-
disambiguated SPDX `Person`/`Organization` -- stays the agent/Skill's
job (`sbom-enrich`), not core's. Every item below is scoped to fit the
core/deterministic side of that split; anything needing heuristic
disambiguation is explicitly left to the Skill, not listed as a core
1.0 item.

## Checklist status (re-verified against code, 2026-09-17)

[G7 SBOM for AI 2026](../../skills/sbom-enrich/references/minimum-elements.md#g7-sbom-for-ai-2026-additive----apply-only-when-an-ai_aipackage-is-present)
was built from one verified sample run and is now known to be **stale
in places** -- re-checked against the current assembly code
(`assemble/spdx3/_ai_package.py`, `assemble/spdx3/dataset.py`):

**Already covered, checklist says "gap" -- fix the doc, not the code:**
Model version, Model description, Model external references
(doi/arxiv/url via `_add_external_identifiers_and_refs`), Model license
(via `build_license_elements`, same mechanism as the main package).

**Genuinely absent -- and mostly pure wiring, not new extraction:**

- ~~**`DatasetMetadata.license`**~~ -- done 2026-10-17 (#3 part 2, B1):
  `dataset.py` writes it as `hasDeclaredLicense` (or concluded). Fed by
  three readers since 2026-10-18 (Croissant via `loom.run`, a local dataset
  card, the Hub dataset card of a Hub model's datasets); see
  [dataset-licence-readers.md](dataset-licence-readers.md).
- ~~**`ai_AIPackage.verifiedUsing`** (model file hash)~~ -- done 2026-10-16
  (#3 part 1): the model file's SHA-256 (and, since 2026-10-18, its
  SHA-512), in fresh `Hash` elements, on every route that hashes the file
  (an `enrich` fragment has no `AIPackage`).
- **Model producer** -- done for the structured sources (#6, below):
  `originatedBy` generic `Agent`s (and `suppliedBy`, the repository owner,
  for a Hugging Face model). What remains is the Skill's: a
  person-or-organisation decision, and a producer stated only in prose.
  See [g7-model-producer-parameter-count.md](../implementation/g7-model-producer-parameter-count.md).
- **Parameter count** -- done (#6, below): derived from tensor shapes
  (GGUF, Safetensors, ONNX) or stated by the Hub (`safetensors.total`, else
  `gguf.total`), as an `ai_hyperparameter` entry. Only the Hub states a
  ready count, through those two fields; `config.json` has none. What
  remains is a count stated only in prose, and the formats without a cheap
  source (PT2, PyTorch classic, Keras, HDF5, NumPy, fastText, CRFsuite). See
  the same document.
- **Dataset provenance** (collection method, origin) and **Model
  training properties** (pre-training vs. fine-tune vs. RLHF, etc.) --
  the one pair of genuinely new capture surfaces, not wiring fixes.
  Deterministic and in-scope when the *user* declares it explicitly in
  their own training/data-prep code via an expanded `loom`
  decorator/SDK (a fluent `add_dataset` builder, a training-properties
  parameter) -- this is the concrete shape of "gather more data from
  source code level" the SDK expansion should target. Design already
  sketched (unbuilt) in
  [loom-sdk-and-notebooks.md](sbom-fragments/loom-sdk-and-notebooks.md);
  needs revisiting with this G7 framing specifically, not just the
  original notebook-ergonomics framing it was written for.
- **Model identifier** and **Dataset identifier**: done 2026-10-17 (B2) as
  `software_packageUrl` (`pkg:huggingface`, `pkg:generic`); see
  [g7-conformance-tests.md](../implementation/g7-conformance-tests.md). As
  scoped: a *stable external
  ID* (e.g. a Hugging Face hub model/dataset id) is a **different,
  smaller** problem than the existing
  [AI model id stability](roadmap.md#to-design)
  item -- that item is about Loom's own ID-registry auto-harvest
  reliability; this is just "surface an already-known hub id as an
  `ExternalIdentifier`" when the model/dataset came from a hub source
  that provides one. Don't conflate the two when scoping.

**Explicitly not core's job for 1.0** (leave to `sbom-enrich`): Model
properties needing prose inference (bias/limitation detail beyond what
`AiModelUsage` already carries), Dataset statistical properties,
Dataset sensitivity, and anything in G7's System/Infrastructure/
Security/KPI clusters -- all either need human judgement or aren't
derivable from repo content alone, matching the checklist's own
"not automatable" calls.

## Implementation order (numbered as in roadmap.md)

The numbers are the 1.0 table's, the ones `roadmap.md` and the "G7 #N"
references use: **#3** mechanical wiring, **#4** stale claims (done), **#6**
model producer and parameter count (done), **#7** `loom` SDK expansion.
(The 1.0 table's #1, #2 and #5 are not G7 field items.)

- **#3 Mechanical wiring**, in two parts. **Part 1 done 2026-10-16**:
  `ai_AIPackage.verifiedUsing` plus gated lookups (with the registry path
  keys). **Part 2 done 2026-10-17** (B1): `DatasetMetadata.license` -> a
  `hasDeclaredLicense` Relationship; an expression, a URL and free text are
  kept as the model's are. The three readers of
  [dataset-licence-readers.md](dataset-licence-readers.md) feed it.
- **#4 Fix the stale `minimum-elements.md` claims** -- prevents the
  agent/Skill from re-asking users about fields core already covers.
  **Done 2026-09-20.** Re-verified against code and a fresh run: besides
  the four rows above (now "conditional" -- emitted only when the
  format/source carries the value), Model properties' architecture,
  Dataset description/identifier/provenance/sensitivity/statistical
  rows were also stale (partly wired via Croissant), and two rows
  over-claimed: Dataset hash (no `verifiedUsing` on
  `dataset_DatasetPackage`) and the CISA "main package never hashed"
  note (it carries the Merkle root).
- **#6 Model producer + parameter count** (structured sources only) --
  **Done 2026-10-15, PR #306.** `originatedBy` Agents and the `parameters`
  `ai_hyperparameter` entry; the #292 `originatedBy`-vs-`suppliedBy`
  question is decided: `originatedBy` for every route, plus `suppliedBy`
  (the repository owner) on the Hugging Face route only. See
  [g7-model-producer-parameter-count.md](../implementation/g7-model-producer-parameter-count.md).
- **#7 `loom` SDK expansion** for dataset provenance + model
  training-properties -- largest, needs the `loom-sdk-and-notebooks.md`
  design revisited with this G7 framing before implementing; that revision
  is [loom-sdk-expansion.md](loom-sdk-expansion.md) (unbuilt). Also from #6:
  originators and a parameter count for a `loom.run` model (the structured
  readers of #6 cover only a model file or a Hub model).

## Follow-ups from #6

Left open by the model producer and parameter count work (PR #306; its
decisions:
[g7-model-producer-parameter-count.md](../implementation/g7-model-producer-parameter-count.md)).

- `loom` SDK: originators and a count for a `loom.run` model (under #7,
  above). The Hugging Face identifier and PURL: done as
  `software_packageUrl` (the "Model identifier" item above).
- `loom model` identity is the model's internal name and version, so two
  files with the same graph name share a document namespace. Fixed in
  #353: a generic `Agent`'s id carries its name, so two
  people no longer fold by a counter id on `loom merge`. The `ai_AIPackage`
  itself collided before #6; that belongs with the registry v3 / identity
  follow-ups.
- Dataset creators map to `publishedBy`, model producers to `originatedBy`:
  a divergence that predates #6; decide whether it is intended.
- GGUF `general.quantized_by` (who produced the quantised file; the G7
  producer definition names fine-tuning companies) as a candidate
  originator, and `general.base_model.N.*` (base-model lineage, which the
  Hub route already gives as `descendantOf`).
- The bact G7 mapping names `context_length`; Pitloom emits source-native
  names (`llama.context_length`).
- A count for the silent formats: PT2 and the PyTorch pickle once a
  metadata reader can supply shapes
  ([model-metadata-readers.md](model-metadata-readers.md)); Keras and HDF5
  if weight shapes are read.
- `Person` or `Organization` for a model producer: from a Hub organisation
  or user lookup (one extra request per model), or the Skill's upgrade path
  (a fragment adds the typed agent; the generic `Agent` stays). See
  [author-entity-recognition.md](author-entity-recognition.md).
- Same-name Agents stay apart: a creator of type `agent` keeps its own
  element, a model's originator is a second, a main-package author `Person`
  another. A dataset creator and a model's originator of one name are one
  generic `Agent` (#353); the other kinds stay apart on
  purpose (their class differs, or they are the SBOM's own creators). One
  identity across them needs a rule for which element wins (pinned by tests).
- ONNX: subgraph attributes with no `type` set (very old files) are not
  walked, `training_info` graphs are not counted, and a `model_author` that
  is not valid UTF-8 yields no originator, silently, as `model_license`
  does.
- `escape_display_controls` is not injective: a name with a control
  character and one with its literal `\uXXXX` text show alike (documented
  for users on the reading-back page; predates #6).
