---
Created: 2026-09-17
Last-Modified: 2026-10-07
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# G7 SBOM for AI field coverage (1.0 headline)

See also: [roadmap.md](roadmap.md) (1.0 target -- this is 1.0's headline
item), [minimum-elements.md](../../skills/sbom-enrich/references/minimum-elements.md)
(the G7 checklist this file works against), [loom-sdk-and-notebooks.md](sbom-fragments/loom-sdk-and-notebooks.md)
(the SDK expansion this depends on).

Split out of `roadmap.md` (2026-09-17) once this item's detail grew
past a summary.

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

- **`DatasetMetadata.license`** -- field exists on the dataclass,
  populated by extractors, never read by `dataset.py`'s assembler. Same
  shape as the AI-package gaps below: the data already exists, nothing
  consumes it.
- **`ai_AIPackage.verifiedUsing`** (model file hash) -- the model file
  is already SHA-256-hashed elsewhere in the same pipeline for its
  `software_File` element; never copied onto the `ai_AIPackage` element
  itself. Reuse the existing hash, don't recompute it.
- **Model producer** -- no field on `AiModelMetadata` yet. In scope for
  core *only* via a structured source (Hugging Face Hub API's own
  author/org field, the same "trust the source's own structured data"
  principle `_apply_originator` already uses for PyPI-resolved
  dependencies) -- never via free-text parsing of an arbitrary string,
  which is the agent-Skill's job per the scope split above. Per-format
  structured sources already read but kept only in `properties`: ONNX's
  standard `model_author` metadata property, PT2 `extra/author`.
- **Parameter count** -- no dataclass field yet. Several formats
  (GGUF, Safetensors, HF `config.json`) already expose this in their
  own metadata (`raw_metadata`/`properties`) without a dedicated
  Pitloom field promoting it -- check each format's existing extractor
  before assuming new parsing is needed.
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
- **Model identifier** and **Dataset identifier** as a *stable external
  ID* (e.g. a Hugging Face hub model/dataset id) are a **different,
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

## Implementation order (mirrors roadmap.md's 1.0 table)

1. **Mechanical wiring** (`DatasetMetadata.license` -> `dataset.py`;
   reuse the existing model-file hash for `ai_AIPackage.verifiedUsing`)
   -- smallest, zero design risk, code-verified gaps.
2. **Fix the stale `minimum-elements.md` claims** -- prevents the
   agent/Skill from re-asking users about fields core already covers.
   **Done 2026-09-20.** Re-verified against code and a fresh run: besides
   the four rows above (now "conditional" -- emitted only when the
   format/source carries the value), Model properties' architecture,
   Dataset description/identifier/provenance/sensitivity/statistical
   rows were also stale (partly wired via Croissant), and two rows
   over-claimed: Dataset hash (no `verifiedUsing` on
   `dataset_DatasetPackage`) and the CISA "main package never hashed"
   note (it carries the Merkle root).
3. **Model producer + parameter count** (structured sources only) --
   medium, self-contained, no SDK changes needed.
4. **`loom` SDK expansion** for dataset provenance + model
   training-properties -- largest, needs the `loom-sdk-and-notebooks.md`
   design revisited with this G7 framing before implementing.
