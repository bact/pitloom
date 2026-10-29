---
Created: 2026-10-18
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# G7 SBOM for AI

See also: [AI model formats](ai-model-formats.md) (what each format gives),
[Metadata provenance](metadata-provenance.md) (where each value came from),
[Command line](cli.md).

Pitloom writes SPDX 3.0 SBOMs for AI models. This page says how much of the
[G7 SBOM for AI: Minimum Elements](https://www.bsi.bund.de/SharedDocs/Downloads/EN/BSI/KI/SBOM-for-AI_minimum-elements.pdf)
those SBOMs cover, how to check it, and what Pitloom leaves out and why.

An incomplete, honest SBOM is better than one that looks complete and is not.
Pitloom leaves a field out when its source does not state it, and never writes
a placeholder to satisfy a rule.

A G7 element can be missing for two different reasons, and this page keeps them
apart:

- **Pitloom cannot extract it**, or cannot decide between sources that
  disagree ([What Pitloom leaves out](#what-pitloom-leaves-out-and-why)). A
  fragment or the `sbom-enrich` skill can supply what a file does not state.
- **Pitloom has the value, but SPDX 3.0.1 has no place for it**
  ([What SPDX 3.0.1 cannot record](#what-spdx-301-cannot-record)). Pitloom then
  records it in a stated workaround or not at all, and says so. A fragment or
  the skill cannot add a place the format lacks: they fill only what it can
  hold.

## What is covered

| Axis | Covered |
| :--- | :------ |
| Elements | Four of the seven G7 clusters: Metadata (`MD`), System-level properties (`SLP`), Models (`MDL`) and Dataset properties (`DP`) |
| SBOM format | SPDX 3.0 (3.0.1) |
| Model sources, tier 1 | Safetensors, ONNX, GGUF, NumPy, fastText, and Hugging Face Hub models |
| Model formats, tier 2 | Keras, HDF5, PyTorch classic, PT2 / ExecuTorch, CRFsuite: kept working; a bug fix may wait, and is written down |
| Python build backends | Hatchling, setuptools, Poetry |

Not covered: the Infrastructure, Security and Key Performance Indicators
clusters. Some G7 elements have no property in SPDX 3.0.1 (see
[below](#what-spdx-301-cannot-record)).

A fix that stops a value being untrue applies to every tier. A tier only
decides how soon a missing feature arrives.

## Check an SBOM

The checker is [`ntia-conformance-checker`](https://github.com/bact/ntia-conformance-checker)
with the `g7ai` standard, which is not yet on PyPI:

```shell
pip install "ntia-conformance-checker @ git+https://github.com/bact/ntia-conformance-checker.git@2355afcd7ec9af732f80680928849db6008e6e9a"
loom model model.safetensors -o model.spdx3.json      # or an ONNX, GGUF, NumPy or fastText file
loom model org/name -o model.spdx3.json              # a Hugging Face model
loom generate path/to/project -o project.spdx3.json  # a project that ships a model
sbomcheck -s spdx3 -c g7ai -r json  -o report.json  model.spdx3.json
sbomcheck -s spdx3 -c g7ai -r sarif -o report.sarif model.spdx3.json
```

`-c` also takes `ntia` (NTIA 2021), `cisa2026`, `fsct3` and `bsi`. The sections
below report the last three; Pitloom's tests pin no NTIA outcomes. Every
standard judges the datasets and models a component reaches by `trainedOn` and
`testedOn`. [Lumina](https://github.com/bact/lumina), a web UI, shows the same
checker results rule by rule.

Each rule (81 for G7) is `present`, `missing`, `not-applicable` (the SBOM has
nothing of that kind, such as no dataset) or `out-of-scope` (the checker does not
check it). The result is "the SBOM has the property the checker looks for", not a
claim of G7 compliance. A check of a property does not judge its value.

When an SBOM's one root is a single AI model and nothing else, the System-level
properties are read from that model, and the report names it
(`systemJudgedByModel`). A project that ships a model has two roots, its package
and, in a second SBOM element, the model. The checker reads the System-level
properties from both, so each rule has to hold for the package and for the
model, and most of them are missing.

## How much the checker finds

Share of the checked rules that are `present`, per cluster, for Pitloom's test
models (figures of 2026-10-18, unchanged in 0.21.0; `--`: nothing of that kind
to check). A tiny test model
carries little metadata, so these figures are low by nature; a model with a
card, an author and a version scores higher.

| SBOM of | Metadata | System | Model | Dataset | All |
| :------ | -------: | -----: | ----: | ------: | --: |
| Safetensors file | 86% | 11% | 29% | -- | 34% |
| ONNX file | 86% | 33% | 62% | -- | 58% |
| GGUF file | 86% | 11% | 43% | -- | 42% |
| NumPy file | 86% | 11% | 38% | -- | 39% |
| fastText file | 86% | 44% | 62% | -- | 61% |
| Hugging Face model | 86% | 56% | 57% | 28% | 50% |
| Model with a licensed dataset (library) | 86% | 33% | 43% | 44% | 46% |
| Hatchling project with a model | 100% | 22% | 29% | -- | 39% |
| setuptools project with a model | 100% | 22% | 29% | -- | 39% |
| Poetry project with a model | 100% | 22% | 29% | -- | 39% |

The three build backends give the same result for the same project.

## What Pitloom leaves out and why

- **No release time for a model file, and a version or producer only where the
  file states one** (a PT2 file does; most files do not). Pitloom does not copy a
  project's author onto its model.
- **A dependency's hash is only what its lock file or index states** (a SHA-256), never
  computed, so a dependency cannot meet a SHA-512 requirement such as BSI's.
  A project's own hash is a SHA-256 Merkle root over its files, not the hash of
  a built archive.
- **No hash for a Hugging Face model.** A repository has many files; hashing them
  needs a request each. A local file always gets its SHA-256 and SHA-512.
- **A model's inputs and outputs are only what its format states or implies.**
  ONNX, Keras, HDF5 and PT2 state a signature. A fastText or CRFsuite model has a
  fixed kind of output (label probabilities, a label sequence), which Pitloom
  names itself; its provenance says `derived_from_format`. Safetensors and NumPy
  hold weights and arrays, which are not inputs, so none is written.
- **A producer is a generic agent**, not a person or an organisation, because a
  name does not say which. A Hugging Face owner is the repository owner, recorded
  as such.
- **A fastText model's domain is derived from the format**, not stated in the
  file; its provenance says so. A fragment's domain (or description, or
  input/output text) replaces a value Pitloom only generated, with one `INFO:`
  line ([SBOM fragments](fragments.md)).
- **A dataset's licence, description, version and owner come only from what
  its source states.** For a Hugging Face model, Pitloom reads the Hub card and
  repository of each listed dataset (up to 20), only when it looks the model up.
  A dataset's provenance and statistics (collection, bias) reach a model SBOM
  only through the library (`loom` with a Croissant file); its size in bytes,
  for a single-file `loom` dataset (the bytes hashed, or its `stat()` size
  when over `max-dataset-hash-bytes`, which satisfies `DP-007`), unless it is
  an unpulled Git LFS pointer (or an over-cap file under 1,024 bytes), or when
  a library caller sets `DatasetMetadata.byte_size`. A dataset named in a
  local model card gets only its name.
- **Licence IDs are kept as read** when the `licenseid` database is not built.
- **A setuptools project ships a model only when `package-data` lists it**, and
  the SBOM describes what would ship.

### What SPDX 3.0.1 cannot record

The checker does not check 25 G7 elements (`out-of-scope`). For 20 of them the
G7 to SPDX 3.0.1 mapping finds no native SPDX property; the other five are in
the Infrastructure, Security and Key Performance Indicators clusters. Pitloom
writes the mapped property for some of them, which no rule then reads.

Where Pitloom reads such a value it records it only openly, and the SBOM says
when a place is a workaround:

| Element | Recorded as |
| :------ | :---------- |
| Parameter count | An `ai_hyperparameter` entry `parameters`, with a comment saying it is a count of elements, not a hyperparameter |
| Context length | An `ai_hyperparameter` entry under the source's own key (such as `llama.context_length`) |
| Architecture | Appended to `ai_typeOfModel` after the model type, so the two cannot be told apart; Pitloom says so once per model with an `INFO:` line (`no SPDX 3.0.1 property: model-architecture (written in ai_typeOfModel)`) |
| Input and output | A labelled JSON text in `ai_informationAboutApplication`; the checker counts the property as present, which is not a statement of intended use |
| A model's known biases | Text in the package comment |
| A model's own file metadata | An annotation, preserved and not interpreted |
| A dataset's record count | Not recorded: `dataset_datasetSize` is a size in bytes, and a Croissant file has no standard key for a count |

A value that has no honest place at all is left out, and the same `INFO:` line
names it. SPDX 3.1 adds some of what is missing, such as a tool version.

## CISA 2026 Minimum Elements

The same checker reports on the 2026 CISA Minimum Elements, for SPDX 3.0 only:
`sbomcheck -s spdx3 -c cisa2026 -r json -o report.json model.spdx3.json`. Of its
23 rules 14 are checked; the author signature, tool version, SBOM version and
the six Practices and Processes elements are listed, never checked.

The component rules judge every package linked from the SBOM root, and also the
datasets and models linked by `trainedOn` and `testedOn`, so a training dataset
with no producer, hash or version is reported.

For Pitloom's test SBOMs the checked rules are met as follows (the checker's
reading, not a claim of compliance):

| Element | Result |
| :------ | :----- |
| Author, format name and version, generation context, timestamp, tool name, identifiers, name | present in every scenario |
| Hash value and algorithm | present for model files and projects. Missing for the Hugging Face and library-built models, because their dataset has no hash (a Hugging Face model has none either) |
| Dependency relationship | present for projects, not for a single model |
| Producer | missing in every scenario: a model file, a dataset and the model inside a project state none |
| Version, licence | present for the Hugging Face model (its dataset's Hub card states a licence and the Hub its revision) and the library-built model; missing for model files and projects, since the file states none |

The hash check accepts any real hash with a value, so a project's Merkle root
(an aggregate over its files, not the hash of one artefact) passes it.

## FSCT 2024

`-c fsct3` reports on the baseline attributes of the 2024 CISA Framing Software
Component Transparency (minimum expected level). Of its 13 rules 10 are checked;
the primary component, the cryptographic hash and the per-component relationship
are listed, never checked. For Pitloom's test SBOMs, as the checker reads them:

| Element | Result |
| :------ | :----- |
| Author name, timestamp, SBOM type, component name | present in every scenario |
| Unique identifier | present in every scenario: a package URL on every package |
| Dependency relationship | present for projects, through the project's `contains` link to its model, which the check accepts in place of a dependency; not present for a single model |
| Version | present for the Hugging Face model (its dataset's version is the Hub revision) and the library-built model; missing for a model file and the model inside a project, since the file states none |
| Supplier name | missing in every scenario |
| Concluded licence, copyright notice | missing in every scenario. Pitloom can write a concluded licence and copyright text when its sources state them, but the test SBOMs carry none: a project's copyright text is `NOASSERTION`, which the checker counts as missing, and a model file carries none |

The same `trainedOn` and `testedOn` reach applies as for CISA 2026.

## BSI TR-03183-2 v2.1

`-c bsi` reports on the SBOM content requirements of the German BSI technical
guideline TR-03183-2 v2.1, per rule, for SPDX 3.0 only. Of its 20 elements 16
are checked; the BOM-URI, the executable and archive properties and the source
hash are listed, never checked (SPDX 3.0.1 cannot show them, or they always
exist). Elements BSI marks "if it exists" are `not-applicable` for a package
that does not give them. For Pitloom's test SBOMs:

| Element | Result |
| :------ | :----- |
| Timestamp, component name, other unique identifiers | present in every scenario |
| Hash of the deployable component (SHA-512) | present for model files; missing for a Hugging Face model, the library-built model and every project: a project's hash is a SHA-256 Merkle root, and a dependency or a dataset has no SHA-512 source |
| Component version | present for a Hugging Face model (its dataset's version is the Hub revision) and the library-built model; missing for model files and projects |
| Original licence (if it exists) | present for a Hugging Face model, the library-built model and projects |
| Creator of the SBOM and of each component | missing in every scenario: BSI wants a person or organisation with an e-mail address or URL, and Pitloom's creator is a software agent |
| Filename, dependencies with completeness, distribution licence, structured property, effective licence, security.txt URL | missing in every scenario: Pitloom does not write them |

Where BSI's own tables and the SPDX mapping differ, the checker accepts both
(see its BSI page). Like the other standards, BSI also judges the datasets linked by `trainedOn` and `testedOn`. The coverage figures are 29–40% of the checked rules.

## Parity

Every surface gives the same result for the same input: the library, the `loom`
command line (`model`, `generate`, `project`, `wheel`) and the Hatchling hook are
tested to agree on the checker's outcome for every rule, on the elements and
property names, and on the names, versions, identifiers and hashes. The Action
and the skills run the same `loom` commands with their own flags and are not
tested separately. The one difference is by design: the build hook records when
the package was built (`builtTime`), because it runs during a build.

## Gaps by format and backend

Tiers apply only to AI model file formats and Python build backends. A known gap
there is listed below with what it needs and a target date. A gap not closed by
its date stays listed with that date missed. As of 0.21.0 (2026-10-28) all three
dates below are missed and the gaps are open.

| Gap | Where | Needs | Target date (missed) |
| :-- | :---- | :---- | :----- |
| No hash for a Hugging Face model | Hub source | A request per file, or a Merkle root | 2026-10-19 |
| Dataset provenance and statistics reach a model SBOM only through `loom` | Hub source, local model cards | A reader for a Hub dataset's Croissant metadata | 2026-10-19 |
| Tier 2 formats | Keras, HDF5, PyTorch, PT2, CRFsuite | Anything beyond keeping them working | 2026-10-19 |
