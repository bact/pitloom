---
Created: 2026-10-18
Last-Modified: 2026-10-18
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
pip install "ntia-conformance-checker @ git+https://github.com/bact/ntia-conformance-checker.git@bebf5f85376f85c3e23e4f04e2dabd86ebc63d9a"
loom model model.safetensors -o model.spdx3.json      # or an ONNX, GGUF, NumPy or fastText file
loom model org/name -o model.spdx3.json              # a Hugging Face model
loom generate path/to/project -o project.spdx3.json  # a project that ships a model
sbomcheck -s spdx3 -c g7ai -r json  -o report.json  model.spdx3.json
sbomcheck -s spdx3 -c g7ai -r sarif -o report.sarif model.spdx3.json
```

Each of the 81 G7 rules is `present`, `missing`, `not-applicable` (the SBOM has
nothing of that kind, such as no dataset) or `out-of-scope` (the checker does not
check it). The result is "the SBOM has the property the checker looks for", not a
claim of G7 compliance. A check of a property does not judge its value.

A project that ships one model and no system of its own is judged by the model
for the System-level properties; the report names the model
(`systemJudgedByModel`). With two models, or none, the project stays the system.

## How much the checker finds

Share of the checked rules that are `present`, per cluster, for the test
models of 2026-10-18 (`--`: nothing of that kind to check). A tiny test model
carries little metadata, so these figures are low by nature; a model with a
card, an author and a version scores higher.

| SBOM of | Metadata | System | Model | Dataset | All |
| :------ | -------: | -----: | ----: | ------: | --: |
| Safetensors file | 86% | 11% | 29% | -- | 34% |
| ONNX file | 86% | 33% | 62% | -- | 58% |
| GGUF file | 86% | 11% | 43% | -- | 42% |
| NumPy file | 86% | 11% | 38% | -- | 40% |
| fastText file | 86% | 44% | 62% | -- | 60% |
| Hugging Face model | 86% | 56% | 57% | 22% | 48% |
| Model with a licensed dataset (library) | 86% | 33% | 43% | 44% | 46% |
| Hatchling project with a model | 100% | 22% | 29% | -- | 40% |
| setuptools project with a model | 100% | 22% | 29% | -- | 40% |
| Poetry project with a model | 100% | 22% | 29% | -- | 40% |

The three build backends give the same result for the same project.

## What Pitloom leaves out and why

- **No version, producer or time for a model file.** A bare file carries none.
  Pitloom does not copy a project's author onto its model.
- **No hash for a Hugging Face model.** A repository has many files; hashing them
  needs a request each. A local file always gets its SHA-256.
- **A model's inputs and outputs are only what its format states.** ONNX, Keras,
  HDF5 and PT2 state a signature; Safetensors and NumPy hold weights and arrays,
  which are not inputs, so none is written.
- **A producer is a generic agent**, not a person or an organisation, because a
  name does not say which. A Hugging Face owner is the repository owner, recorded
  as such.
- **A fastText model's domain is derived from the format**, not stated in the
  file; its provenance says so.
- **Dataset licence, provenance and statistics reach a model SBOM only through the
  library.** No reader feeds a dataset card into a model SBOM yet.
- **Licence IDs are kept as read** when the `licenseid` database is not built.
- **A setuptools project ships a model only when `package-data` lists it**, and
  the SBOM describes what would ship.

### What SPDX 3.0.1 cannot record

Twenty-five G7 elements have no SPDX 3.0.1 property, or are not yet reviewed. Where
Pitloom reads such a value it records it only openly: the parameter count as an
`ai_hyperparameter` entry with a comment saying it is not a hyperparameter; known
biases as text in the package comment; a model's own metadata in an annotation.
The architecture shares `ai_typeOfModel` with the model type, so the two cannot be
told apart.

## CISA 2026 Minimum Elements

The same checker reports on the 2026 CISA Minimum Elements, for SPDX 3.0 only:
`sbomcheck -s spdx3 -c cisa2026 -r json -o report.json model.spdx3.json`. Of its
23 rules 14 are checked; the author signature, tool version, SBOM version and
the six Practices and Processes elements are listed, never checked.

For Pitloom's test SBOMs the checked rules are met as follows (the checker's
reading, not a claim of compliance):

| Element | Result |
| :------ | :----- |
| Author, format name and version, generation context, timestamp, tool name, identifiers, name | present in every scenario |
| Hash value and algorithm | present, except for a Hugging Face model (no file hash) |
| Dependency relationship | present for projects, not for a single model |
| Producer, version, licence | present for a Hugging Face model and a library-built one; missing for a model file or a project, since the file states none |

Hash value and algorithm are checked as "an integrity method is present", not
that it is a hash with a value.

## Parity

Every surface gives the same G7 result for the same input: the library, the
`loom` command line (`model`, `generate`, `project`, `wheel`), the Hatchling hook
and, since the Action and the skills run those commands, the GitHub Action and
the skills. This is tested, not assumed. The one difference is by design: the
build hook records when the package was built (`builtTime`), because it runs
during a build.

Tiers apply only to AI model file formats and Python build backends. A known gap
there is listed below with what it needs; a date is set for each.

| Gap | Where | Needs | Target |
| :-- | :---- | :---- | :----- |
| No hash for a Hugging Face model | Hub source | A request per file, or a Merkle root | to be set |
| Dataset licence, provenance and statistics reach no model SBOM | all sources | A reader for dataset cards, then the `loom` SDK | to be set |
| A notice when a value is read but cannot be recorded | all readers | One shared message helper | to be set |
| Tier 2 formats | Keras, HDF5, PyTorch, PT2, CRFsuite | Anything beyond keeping them working | to be set |
