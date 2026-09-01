---
Created: 2026-02-22
Last-Modified: 2026-09-01
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM enrichment and AI SBOMs

This document outlines strategies for enriching SBOMs with additional metadata,
focusing on AI model and dataset information in Pitloom.

## Current implementation

Pitloom maps extracted model metadata to SPDX 3 native AI profile fields on
`ai_AIPackage`. The mapping is handled in `pitloom.assemble.spdx3.ai`:

| `AiModelMetadata` field | SPDX 3 field |
| :---- | :---- |
| `name` | `name` |
| `version` | `software_packageVersion` |
| `description` | `description` |
| `type_of_model` | `ai_typeOfModel` |
| `hyperparameters` | `ai_hyperparameter` (list of `DictionaryEntry`) |
| `inputs` / `outputs` | `ai_informationAboutApplication` (JSON string) |
| `format_version` | not yet mapped -- candidate: `comment` or custom `ExternalRef` |
| `framework` | not yet mapped -- candidate: `ai_informationAboutApplication` or `comment` |
| `framework_version` | not yet mapped -- candidate: `comment` or `ExternalRef` |
| `properties` | not yet mapped (stored in `AiModelMetadata.properties`, not emitted to SPDX) |
| `provenance` | `comment` |

`ai_AIPackage` elements are linked to the main Python package via an SPDX
`contains` relationship.

## Dataset-to-model relationship linking

**Shipped.** The AI model itself and its associated training/evaluation
datasets are both documented, linked via SPDX 3's dedicated relationship
types between `ai_AIPackage` and `dataset_DatasetPackage`:

| SPDX 3 Relationship type | Meaning | Native in SPDX 3.0.1? |
| :---- | :---- | :---- |
| `trainedOn` | Primary dataset used to train the model | Yes |
| `testedOn` | Dataset(s) used to evaluate the trained model | Yes |
| `finetunedOn` | Dataset used for fine-tuning a pre-trained model | No -- `other` + comment |
| `validatedOn` | Dataset used for validation during training | No -- `other` + comment |
| `pretrainedOn` | Dataset used to pre-train a foundation model | No -- `other` + comment |

### Implementation

- `AiModelMetadata.datasets` (`pitloom.core.ai_metadata`) is a
  `list[DatasetReference]` (`pitloom.core.dataset_metadata`) carrying each
  dataset's role, name, URI, and license -- populated today by the
  README/model-card frontmatter enricher (`enrich/readme.py`) and the
  Hugging Face extractor (`extract/_huggingface.py`).
- `add_datasets_for_model()` (`src/pitloom/assemble/spdx3/dataset.py`)
  creates the `dataset_DatasetPackage` element and emits the relationship,
  mapping each role to its native SPDX 3.0.1 `RelationshipType` where one
  exists, falling back to `RelationshipType.other` plus an explanatory
  comment for the three roles SPDX 3.0.1 doesn't have a term for yet
  (`_role_to_rel()` in the same module).
- Called from `pitloom.assemble.spdx3.ai` and `_document_model.py`, which
  also append `ProfileIdentifierType.dataset` to `profileConformance`
  whenever at least one dataset element is present
  (`pitloom.assemble.spdx3.document`).

### Dataset metadata sources

When a dataset is available on a recognised hub, its metadata can be retrieved
in machine-readable Croissant format (JSON-LD extension of `schema.org/Dataset`),
adopted by Hugging Face, Kaggle, and OpenML.
<https://github.com/mlcommons/croissant>

To avoid SBOM bloat, only top-level identity fields (name, license, task) should
be inlined into the `dataset_DatasetPackage` element; exhaustive provenance can
be linked via an `ExternalRef` pointing to the Croissant document URL.

## Planned: SBOM enrichment from external sources

