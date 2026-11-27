---
Created: 2026-10-18
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM minimum elements: G7 SBOM for AI 2026

See also: [`minimum-elements.md`](minimum-elements.md) (the other standards,
the status legend, checker ids and how the calls were verified),
[`minimum-elements-questions.md`](minimum-elements-questions.md),
[`minimum-elements-workflow.md`](minimum-elements-workflow.md).

The G7 checklist of the five in
[`minimum-elements.md`](minimum-elements.md): every cluster, mapped to the
Pitloom/SPDX 3 field that carries it, with the status words that page defines.

## G7 SBOM for AI 2026 (additive -- apply only when an `ai_AIPackage` is present)

Checker `g7ai`: 81 rules (`BOM-G7AI2026-<id>`), 25 of them `out-of-scope`:
Metadata 10 (3), System Level Properties 12 (3), Models 28 (7), Dataset
Properties 23 (5), Infrastructure 2 (2), Security Properties 4 (3), Key
Performance Indicators 2 (2), the `out-of-scope` count in brackets. The Metadata
cluster (`MD-001` to `-010`) reads what CISA 2026's SBOM Metadata does; its
`out-of-scope` rules are the SBOM version, author signature and tool version.
How much a default run fills, per cluster and model source: Pitloom's "G7 SBOM
for AI" page (<https://bact.github.io/pitloom/g7-sbom-for-ai/>).

### Models cluster

The checker reads `ai_AIPackage` properties only, in the way listed after the
table ("What the checker reads").

