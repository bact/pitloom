---
Created: 2026-10-23
Last-Modified: 2026-10-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# `loom` SDK: what it records today and how to expand it

See also: [roadmap.md](roadmap.md#loom-sdk-code-model-dataset-annotation)
(the roadmap section), [g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md)
(G7 #7, which this plans), [loom-sdk-and-notebooks.md](sbom-fragments/loom-sdk-and-notebooks.md)
(the earlier sketch: `log_*` API, notebook sessions, IPython magic),
[mlflow-extractor.md](mlflow-extractor.md) (reading the same facts from a
tracking server instead), [g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md),
[sbom-format-gaps.md](sbom-format-gaps.md); built behaviour:
[id-registry-v3-loom.md](../implementation/id-registry-v3-loom.md),
[ai-dataset-linking.md](../implementation/ai-dataset-linking.md); user page:
`docs/python-api.md`.

Status: section A describes what is built, checked against the tree at
`8ac401da` (2026-10-23). Sections B and C are not built and nothing in them
is decided. Effort (S under half a day, M about a day, L more, as in
[known-bugs.md](known-bugs.md)) is given only where the existing code makes
it estimable.

## A. What exists today

### API surface (`src/pitloom/loom.py`, `_loom_*.py`)

- `loom.run` / `loom.Run(output_file, pretty=False, creation_metadata=None,
  id_registry=None, *, pitloom_config=None)`: a `contextlib.ContextDecorator`,
  so both `with loom.run(...) as run:` and `@loom.run(...)`. Runs nest; a
  recursive decorated call is safe.
- Declarations, as module functions and as methods of the run object:
  `set_model(name, model_type=None, hyperparameters=None, generated=None, *,
  path=None)`, `use_model(...)` (`generated=False`),
  `set_model_hyperparameters(dict[str, str])` (replaces the last declared
  model's), `add_dataset`, `add_validation_dataset`, `add_input_dataset`
  (`name, dataset_type="text", *, croissant=None, declared_license=None`) and
  `add_output_dataset(..., data_preprocessing=None, input_datasets=None)`.
  A call outside a run raises `RuntimeError`. Every function returns `None`.
- Config: of `pitloom_config=` only `id-registry`, `update-id-registry` and
  `max-dataset-hash-bytes` are read; no `[tool.pitloom]` is read implicitly.

### What a run records

| Declared | SPDX 3.0.1 output |
| :------- | :---------------- |
| `set_model` / `use_model` | one `ai_AIPackage` per call: `name`, `ai_typeOfModel` (`[model_type]`), `ai_hyperparameter` (string values); with `path=` a regular file at run exit, `verifiedUsing` SHA-256 and SHA-512 |
| `add_dataset` and siblings | one `dataset_DatasetPackage` per key and content, `dataset_datasetType`; a single file adds a `software_File` and `contains`, both hashed (SHA-256, SHA-512); a directory gets a SHA-256 Merkle root |
| `croissant=`, a directory's dataset card, `declared_license=` | licence, version, description, download location, size, collection process, preprocessing, known bias, intended use, personal information, anonymisation (`set_dataset_fields`); a creator as `publishedBy`; each with provenance. A declared licence wins over Croissant, Croissant over a card |
| model + `add_dataset` / `add_validation_dataset` | `trainedOn` / `testedOn` from the run's model |
| `add_output_dataset` | `hasInput` to the inputs it names (all when `None`) |
| the calling script | a `software_File`; `generates` (scope `build`) to the model when `generated=True`, or when `generated` is `None` and a training dataset was declared; otherwise `hasDataFile` (scope `runtime`); `generates` to output datasets |
| each call | a provenance `Annotation` naming the caller (`Method: inspect_caller`) |

The fragment is written only when the block exits without an exception; a
model the registry did not know is registered after the fragment is written.
With a registry, the model is looked up by its `path=` file's path key, gated
by its SHA-256; datasets by path key and content. Without a registry every id
is minted under a fresh `uuid4()` document uuid.

### How it reaches the SBOM

A run writes one SPDX 3.0.1 JSON-LD fragment (no other format). It reaches a
project SBOM only when `[tool.pitloom.fragment] files` lists it: the project
surfaces merge it (`loom generate`/`loom project` on a directory,
`generate_project_sbom()`, the Hatchling hook), or `loom merge` does. The SDK
runs only inside the user's own Python process: no CLI subcommand, Action
input or skill invokes it; `skills/sbom-generate/SKILL.md` mentions it as a
source of datasets and models. Non-directory targets drop configured fragments
without a `WARNING:` (roadmap, "No silent deviations, per surface").

## B. What can be expanded

Each row names the G7 SBOM-for-AI element (2026, checker rule family in
`ntia-conformance-checker` `rules/g7ai.yaml`) and the SPDX 3.0.1 property the
G7 mapping (`tests/fixtures/conformance/g7ai2026-to-spdx30.sssom.tsv`) points
to. "Not written" means `loom` has no argument that writes it today (checked
in `_loom_active_run.py`, `_loom_model.py`, `_loom_dataset.py`).

### B1. Dataset provenance (G7 DP-006, DP-008, DP-009)

- **Collection method, sensitivity, bias, intended use as arguments.**
  `dataset_dataCollectionProcess`, `dataset_hasSensitivePersonalInformation`,
  `dataset_anonymizationMethodUsed`, `dataset_knownBias`,
  `dataset_intendedUse` are written today only from a Croissant file or a card.
  `DatasetMetadata` and `set_dataset_fields` already carry every one, so this
  is wiring plus a precedence rule per field (declared wins, as
  `declared_license` does) and one test per tri-state boundary. **S-M.**
- **Preprocessing on any dataset.** `data_preprocessing=` exists only on
  `add_output_dataset`; a training dataset cannot state it. **S.**
- **Dataset source (DP-006).** The rule reads `originatedBy`; loom writes a
  creator only as `publishedBy` (FG-5 in
  [sbom-format-gaps.md](sbom-format-gaps.md); roadmap "G7 dataset creator").
  An explicit `originator=` argument would state the role instead of guessing
  it. Needs the FG-5 decision first.
- **Dataset dependency (DP-009).** The rule reads `dependsOn` or
  `descendantOf`; loom links an output to its inputs with `hasInput`. Whether
  `hasInput` should also satisfy it is a checker or mapping question, not a
  reason to change Pitloom's relationship type.
- **Synthetic data method** (mapping: a `generates` edge from the generator):
  no API today.

### B2. Model training properties and evaluation (G7 MDL-011, KPI)

- **Training information** (`ai_informationAboutTraining`, read by the model
  learning-type rule beside `ai_typeOfModel`): pre-training, fine-tune,
  RLHF, post-training technique. `model_type=` fills only `ai_typeOfModel`,
  which also holds the architecture (FG-2). A `training=` text argument. **S.**
- **Model data preprocessing** (`ai_modelDataPreprocessing`, the mapping's
  "training properties" match): not written.
- **Metrics** (`ai_metric`, `ai_metricDecisionThreshold`; G7 operational
  KPIs, which the checker lists but does not check). The sentimentdemo
  `evaluate.py` computes F1, precision and recall and can only print them.
  The earlier sketch maps `log_evaluation` to an `Annotation`; SPDX 3.0.1 has
  native properties, so prefer them. Open: `ai_metric` sits on the model, with
  no link to the dataset it was measured on; if that is confirmed, it is a
  format-gap ledger entry in the same change.
- **Energy** (`ai_energyConsumption`, training, fine-tuning, inference): not
  written; a value only the user can state.
- **Hyperparameter values**: `dict[str, str]` only. Accepting numbers needs
  one canonical spelling of a float or int (canonical-output rules) before it
  reaches `ai_hyperparameter`.

### B3. Model description, lineage and producer (G7 MDL-004, MDL-006)

- **Lineage** (`descendantOf`): a `base_model=` argument for a fine-tune. The
  Hugging Face route already writes `descendantOf`; the base model's id needs
  the same registry or PURL rule as any other model.
- **Limitation, intended use, domain** (`ai_limitation`,
  `ai_informationAboutApplication`, `ai_domain`): not written. A declared
  value meets a value the project scan reads from the model file at merge;
  see C2 for which wins.
- **Producer and parameter count** for a `loom.run` model (`originatedBy`, the
  `parameters` entry): left open by #6 (PR #306) under G7 #7. A count only
  from a source that states one; a `"7B"` string is not a count (the rule in
  `is_parameter_count_text`).
- **Timestamp** (`builtTime`): must come from a pinned source
  (`SOURCE_DATE_EPOCH`), never the clock, or fragments stop being
  reproducible. Not designed.

### B4. Identity and structure

- **Several models per run.** Each `set_model` adds an `ai_AIPackage`, but
  `trainedOn`, `testedOn`, `generates` and `hasDataFile` attach only to the
  last one declared (`LoomModels.resolve()` returns the last declaration).
  An earlier model in the same run is in the fragment and linked to nothing.
  A handle returned by `set_model` (or a `model=` argument on the dataset
  calls) would say which model a dataset belongs to. **M** (API change,
  relationship emission, a test per pairing).
- **Ids without a registry.** Every run mints under a fresh `uuid4()`, so two
  runs of one script give different bytes and ids, and only a SHA-256 can
  unify their elements at merge; an element with no hash never does (item 11
  of [id-registry-v3.md](../implementation/id-registry-v3.md) and "pitloom.loom
  run namespaces" in [id-registry-followups.md](id-registry-followups.md)). A
  deterministic document uuid (from the output path and the script) would
  meet the SBOM determinism rule; not designed.
- **`path=` is what links loom's model to the file.** Only a model declared
  with `path=` carries the file's hashes, so only it unifies with the project
  scan's model at merge (by SHA-256), and with a registry it is keyed by its
  file and gated by its content, as a scan's model is. The "no `path=`"
  `WARNING:` fires only while a registry is loaded (decided in
  id-registry-v3.md: without one, a missing hash is normal absence). The
  docs could say plainly that a model without `path=` stays a separate
  package after the merge. **S** (docs).
- **Decorator and context manager** both exist. A builder object (the earlier
  sketch's `ds.set_license(...)`) and a persistent notebook session are in
  [loom-sdk-and-notebooks.md](sbom-fragments/loom-sdk-and-notebooks.md).

### B5. Frameworks and surfaces

- **Framework helpers**, opt-in: read what a framework object states (fastText
  `getArgs()`, which sentimentdemo copies by hand; scikit-learn
  `get_params()`; a trainer's arguments) into hyperparameters. Never inferred
  from code that was not called.
- **Hook and Action**: both merge listed fragments but never run a script. The
  fragment records the script's SHA-256 (its `software_File`); a merge could
  report a fragment whose script changed since it was written, as
  `loom fragment list` reports `SHA256=` and `MODIFIED=` today. An idea, not
  designed.

## C. Gaps learned so far

### C1. sentimentdemo: models declared without `path=`

The sentimentdemo repository (local copy at `74462e8`, 2026-09-18) calls
`run.set_model(model_file_path, model_type="supervised")` in `train.py`, and
`use_model` in `evaluate.py` and `predict.py`, without `path=` and without
`id_registry=`. A probe on `8ac401da`, no registry: two runs of
`set_model("m.bin")` and two of `set_model("m.bin", path="m.bin")` gave four
different `ai_AIPackage` ids; `loom merge` of the two `path=` fragments gave
one `ai_AIPackage` (unified by SHA-256), of the two without `path=` two.
Elements are never unified by name alone (`docs/fragments.md`), so a model
declared without `path=` has no hash to unify on, and each regenerated
sentimentdemo fragment adds its own copy of the one model beside the project
scan's. The committed fragments share `#AIPackage-2` only because an older
Pitloom wrote them with the repository's v2 `loom-ids.json`, which v3 refuses
(#305). The full pipeline (fastText training) was not rerun. Pitloom's own
copy, `examples/sentimentdemo-aibom/`, passes `path=` and `id_registry=`.
Fix: in sentimentdemo, both arguments; in Pitloom, the docs line in B4.

### C2. Fragment value vs a value Pitloom generated or read

PR #349 (open, 2026-10-23) makes a fragment's `description`, `ai_domain` or
`ai_informationAboutApplication` replace one Pitloom generated from the
model's format (`generated_from_labels`, `derived_from_format`), with one
`INFO:`; a value read from the file still wins a conflict. A `loom` fragment
is merged by the same code, so every field B adds to the model inherits that
rule. Whether an explicit SDK declaration should beat a value read from the
file ("honour user intent") is a decision for the SDK work, field by field,
not a side effect of the merge order.

### C3. Recorded bugs that concern the SDK

- `loom fragment validate A B` fails on two `loom.run` fragments: both name
  their creation info `_:CreationInfo0`
  ([known-bugs-p3.md](known-bugs-p3.md)).
- The model provenance annotation's document name falls back to `"model"`
  (`_loom_model.py`, `declared.name or "model"`); unchecked against the name
  cascade (same file).
- `_get_caller_script_path()` (`_loom_caller.py`) still probes with
  `Path.is_file()`; datasets and models moved to `path_probe.is_regular_file`.
  Its broad `except` turns a raised error into one `WARNING:`.

### C4. Honesty rules every new argument follows

- Absent (`None`) is "not stated": nothing is written, silently. Empty but
  given (`[]`) is a real statement and wins, as `data_preprocessing=[]` does
  today.
- A placeholder is not a claim: `unknown`, blank or a bare `other` is no
  value, as `declared_license` already treats them; `NOASSERTION` is written
  as stated.
- A value goes to the property the G7 mapping names, or to the format-gap
  ledger; never stretched into another property without saying so
  ([g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md)).
- Each value keeps its provenance (`inspect_caller`), so a reader can tell a
  declared fact from a read one.