Model formats that carry little embedded metadata (PyTorch classic, Scikit-learn
pickles, some HDF5 files) can be enriched with information from external sources.
This is analogous to what
[AIMMX](https://github.com/IBM/AIMMX) does at the repository level and what
[Parlay](https://github.com/snyk/parlay) does by querying third-party services
such as OpenSSF Scorecard and package registries.

### Enrichment data sources

| Source | What it provides | Network required | Default | Status |
| :----- | :--------------- | :--------------- | :------ | :----- |
| Repository README / model card | License, dataset references (YAML frontmatter only -- not prose; see below) | No (local file) | **Disabled** (opt-in) | **Shipped** (`enrich/readme.py`) |
| Hugging Face Hub metadata | Architecture, tags, license, dataset links, paper references | Yes | User opt-in | Not started |
| OpenSSF Scorecard | Supply chain security posture of the upstream project | Yes | User opt-in | Not started |
| Parlay package enrichment | Package ecosystem metadata (description, homepage, license) | Yes | User opt-in | Not started |
| PyPI / conda metadata | Version history, maintainers, download stats | Yes | User opt-in | Not started |

Every source defaults **off**, including the local, no-network README
pass -- enrichment as a whole is still immature (one source, frontmatter
only), so nothing runs unless explicitly turned on, project-wide via
config or per-run via a flag/parameter. (OpenSSF Scorecard/Parlay were
originally sketched as "enabled by default, low cost" before this
decision; that default no longer applies once any of them actually ship.)

### Enable/disable per source

Because some enrichment functions require a network connection or may raise
licensing questions (e.g., pulling data from a hub that has terms of use),
Pitloom allows users to enable or disable each source independently in
`pyproject.toml`:

```toml
[tool.pitloom]
enrich = false          # README / model card -- off by default, opt in explicitly
```

Only this one flat toggle exists today -- per-source enable/disable for
`openssf_scorecard`/`huggingface`/`pypi` is added when their enrichers
actually land, not pre-declared ahead of them (same discipline
`[tool.pitloom.provenance]`'s keys followed: one key per shipped
capability, not a speculative full set up front).

### Surfaces (shipped)

The mechanical enrichment engine (`run_enrichers()`) is exposed the same
way across every generation path -- no surface has its own bespoke
on/off model:

| Surface | How to opt in |
| :------ | :------------ |
| CLI -- `loom model`/`loom project`/`loom generate` | `--enrich` (or `--no-enrich` to force off despite config) |
| CLI -- standalone `loom enrich <model-file>` | Runs by default (invoking the command is itself the opt-in); `--no-enrich` writes an empty fragment instead. Writes a standalone fragment (no `SpdxDocument`/`software_Sbom`/`ai_AIPackage`) for merging into a base SBOM via `[tool.pitloom.fragment]` |
| Python API -- `generate_model_sbom()`/`generate_project_sbom()`/`generate()` | `enrich=True`/`enrich=False` keyword (`None` defers to config) |
| Python API -- `enrich_model()` | Same as `loom enrich`: runs by default, `enrich=False` suppresses, returns the fragment JSON string |
| Hatchling build hook | Inherits the project's `[tool.pitloom] enrich` automatically -- no separate hook-level key, per the same "one config surface" rule the hook already enforces for creator/tool/fragment settings |
| GitHub Action | `enrich: "true"`/`"false"` input, mapped to `--enrich`/`--no-enrich`; empty (default) defers to config |

**Design invariant:** `loom generate --enrich <target>` and (`loom
generate --no-enrich <target>` + `loom enrich <target>` + `loom merge`)
produce equivalent enrichment evidence *for a single-model-file target*
-- both paths share the same deterministic identity computation for the
referenced `ai_AIPackage` (`_ai_model_identity()` in `document.py`).
Verified by `tests/core/generator/test_generator_misc.py::test_enrich_then_merge_matches_one_shot_enrich`.

**This does NOT hold for a project directory target without extra
care.** `loom project <dir>`/`loom generate <dir>` assign a model's
`ai_AIPackage` a *project*-derived id (from the project's own name/
version/dependencies/Merkle root), not the model-only id `loom enrich`
computes by default -- a genuinely different identity scheme, not just a
different value. A fragment built with the wrong one references an id
that doesn't exist in the merged result: its dataset relationship and
enrichment Annotation become silently dangling references, with no
warning from `merge_fragments()` (found during independent review; see
git history for the fix). `merge_fragments()` now detects this class of
bug generically (any dangling reference after a merge fails the merge,
see `_raise_on_dangling_references()` in
`src/pitloom/assemble/spdx3/fragments.py`), but getting the identity
right in the first place is still the correct fix, not something to
merge past. **Always pass `loom enrich --project-dir
<dir>` (or `enrich_model(..., project_target=<dir>)`)** when the
fragment is meant to merge into a project-level base document -- this
resolves the project's own identity (see `_project_doc_identity()` in
`assemble/_model_generator.py`) so the two agree. Covered by
`tests/core/generator/test_generator_model_fragments.py::test_enrich_model_project_target_merges_correctly_end_to_end`
(the real regression test -- verifies attachment survives an actual
merge, not just matching id strings) and
`test_enrich_model_without_project_target_mismatches_project_level_id`
(negative-space guard that omitting it really does mismatch).

Similarly, a project using `--registry`/`IdRegistry` to pin a stable
`ai_AIPackage` id needs `loom enrich --registry <file>` (or
`enrich_model(..., registry=...)`) too, for the same reason.

**Known limitation, not yet fixed:** two AI models in the same project
that share an identical resolved identity -- no embedded `name` *and*
the same detected format (e.g. two nameless `.safetensors` files) --
get the same predicted `ai_AIPackage` id from independent `loom enrich`
runs, because `generate_spdx_id()`'s per-prefix counter is
order-of-calls-dependent within a single real build and a standalone
one-model-at-a-time fragment can't know its position in that sequence.
Give ambiguous models a `name` in their own metadata to disambiguate, or
avoid enriching more than one such model independently until this is
addressed.

**Known limitation, by design, not planned to change:** two
*independently-authored* fragments describing the same real-world
dataset -- e.g. `loom enrich`'s deterministic fragment and the
`sbom-enrich` Skill's own hand-drafted agent fragment (see below) both
mentioning "tiny-imagenet" -- produce **two separate
`dataset_DatasetPackage` elements** in the merged output, not one,
unless they happen to share a `spdxId` or a SHA-256 `verifiedUsing`
hash (neither does today -- a dataset reference has no local file to
hash, and each fragment mints its own id in its own namespace).
`merge_fragments()`'s unification policy deliberately never matches by
`type` + `name` alone (see its module docstring in `fragments.py`) --
adding a name-based special case just for datasets would undermine that
policy's whole point (avoiding false-positive merges of genuinely
different same-named things) for the sake of one workflow. Confirmed by
direct repro (two fragments, one hand-authored matching the
`sbom-enrich` Skill's own example shape, merged into a project-level
base document -- two `dataset_DatasetPackage` nodes both named
`tiny-imagenet` survive). The mitigation is process-level, not
code-level: `skills/sbom-enrich/SKILL.md`'s step 3 already instructs the
agent to run the deterministic pass first and only add fields for gaps
it left untouched, precisely so the agent doesn't independently
re-describe a dataset `loom enrich` already found. Followed correctly,
this scenario doesn't arise; a code-level guard isn't planned given the
conflict with the existing no-name-matching invariant.