| Element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Model name | `ai_AIPackage.name` | covered (cut to 1024 characters with `...~<digest>`, controls shown as `\uXXXX`: a cap, not a gap); **gap** when `name` is only the file's stem (`Method: file_name_stem`: a stub, or a format with no name field; see `sbom-enrich`, step 3). A fragment model element that unifies with it (same `spdxId` or SHA-256, as from `loom.set_model(name, path=...)`) renames it |
| Model identifier | `software_packageUrl`: `pkg:huggingface/<owner>/<name>[@<commit>]` for a Hub model, else `pkg:generic/<file>?checksum=sha256:<digest>` for a hashed model file; DOI as `ExternalIdentifier` (type `other`) and the hub page as an `altWebPage` `externalRef`, when the source carries them | conditional; **gap** for a model with no file, no hub id and no DOI |
| Model version | `software_packageVersion`, when the format carries one (GGUF, ONNX `model_version`, PT2 `extra/model_version`, Safetensors `modelspec.version`/`version`/`model_version`); a Hugging Face model's version is its 40-digit commit hash (when the Hub gives one), so a new revision is a new document | conditional -- verify per model type |
| Model timestamp | `releaseTime` on the AI package: a Hugging Face model's last-modified time (its revision's commit time), when the Hub gives one. `CreationInfo.created` is when the SBOM was made, not the model's time, and does not count | conditional; **gap** for a model file, which carries no time |
| Model producer | `ai_AIPackage.originatedBy` -> one generic `Agent` (name only) per name a structured field states: ONNX `model_author` (a comma-separated list, split on commas), PT2 `extra/author`, GGUF `general.author` then `general.organization`, Safetensors `__metadata__` key `modelspec.author` (one name), the Hugging Face repository owner (`Method: repository_owner`). `suppliedBy` is set only on the Hugging Face route, to the same owner `Agent` (the Hub repository is the distribution source); no model file sets it, and a model never inherits the main package's. A re-upload, quantisation or fine-tune names its uploader: the original maker is a question for the card or the user (`descendantOf` records lineage only). A GGUF `general.organization` is often the converter's guess from the base model (read as stated). PyTorch classic, Keras, HDF5, NumPy, fastText and CRFsuite carry none | conditional -- check `originatedBy` first; **gap** when the format has no author field, it is empty, or the model is a stub (`sbom-enrich`, step 3). The `Agent` says nothing of person vs organisation: when the model card states which, or names a producer the file does not, add a `Person`/`Organization` to `originatedBy` by fragment; the generic `Agent` stays beside it (lists merge as a union; `examples.md`, "Model producer") |
| Model description | `ai_AIPackage.description`, when the format/source carries one (GGUF, ONNX, PT2, Safetensors, Hugging Face; distinct from the *main* `software_Package.description`). A CRFsuite model's description is Pitloom's own summary of its labels (`Method: generated_from_labels`), not the producer's | conditional -- verify per model type (`MDL-006` does not read `description`, see below); a `generated_from_labels` description is a **gap** for a producer-written one, which a fragment's different description replaces on a project base (one `INFO: Merge: ELEMENT=<spdx-id>: <property> generated from the model file replaced by a fragment's; kept <kept>, dropped <dropped> [generated-value-conflict]`; other conflicts keep the base's value); none at all when a label was over 4 KiB (a cap, see `sbom-generate`) |
| Model hash value / algorithm | `verifiedUsing` (`{"algorithm": "sha256", ...}` and `sha512`) on the `ai_AIPackage`, the model file's SHA-256 and SHA-512 (project, wheel, embed-wheel, hook, `model`, `loom.run` with `path=`); in a project, wheel or embed SBOM the model `contains` its `software_File`, which carries the same hashes (a `loom model` SBOM has no file element). A model read from Hugging Face, or declared without a file, has none | covered when a model file was read; **gap** for a pathless model. A fragment adds no `AIPackage` of its own, so it never supplies this hash |
| Model properties (architecture, parameter count, etc.) | `ai_typeOfModel` (type + architecture) and `ai_hyperparameter` (list of `DictionaryEntry`, incl. quantisation). The parameter count is the entry `parameters`, a decimal integer as text: SPDX 3.0.1 has no model-size property, so this entry is only the carrier (the package `comment` says so). Pitloom sums the tensor elements of GGUF, Safetensors, ONNX and PT2 files, counts a CRFsuite model's features (one weight each), and takes the Hub's sum (`safetensors.total`, else `gguf.total`); all stored tensors count, so it is no trainable-parameter figure (<https://bact.github.io/pitloom/ai-model-formats/#what-the-count-counts>) | covered for architecture/type/hyperparameters (the checker never judges architecture or the count: `MDL-009.2`/`.3`); parameter count covered by convention (a G7 'GAP' in the SPDX mapping) when the `parameters` entry is there, a **gap** for PyTorch classic, Keras, HDF5, NumPy, fastText, a GGUF split over files or with no tensors (a vocabulary-only file), a stub, a count rejected with a `WARNING:` and a Hub model with no Safetensors or GGUF metadata (a model card's prose may state it: a fragment can add the `parameters` entry, which a base entry with another value beats, with a `WARNING: Merge: ELEMENT=<spdx-id>: <property> key <entry-key> differs; kept <kept>, dropped <dropped> [fragment-conflict]`; never type the count note, the merge adds it; say in the provenance `comment` that it is the card's figure; `examples.md`, "Model producer") |
| Model input-output properties | `ai_informationAboutApplication` (JSON string): the signature the format states (ONNX, Keras and HDF5 inputs; ONNX and PT2 inputs and outputs; PT2 only its user inputs and outputs), and the outputs a fastText or CRFsuite model's format fixes (its labels; `Method: derived_from_format`). Weights are never written as inputs: not for Safetensors or NumPy, nor PT2 parameters. It is not an intended-use or preprocessing statement, though `MDL-006.4`, `MDL-010.4` and `SLP-008.3` read it as one | conditional; **gap** for Safetensors, NumPy, GGUF, PyTorch classic and the Hub; no format yields `intended_use` today. On a project base a fragment's different text replaces a `derived_from_format` one whole (one `INFO: Merge: ELEMENT=<spdx-id>: <property> generated from the model file replaced by a fragment's; kept <kept>, dropped <dropped> [generated-value-conflict]`) |
| Model training properties | not modelled (`ai_typeOfModel` is the closest overlap) | **gap** -- ask/read for the training technique (pre-training, fine-tuning, RLHF, ...); `MDL-011` is `present` from `ai_typeOfModel` alone, which is no answer |
| Model license | a `hasDeclaredLicense` relationship on the AI package to a `LicenseExpression` (a valid SPDX id, or a `LicenseRef-` mapped to a `SimpleLicensingText`), as for the main package; a Hugging Face card `license: unknown` is the `NoAssertionLicense` individual; source is the model file (ONNX `model_license`, PT2 `extra/license`, GGUF `general.license`, Safetensors `modelspec.license` else `license`), the Hugging Face card, or local model-card enrichment (`enrich/readme.py`) | conditional (the checker reads `hasDeclaredLicense` only) -- **gap** only when none of those carry a licence; then fill it with `sbom-enrich`'s steps 2-6 |
| Model external references | `externalRef` (arXiv as `documentation`, hub page as `altWebPage`) and DOI as `ExternalIdentifier`, when the source carries them | conditional; **gap** when it carries none |

### Dataset Properties cluster

Applies to each `dataset_DatasetPackage`, only when an `ai_AIPackage` is
present (the G7 checklist is additive).

Checker rules `BOM-G7AI2026-DP-001` to `-010` (23 with sub-rules; `DP-003.1`
domain, `.2` format, `DP-006.4` synthetic method, `DP-008.2`/`.3` copyright and
sensitive category are `out-of-scope`). A rule marked *any-of* is `present` when
any sub-rule is. It reads: `DP-001` `name`; `DP-002` *any-of* lifecycle role (a
`trainedOn`/`testedOn` pointing at the dataset), `dataset_datasetAvailability`,
`dataset_confidentialityLevel`; `DP-003` *any-of* `dataset_datasetType`
(`noAssertion` does not count); `DP-004` `software_packageUrl`, an
`externalIdentifier` or `software_contentIdentifier`; `DP-005` `verifiedUsing`
on the package; `DP-006` *any-of* `originatedBy`,
`dataset_dataCollectionProcess`, `dataset_dataPreprocessing`; `DP-007`
`dataset_datasetSize` (bytes) or `dataset_knownBias` (a Croissant record count
is not recorded and does not satisfy it: SPDX 3.0.1 has no property for one);
`DP-008` *any-of* `dataset_hasSensitivePersonalInformation` or
`dataset_anonymizationMethodUsed`; `DP-009` `dependsOn` or `descendantOf` from
the dataset; `DP-010` `hasDeclaredLicense` only. Verified on Pitloom 0.21.0
(checker `82a63b9`, 2026-10-23; the expected tables are unchanged at the current
pin `2355afc`) with a mocked and a real Hugging Face model with Hub datasets, a
library-built model with a dataset and a `loom.run` fragment with a local
Croissant file (see the note in [`minimum-elements.md`](minimum-elements.md)). A
Croissant file is read only by `loom.run` (`croissant=`) and the library's
`read_croissant()` (alias `read_dataset()`), never from a project directory or a
Hub dataset.

| Element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Dataset name | `dataset_DatasetPackage.name` | covered |
| Dataset description | `description`, when the source carries one: a Croissant file, or the first prose paragraph of a Hugging Face dataset card (for a dataset a Hub model card lists, looked up with the model); a dataset named only in a local model card gets a name, nothing more | conditional |
| Dataset content | `dataset_datasetType`, `dataset_dataPreprocessing` | covered when a Croissant file or a library caller declares them (type defaults to `noAssertion`, which `DP-003` does not count: every Hub dataset gets it); finer content description (format, structure) is a **gap** |
| Dataset identifier | `software_packageUrl` `pkg:generic/<name>[@<version>]?download_url=<url>` when the download URL is http(s); `software_downloadLocation` and `software_packageVersion` when known (a Hub dataset's version is its repository's commit hash; the `spdxId` is internal) | conditional; **gap** for a dataset with no http(s) download URL |
| Dataset hash | none on a `dataset_DatasetPackage` found in a project or model card (no `verifiedUsing`, `dataset.py`); a dataset file scanned as a project file carries its SHA-256 and SHA-512 on its own `software_File`. A `loom.run` dataset carries one when it exists on disk and is within `max-dataset-hash-bytes`: a file's SHA-256 and SHA-512 (and `contains` that file's `software_File`), or a directory's SHA-256 Merkle root over its files' paths and content, commented as such | **gap** at package level outside `loom.run`; the hash is already on the linked `software_File` when the file ships with the project; a directory's Merkle root is not a hash of a single artefact |
| Dataset provenance | `dataset_dataCollectionProcess` (free text), creator as a `publishedBy` relationship to an `Agent` (a Croissant creator, a library caller's `creator`, or a Hub dataset's repository owner, its provenance `Method: repository_owner`; `DP-006.1` reads `originatedBy`, so this creator never satisfies it), and `trainedOn`/`testedOn` relationships to the model, when the relationship exists (the collection process only from a Croissant file) | conditional -- origin/lineage beyond that is a **gap** -- the classic `sbom-enrich` prose-inference target |
| Dataset statistical properties | `dataset_datasetSize` (size in bytes; set for a `loom` single-file dataset unless it is an unpulled Git LFS pointer (or an over-cap file under 1,024 bytes), else only by a library caller's `byte_size`) and `dataset_knownBias` (a Croissant file's `rai:dataBiases`); `DP-007` reads either. A Croissant record count is not recorded and never copied into `dataset_datasetSize` | **gap** unless a size or known biases is declared (a `loom` single-file dataset has its size, unless it is an unpulled Git LFS pointer (or an over-cap file under 1,024 bytes)); else ask once for the dataset's size in bytes or its known biases; non-interactively leave `DP-007` missing and report the gap. Generally **not automatable** without the user running their own analysis |
| Dataset sensitivity | `dataset_hasSensitivePersonalInformation` (what `DP-008.1` reads, with `dataset_anonymizationMethodUsed`), when a Croissant file declares `rai:personalSensitiveInformation`; `dataset_anonymizationMethodUsed` and `dataset_intendedUse` only when a library caller sets them (no reader fills them) | conditional -- when the source is silent, ask the user directly (PII/copyright/sensitive-data flags are not derivable from files alone) |
| Dataset dependency relationship | `trainedOn` / `testedOn` from the model to the dataset (a Hub or local model card's `datasets:` list or a GGUF file's `general.datasets`/`general.dataset.<id>.*`, as `trainedOn`, or `loom.run`: `add_dataset()` is `trainedOn` in a `set_model()` run and `testedOn` in a `use_model()` run, `add_validation_dataset()` `testedOn`); references to one dataset (a Hub id in any case, from any of these) give one dataset package with one relationship per role, a later reference filling only fields still unset; `loom.run` also records `hasInput` from an output dataset to the input datasets it came from, and `generates` from its script to its outputs. The checker follows `trainedOn`/`testedOn`, so a dataset linked this way is judged by every standard, but `DP-009` reads a `dependsOn`/`descendantOf` from the dataset, which Pitloom never writes: it stays `missing` | conditional -- **gap** for a dataset no source links to its model; `DP-009` a **gap** always |
| Dataset license | a `hasDeclaredLicense` Relationship (`hasConcludedLicense` for a licence with no source named, which `DP-010` does not count) from the dataset to a licence element, when the dataset metadata states a licence. Two kinds of dataset get one from a reader. A `loom.run` dataset: from its `declared_license=`, its local Croissant file (`croissant=`), or a directory dataset's `README.md` card frontmatter (`license`; `other` with `license_name`/`license_link`); a source's `unknown`, `NOASSERTION`, blank or bare `other` gives none, and so does the caller's own `unknown`, blank or bare `other` (the next source may then state one); only the caller's `declared_license="NOASSERTION"` (any case) is written, as the `NoAssertionLicense` individual, and a `declared_license=` on any call beats every Croissant file and card (of two declared, the first call's). A source's list of several licences gives one relationship each (in order, once each; a bare `other` in it gives none) and a dataset package `comment` that the source does not say whether they combine as AND or OR: do not merge them into one expression without evidence. A dataset a Hugging Face model card lists: from its Hub dataset card's `license`, by the same rules (up to 20 datasets, only when the model is looked up; a failed request is a `WARNING:` and the dataset keeps its name) | conditional; **gap** for a dataset named only in a local model card, or whose card states none: check its Croissant file/card, then fill via fragment |

### What the checker reads (Models, System Level Properties)

A rule marked *any-of* is `present` when any of its sub-rules is, and reads no
property of its own.

- `MDL-006` model description, *any-of*: `.1` capability reads `summary`, `.2`
  limitation `ai_limitation`, `.3` lineage `descendantOf`, `.4` intended use
  `ai_informationAboutApplication`. `description` is not read: a model with a
  description and none of these four is `missing`.
- `MDL-009` properties, *any-of*: `.1` type `ai_typeOfModel`, `.4`
  hyperparameters `ai_hyperparameter`; `.2` architecture and `.3` parameter
  count are `out-of-scope` (the `parameters` entry is never judged).
- `MDL-010` input-output, *any-of*: `.4` preprocessing reads
  `ai_informationAboutApplication`; `.1` to `.3` (modality, context length) are
  `out-of-scope`.
- `MDL-011` training, *any-of*: `.1` learning type reads `ai_typeOfModel` or
  `ai_informationAboutTraining`, so it is `present` for any model with a type
  although a type is not a training technique; `.2` is `out-of-scope`.
- Direct reads on the package: `MDL-001` name; `-002` identifier
  (`software_packageUrl`, an `externalIdentifier` or
  `software_contentIdentifier`); `-003` `software_packageVersion`; `-004`
  `builtTime` or `releaseTime`; `-005` `originatedBy`; `-007`/`-008`
  `verifiedUsing` on the `ai_AIPackage` itself (the linked `software_File`'s
  hash does not count); `-012` `hasDeclaredLicense` only (a concluded licence
  does not count); `-013` any `externalRef` (a DOI `ExternalIdentifier` alone
  does not).

### System Level Properties

The checker reads the SBOM's roots as "the system": the `rootElement` of each
`software_Sbom` the document names. When those are a single AI model (a `loom
model` SBOM), these rules read that model (the report names it,
`systemJudgedByModel`). A project SBOM that ships a model names a `source`
`software_Sbom` rooted at the project's package and a `build` one rooted at the
model, so each rule must hold for both, and a finding names whichever misses
(`SLP-003` names the model when only the project declares authors). Rules:
`SLP-001` name; `-002` a `contains`/`dependsOn` from the system; `-003`
`originatedBy`; `-004` `software_packageVersion`; `-005` `builtTime` (the main
package, only in a Hatchling hook build) or `releaseTime` (a Hub model); `-007`
data usage reads `ai_useSensitivePersonalInformation` (Pitloom writes none);
`-008` input-output, *any-of*, `.3` preprocessing reads
`ai_informationAboutApplication`; `-009` application area reads `ai_domain`
(a fastText model's, derived from the format, which a fragment's different
domain replaces on a project base; a Hub model's pipeline tag); `-006` data flow
is `out-of-scope`. Data flow, data usage, application area and system
input-output are mostly **gaps** to fill from the user, not from repo content.

### Infrastructure, Security Properties, KPI clusters

Not modelled by Pitloom, and with one exception not checked:
`INF-001`/`-002`, `SP-001`, `-003`, `-004` and `KPI-001`/`-002` are
`out-of-scope`; `SP-002` security compliance reads `ai_standardCompliance` on
the system (Pitloom writes none, so it is `missing`). Every element here is a
**gap**, and the Security and KPI ones are largely **not automatable** from repo
content: they describe the deployed system's posture, not the model artefact.
Lowest priority: pursue them only when the user asks for full G7 coverage, and
expect most to stay open gaps.
