---
Created: 2026-02-22
Last-Modified: 2026-08-10
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

## Planned: dataset-to-model relationship linking

A current gap in Pitloom's SBOM output is that only the AI model itself is
documented, not its associated training, evaluation, or fine-tuning datasets.

SPDX 3 provides the `dataset_DatasetPackage` class and dedicated relationship
types between `ai_AIPackage` and `dataset_DatasetPackage`:

| SPDX 3 Relationship type | Meaning |
| :---- | :---- |
| `trainedOn` | Primary dataset used to train the model |
| `testedOn` | Dataset(s) used to evaluate the trained model |
| `finetunedOn` | Dataset used for fine-tuning a pre-trained model |
| `validatedOn` | Dataset used for validation during training |
| `pretrainedOn` | Dataset used to pre-train a foundation model |

### Implementation approach

1. Extend `AiModelMetadata` with a `datasets` field (list of `DatasetReference`
   dataclass) carrying: role (trained/tested/etc.), name, URI, and license.
2. Add `dataset_DatasetPackage` element creation to `pitloom.assemble.spdx3.ai`.
3. Emit the appropriate relationship type for each dataset reference.
4. Append `ProfileIdentifierType.dataset` to `profileConformance` when at least
   one dataset element is present.

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
[tool.pitloom.enrich]
local = false          # README / model card -- off by default, opt in explicitly
```

Only `local` exists today -- `openssf_scorecard`/`huggingface`/`pypi` keys
are added when their enrichers actually land, not pre-declared ahead of
them (same discipline `[tool.pitloom.provenance]`'s keys followed:
one key per shipped capability, not a speculative full set up front).

### Surfaces (shipped)

The mechanical enrichment engine (`run_enrichers()`) is exposed the same
way across every generation path -- no surface has its own bespoke
on/off model:

| Surface | How to opt in |
| :------ | :------------ |
| CLI -- `loom model`/`loom project`/`loom generate` | `--enrich` (or `--no-enrich` to force off despite config) |
| CLI -- standalone `loom enrich <model-file>` | Always runs -- invoking the command is itself the opt-in; writes a standalone fragment (no `SpdxDocument`/`software_Sbom`/`ai_AIPackage`) for merging into a base SBOM via `[tool.pitloom.fragments]` |
| Python API -- `generate_model_sbom()`/`generate_project_sbom()`/`generate()` | `enrich=True`/`enrich=False` keyword (`None` defers to config) |
| Python API -- `enrich_model()` | Same as `loom enrich`: always runs, returns the fragment JSON string |
| Hatchling build hook | Inherits the project's `[tool.pitloom.enrich]` automatically -- no separate hook-level key, per the same "one config surface" rule the hook already enforces for creator/tool/fragment settings |
| GitHub Action | `enrich: "true"`/`"false"` input, mapped to `--enrich`/`--no-enrich`; empty (default) defers to config |

**Design invariant:** `loom generate --enrich <target>` and (`loom
generate --no-enrich <target>` + `loom enrich <target>` + `loom merge`)
produce equivalent enrichment evidence -- both paths share the same
deterministic identity computation for the referenced `ai_AIPackage`
(`_ai_model_identity()` in `document.py`), so a standalone fragment always
merges cleanly into a base document generated separately. Verified by
`tests/test_generator.py::test_enrich_then_merge_matches_one_shot_enrich`.

## AI-agent enrichment (skill / plugin)

An AI agent (e.g. Claude Code, or another Agent-SDK-based runtime) is
itself an enrichment source, distinct from the code-side enrichers above.
Where a README/model-card parser is limited to pattern matching, an agent
can read prose, reason about intent, and infer information no structured
extractor can reach -- a plausible license from ambiguous wording, what a
dependency is actually *for*, or a `trainedOn`/`testedOn` dataset
relationship implied by a paragraph rather than a machine-readable field.

This is documented and enabled today via the `skills/sbom-enrich/` Skill
(see [adoption-surfaces.md](adoption-surfaces.md) and
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
[sbom-fragments.md](sbom-fragments.md)):

1. Generate (or reuse) a base SBOM with `loom <project-or-model>`.
2. Draft a small, standalone SPDX 3 JSON-LD fragment containing only the
   elements or relationships the agent inferred.
3. Register the fragment in `pyproject.toml`:

   ```toml
   [tool.pitloom.fragments]
   files = ["fragments/agent-enrichment.spdx3.json"]
   ```

4. Re-run `loom <project-or-model>` so `merge_fragments()` folds the
   fragment into the final SBOM.

Every inferred field carries a provenance marker in its `comment` --
`Source: <agent name> (<vendor>) | Method: inference | Date: <ISO 8601
date>` when the agent knows its own identity, else the generic `Source:
AI agent | Method: inference` -- reusing the same `role: "inferred"`
provenance convention documented in
[metadata-provenance.md](metadata-provenance.md) and in
[annotation-provenance.md](../implementation/annotation-provenance.md)'s
G2 role vocabulary, so agent-derived content is always distinguishable
from Pitloom's own extraction and from other configured enrichment
sources. This keeps the result auditable: a reviewer can grep for `AI
agent` or `Method: inference` in the SBOM to see exactly what was
inferred rather than extracted.

See `skills/sbom-enrich/SKILL.md` and
`skills/sbom-enrich/references/examples.md` for the full agent-facing
instructions and a worked fragment example. Validate the merged result
with the `skills/sbom-validate/` Skill.

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
   Annotation (see `annotation-provenance.md`'s N3 row).
3. Wired at both the single-model and project levels. `generate_model_sbom()`
   (`src/pitloom/assemble/__init__.py`) reads `[tool.pitloom.enrich]` from
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