## AI-agent enrichment (skill / plugin)

An AI agent (e.g. Claude Code, or another Agent-SDK-based runtime) is
itself an enrichment source, distinct from the code-side enrichers above.
Where a README/model-card parser is limited to pattern matching, an agent
can read prose, reason about intent, and infer information no structured
extractor can reach -- a plausible license from ambiguous wording, what a
dependency is actually *for*, or a `trainedOn`/`testedOn` dataset
relationship implied by a paragraph rather than a machine-readable field.

This is documented and enabled today via the `skills/sbom-enrich/` Skill
(see [adoption-surfaces.md](../implementation/adoption-surfaces.md) and
[agent-skill.md](../implementation/agent-skill.md) for the surfaces this
builds on); it does not require new code inside Pitloom core. The Skill
runs the deterministic `loom enrich` pass first (see "Surfaces" above),
then only proposes prose-derived fields for gaps that pass left
untouched -- default precedence is deterministic-wins, with an explicit
override path (recording both values and a reason) when the agent has
clear contradicting evidence from prose. See `skills/sbom-enrich/SKILL.md`
for the full sequencing.

| Source | What it provides | Network required | Default |
| :----- | :--------------- | :--------------- | :------ |
| AI agent (Skill / plugin) | Prose-derived inference: license guesses, dependency purpose, dataset relationships, anything requiring reading comprehension rather than parsing | Optional (agent-dependent; Pitloom itself needs none) | User opt-in (agent only enriches when asked, or when a skill/plugin step explicitly runs) |

### Delivery path: fragment merge, not direct edits

An agent never edits a generated SBOM file in place. Instead it follows
the same **fragment** mechanism already used by `pitloom.loom` and
third-party fragment producers (see
[sbom-fragments/fragment-merge-design.md](sbom-fragments/fragment-merge-design.md)):

1. Generate (or reuse) a base SBOM with `loom <project-or-model>`.
2. Draft a small, standalone SPDX 3 JSON-LD fragment containing only the
   elements or relationships the agent inferred.
3. Register the fragment in `pyproject.toml`:

   ```toml
   [tool.pitloom.fragment]
   files = ["fragments/agent-enrichment.spdx3.json"]
   ```

4. Re-run `loom <project-or-model>` so `merge_fragments()` folds the
   fragment into the final SBOM.

Every inferred field carries a provenance marker in its `comment` --
`Source: <agent name> (<vendor>) | Role: inferred | Date: <ISO 8601
date>` when the agent knows its own identity, else the generic `Source:
AI agent | Role: inferred` -- reusing the same `role: "inferred"`
provenance convention documented in
[metadata-provenance.md](../implementation/provenance/metadata-provenance.md) and in
[role-vocabulary.md](../implementation/provenance/role-vocabulary.md),
so agent-derived content is always distinguishable
from Pitloom's own extraction and from other configured enrichment
sources. This keeps the result auditable: a reviewer can grep for `AI
agent` or `Role: inferred` in the SBOM to see exactly what was
inferred rather than extracted.

See `skills/sbom-enrich/SKILL.md` and
`skills/sbom-enrich/references/examples.md` for the full agent-facing
instructions and a worked fragment example. Validate the merged result
with the `skills/sbom-validate/` Skill.

### Standards-driven completion: minimum elements

Alongside open-ended prose enrichment, `sbom-enrich` also has a
**checklist-driven** entry point: "Complete a standard's minimum
elements" in `skills/sbom-enrich/SKILL.md`, addressing
[bact/pitloom#137](https://github.com/bact/pitloom/issues/137). Instead
of opportunistically filling whatever gaps prose reveals, this mode runs
a gap analysis against a named standard's required elements -- NTIA
2021, CISA 2026 (the current baseline, supersedes NTIA 2021), or G7
SBOM for AI 2026 (additive, for AI models/datasets) -- and only then
falls back to the same resolution order (deterministic pass, prose,
then interactive questions) for whatever the checklist says is still
missing. It reuses every mechanism above unchanged: fragments,
the five-role provenance vocabulary, and the `sbom-validate` post-merge
check. The three checklists, each element mapped to the Pitloom/SPDX 3
field that already carries it (verified against a real generated AI
SBOM, not just source reading), plus a question bank for elements with
no automatable source, live in
`skills/sbom-enrich/references/minimum-elements.md`.

### Interactive mode: asking the SBOM author

When the Skill runs in an interactive session (a human present to answer),
it can go beyond prose inference for gaps neither the deterministic pass
nor prose resolves -- by asking. Some fields are things the person running
the enrichment is plausibly positioned to know even though no file states
them -- intended use, training-data provenance/consent, deployment
restrictions. The agent may ask a targeted question for *specific*
remaining gaps, not run an open-ended interview.

**Decision rule for the role: is the answer the fact, or a pointer to the
fact?**

1. **The SBOM author states the fact itself** ("it's MIT", "yes, trained
   on our internal support-ticket corpus"). Role is `sbomAuthorSupplied`,
   not `inferred` -- the agent didn't derive it, it relayed what it was
   told, and Pitloom can no more verify it than a `declared` value. See
   [role-vocabulary.md](../implementation/provenance/role-vocabulary.md)
   for the full definition; the same role also covers a
   value passed via CLI flag or `[tool.pitloom]` config, since both are
   the SBOM author asserting a value directly, just through a different
   channel than chat.
2. **The SBOM author points at a source instead** ("look at
   CONTRIBUTING.md", "read the internal wiki page", "try the HF model
   card", "infer it from the changelog"). The role is *never*
   `sbomAuthorSupplied` here -- the human didn't assert the fact, only
   named where to look. The agent must actually go look, and the
   resulting role is whichever mechanism it then used to get the value
   out of that source: `declared` if reading a field the source states
   about itself, `externalReported` if relaying another party's own claim
   found there, `inferred` if the agent had to reason over prose to reach
   it.

**Consent gate for any source outside the target project** -- applies
regardless of who initiated the lookup. Two ways this comes up:

- The SBOM author points the agent at an outside source (case 2 above).
- The agent notices something relevant **on its own initiative**, with no
  prompting: already sitting in its context window, in another file it
  has permission to read, or at a known remote location -- e.g. PyPI,
  arXiv, Hugging Face Hub, GitHub, GitLab, Codeberg, or a URL already
  visible in context. (Some of these overlap with data sources planned
  as future *deterministic* enrichers -- see "Enricher implementation
  approach" below; an agent-initiated lookup here is a distinct,
  informal, interactive-session-only path, not a substitute for building
  those.)

Either way, the agent must never fold the finding into a fragment
silently. It must name exactly what it found and where, and ask the SBOM
author for permission to use it, before drafting anything -- an
agent-initiated ask needs to be at least as explicit as one prompted by
the user, since there was no request inviting the agent to go looking in
the first place. The resulting role is still whichever of
`declared`/`externalReported`/`inferred` matches how the value was
obtained; the permission check is a consent gate, not a provenance role,
and never makes the result `sbomAuthorSupplied`.

In a non-interactive run (CI, batch, no human present to answer), skip
both entirely -- do not block waiting for input; fall back to prose-only
inference (or no enrichment) for anything these would have covered.

### Enricher implementation approach (shipped, MVP scope)

1. `src/pitloom/enrich/` subpackage, one module per data source. Shipped:
   `enrich/readme.py` (local YAML frontmatter). Not yet built:
   `enrich/openssf.py`, `enrich/huggingface.py`, `enrich/pypi.py` -- the
   framework (`enrich/base.py`'s `Enricher` protocol,
   `enrich/__init__.py`'s `run_enrichers()` dispatcher) supports them
   without further framework changes: implement `Enricher`, add one
   `EnrichConfig` field, one line in the dispatcher's fixed order.
2. Each enricher's `enrich(model, *, model_dir)` mutates the
   `AiModelMetadata` in place (same convention every extractor already
   follows) **and** returns an `EnrichmentResult` (`enrich/base.py`)
   listing exactly which fields it changed -- the return value, not a
   post-hoc diff, is what feeds N3's `CreationInfo` and the E1/E2
   Annotation (see `use-case-catalog.md`'s N3 row).
3. Wired at both the single-model and project levels. `generate_model_sbom()`
   (`src/pitloom/assemble/__init__.py`) reads `[tool.pitloom] enrich` from
   a `pyproject.toml` in the model file's own directory (no ancestor
   walk-up) and calls `run_enrichers()` after `read_ai_model()`, before
   `build_model()`. Project-level callers -- `generate_project_sbom()` and
   the Hatchling build hook's `_build_document_model()`
   (`plugins/hatch.py`) -- both call the same
   `run_enrichers_for_models()` (`enrich/__init__.py`), which resolves
   each discovered AI model's own directory from
   `AiModelFormatInfo.physical_path` and returns a parallel
   `list[list[EnrichmentResult]]` passed through to `build()` ->
   `add_ai_models()`; this is the one place "which directory does this
   model's enrichment look in" is decided, shared rather than
   reimplemented per caller. Only the local-file path runs `readme.py` --
   a Hugging Face Hub source already gets model-card frontmatter natively
   via `_load_model_card()` in `_huggingface.py`.
4. `enrich_model()` (same file) is the standalone-fragment counterpart:
   runs the same `run_enrichers()` call but skips full document assembly,
   producing just the new elements via `build_enrichment_fragment()`
   (`assemble/spdx3/document.py`) -- see "Surfaces" above.
5. Provenance: scalar fields (e.g. `license`) also get an entry in the
   existing `AiModelMetadata.provenance` dict, same as extractors; every
   changed field additionally becomes one entry in the `EnrichmentResult`
   that N3/E1/E2 consume, which a plain provenance-dict entry alone
   couldn't drive (no before/after value, no per-element grouping).

## AI SBOM field mapping: `pitloom:ai` namespace (CycloneDX)

When Pitloom gains CycloneDX output support, SPDX 3 native fields have no
direct equivalent and must be expressed as CycloneDX `properties` entries.
The following namespace is reserved for that purpose:

### Model identification and architecture

- `pitloom:ai:model:type` -- broad category (e.g., `transformer`, `cnn`)
- `pitloom:ai:model:architecture_family` -- specific structural family
- `pitloom:ai:model:parameters_count` -- total parameter count
- `pitloom:ai:model:format_version` -- version of the model file format
  (e.g., `v2` for Keras v2, `1.0` for NumPy 1.0)
- `pitloom:ai:model:framework` -- base framework/format
  (e.g., `pytorch`, `onnx`, `keras`)
- `pitloom:ai:model:framework_version` -- version of the framework that produced
  the model (e.g., `2.15.0` for Keras 2.15.0)

### Training and hyperparameters

- `pitloom:ai:training:learning_rate`
- `pitloom:ai:training:batch_size`
- `pitloom:ai:training:epochs`
- `pitloom:ai:training:optimizer` -- optimizer algorithm (e.g., `adamw`, `sgd`)
- `pitloom:ai:training:random_seed`

### Dataset constraints and provenance

- `pitloom:ai:dataset:training:name` -- name or URI of the training dataset
- `pitloom:ai:dataset:training:size` -- volume of data (e.g., `1.2TB`)
- `pitloom:ai:dataset:training:split` -- ratio or segment used (e.g., `train`)
- `pitloom:ai:dataset:preprocessing` -- normalization or transformation applied

### Metrics and evaluation

- `pitloom:ai:metric:accuracy`
- `pitloom:ai:metric:f1_score`
- `pitloom:ai:metric:loss`

### Ethical and compliance considerations

- `pitloom:ai:compliance:license_category` -- e.g., `open-weights`
- `pitloom:ai:safety:bias_mitigation` -- notes on debiasing techniques applied
- `pitloom:ai:safety:intended_use` -- approved use cases
- `pitloom:ai:safety:restricted_use` -- explicitly prohibited use cases
