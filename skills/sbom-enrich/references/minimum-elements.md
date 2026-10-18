---
Created: 2026-08-12
Last-Modified: 2026-10-18
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM minimum elements checklists

See also: [`minimum-elements-bsi.md`](minimum-elements-bsi.md) (BSI),
[`minimum-elements-questions.md`](minimum-elements-questions.md) (the
question bank for elements that cannot be derived).

Companion to
[`../SKILL.md`](https://github.com/bact/pitloom/blob/main/skills/sbom-enrich/SKILL.md)'s
"Complete a standard's minimum elements" section. Five checklists -- NTIA 2021,
FSCT 2024, CISA 2026, G7 SBOM for AI 2026 and BSI TR-03183-2 v2.1 -- each
mapped to the Pitloom/SPDX 3 field that carries it today, so the agent can tell
a real gap from something the base SBOM already covers before asking the user
anything. See also `minimum-elements-workflow.md` (step detail, and how to run
and read the optional checker).

**Which checklist applies:** CISA 2026 *supersedes* NTIA 2021 (same core
principles, renamed/split/added fields -- see the "2021 name" column below) and
is the current baseline unless the user specifically asks for another one (e.g.
an older contract or policy cites NTIA 2021 by name). FSCT 2024 (CISA's
*Framing Software Component Transparency*, third edition) and BSI TR-03183-2
(the German BSI technical guideline) apply only when named. G7 SBOM for AI 2026
is **additive** -- apply it only when the base SBOM has an `ai_AIPackage`
element, on top of whichever general checklist applies.

**Checker ids** (`sbomcheck -s spdx3 -c <id>`, see
`minimum-elements-workflow.md`): `ntia`, `fsct3`, `cisa2026`, `g7ai`, `bsi`.
The checker's `present` means the property it looks for exists, not that its
value is right or that the standard's intent is met (NTIA's and CISA's author
rules accept Pitloom's own software-agent creator, for example). The FSCT 2024
and CISA 2026 component rules judge every package reachable from the SBOM root
through composition and dependency relationships, plus datasets and models
linked by `trainedOn`/`testedOn`; BSI follows composition and dependency
relationships only (a dataset linked only by `trainedOn` is not judged, and the
checker logs it as a floating element).

Status legend: **covered** -- Pitloom emits this deterministically, nothing to
do. **conditional** -- emitted only when a dependency resolves against
PyPI/installed metadata, or similar; verify per-run, don't assume. **gap** --
this workflow's actual job. **not automatable** -- no file or answer this
workflow can gather will satisfy it; say so plainly rather than implying it can
be filled.

The "covered"/"conditional"/"gap" calls below were re-checked on 2026-09-20
against the assembly code (`assemble/spdx3/_ai_package.py`, `ai.py`,
`dataset.py`, `document.py`) and a fresh `loom project`/`loom model` run -- not
against a single sample SBOM, which misses fields the sample's model format
never carried. The model producer and parameter-count rows were re-checked on
2026-10-15 against the readers, `assemble/spdx3/_ai_originators.py`, the
fragment merge (`_fragments_props.py`) and real `loom model`/`loom project` runs
with a merged fragment. The FSCT 2024 and BSI tables, the checker notes and
the hash rows were checked on 2026-10-18 with Pitloom 0.20.2 and the checker
pin of Pitloom's `conformance` group, on ONNX, Safetensors and GGUF test
models, a small Hatchling project and a `uv.lock` project, online and
`--offline`. Re-verify if the assembly code has changed since.

## NTIA 2021 (7 data fields + 6 practices)

Field names below are the 2021 originals; CISA 2026's Appendix B documents each
rename.

| 2021 element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Supplier Name | dependency: `originatedBy` -> `Agent` via `_apply_originator`/PyPI JSON API (`deps_originator.py`, called from `deps.py`'s `_enrich_from_pypi`); main package: `originatedBy` -> one `Agent` per `[project].authors` entry (covered when authors are declared), and `software_Package.suppliedBy`, only set when `[[tool.pitloom.creator]]` is configured (`document.py`'s `_build_main_package`) | conditional (deps, PyPI-resolvable only); main package: **covered** by `originatedBy` when authors are declared, a **gap** for `suppliedBy` unless `[[tool.pitloom.creator]]` is set -- same config also fixes `Author of SBOM Data` below, see the note there; an AI model: `originatedBy` from structured fields, and `suppliedBy` on the Hugging Face route only (the repository owner), never from a model file (see G7 "Model producer" below) |
| Component Name | `software_Package.name` / `ai_AIPackage.name` | covered |
| Version of the Component | `software_packageVersion` (explicit `"unknown"` string when not resolvable -- already matches the 2021/2026 "indicate unknown" guidance) | covered |
| Other Unique Identifiers | `software_packageUrl` (PURL); main package always, deps only when resolvable | conditional |
| Dependency Relationship | `Relationship`/`LifecycleScopedRelationship` (`contains`, `dependsOn` with scope `runtime`, `hasOptionalDependency` for extras, `hasDataFile`, `generates`, etc.) | covered |
| Author of SBOM Data | `CreationInfo.createdBy` -> `SoftwareAgent` named "Pitloom" (the *tool*, not a person/org) unless `[[tool.pitloom.creator]]` is configured | **gap** unless the project configures `[[tool.pitloom.creator]]` -- check that first before asking the user. **One config answers two elements at once:** the same creator Agent also becomes the main package's `suppliedBy` (`document.py`: "so only assert it for a real named creator -- not for the default SoftwareAgent 'Pitloom', which is the SBOM tool, not the package's supplier"), so this single fix closes both `Author of SBOM Data`/`SBOM Author` *and* the main package's `suppliedBy` in one answer (its `originatedBy` is already set when the project declares authors) -- lead with this when ranking gaps by effort-to-impact |
| Timestamp | `CreationInfo.created` | covered |

Checker (`-c ntia`, rules `BOM-NTIA2021-DF-001` to `-007`, in the table's
order: supplier, name, version, identifier, dependency relationship, author,
timestamp): the supplier rule reads `suppliedBy` on every package, so it is
missing for a model file, for dependencies (Pitloom sets no `suppliedBy` on
them) and for the main package without `[[tool.pitloom.creator]]`; the author
rule accepts the default `Pitloom` software agent; the dependency rule is
document-level, missing for a single-model SBOM.

Practices (process expectations, not data fields -- report as satisfied/not by
observation, nothing to draft a fragment for): Depth (Pitloom's dependency graph
has no fixed depth limit -- covered), Known Unknowns (Pitloom's `"unknown"`
string convention -- covered), Distribution and Access Control (deployment
concern, out of scope), Accommodation of Mistakes (re-run `loom` to regenerate
-- covered), Automation Support (SPDX 3 JSON-LD is machine-processable --
covered), Frequency (deployment/process concern, out of scope).

## FSCT 2024 (baseline attributes, minimum expected level; checker `fsct3`)

Rule ids are `BOM-FSCT2024-<id>`. "Pitloom" says what a default run writes,
checked with `loom model`/`loom generate` and `sbomcheck -c fsct3` on
2026-10-18.

| Id | Element | SPDX 3 field the checker reads | Pitloom | Checked |
| :--- | :--- | :--- | :--- | :--- |
| META-001 | Author Name | `CreationInfo.createdBy` | fills (the default `Pitloom` software agent counts; FSCT means the SBOM's author, so name a person or organisation: `--creator-name`/`--creator-type`/`--creator-email` or `[[tool.pitloom.creator]]`) | yes |
| META-002 | Timestamp | `CreationInfo.created` | fills | yes |
| META-003 | SBOM Type | `software_sbomType` | fills | yes |
| META-004 | Primary Component | `rootElement` | fills (the `software_Sbom` names the root package or model) | no (`out-of-scope`) |
| META-005 | Dependency Relationship | one `contains`/`dependsOn`/`hasStaticLink`/`hasDynamicLink` anywhere | fills for a project (its `contains` links); none in a single-model SBOM, and a `loom model` base merges no fragment | yes |
| COMP-001 | Component Name | `name` | fills | yes |
| COMP-002 | Version | `software_packageVersion` | the main package and lock- or PyPI-resolved dependencies; a model only when its format states one (see G7 "Model version"); a dataset only when its source states one | yes |
| COMP-003 | Supplier Name | `suppliedBy` | the main package only with `[[tool.pitloom.creator]]` or `--creator-*` (that creator becomes its supplier); a Hugging Face model (its owner); never a dependency, a model file or a model in a project: the user must supply it | yes |
| COMP-004 | Unique Identifier | `software_packageUrl`, `software_contentIdentifier` or a packageUrl/cpe/swid/swhid/gitoid `externalIdentifier` | fills (a PURL on every package; a dataset needs an http(s) download URL) | yes |
| COMP-005 | Cryptographic Hash | `verifiedUsing` | see CISA's hash row | no |
| COMP-006 | Relationship (per component, with completeness) | -- | Pitloom writes no `completeness` | no |
| COMP-007 | License | `hasConcludedLicense` only | a dependency's licence from PyPI or its installed copy; never the project's own stated licence, which is `hasDeclaredLicense`: the user can conclude it by fragment | yes |
| COMP-008 | Copyright Notice | `software_copyrightText` (`NOASSERTION` counts as missing) | the main package when its `LICENSE` carries copyright lines; a dependency often `NOASSERTION`; a model none | yes |

## CISA 2026 (current baseline; 10 metadata + 7 component fields + 6 practices)

### SBOM Metadata

| Element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| SBOM Author | see NTIA 2021's "Author of SBOM Data" row above -- same gap, same one-config fix | **gap** unless `[[tool.pitloom.creator]]` configured |
| SBOM Author Signature | none | **not automatable** -- needs the project's own signing infrastructure (NIST SP 800-57 Pt. 1); ask whether one exists, don't attempt to fake it |
| SBOM Data Format Name | implicit: `@context` is the SPDX 3 JSON-LD context | covered (self-describing by format, no explicit field needed) |
| SBOM Data Format Version | `CreationInfo.specVersion` (e.g. `"3.0.1"`) | covered |
| SBOM Generation Context | `software_Sbom.software_sbomType` (`source`/`build`/`analyzed`/`deployed`/`runtime` -- CISA 2026's own examples, "before build"/"build"/"after build", map onto this enum) | covered |
| SBOM Timestamp | `CreationInfo.created` | covered |
| SBOM Tool Name | `Tool.name` (e.g. `"Pitloom"`) | covered |
| SBOM Tool Version | embedded in `Tool.summary` (e.g. `"Pitloom 0.12.0"`) -- a free-text string, not a discrete version property, because **SPDX 3.0.1 itself has no native `Tool.version` property** (`creation_info.py`'s docstring: added in 3.1-dev; the `summary` text is Pitloom's deliberate workaround, same pattern used for enrichment-run tools) | covered, but only as embedded text -- if a consumer needs a structured field this is a spec-version limitation, not something a fragment can fix |
| SBOM Version | none -- no field tracks a version for the SBOM document itself, distinct from the tool's version | **gap**, and not one this workflow can fill safely (the SBOM author would need to adopt a real versioning scheme for their SBOM outputs, not just answer a question once) -- report as unaddressed, don't fabricate a `"1.0"` |
| SBOM Dependency Relationship | see Component Dependency Relationship below -- same field, same coverage | covered |

### Component Data

| Element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Component Producer | dependency: `originatedBy` via `_apply_originator` (`deps_originator.py`) from PyPI JSON API; main package: `originatedBy` from `[project].authors`, and `suppliedBy` only when `[[tool.pitloom.creator]]` is configured; an AI model: `originatedBy`, see G7 "Model producer" below | conditional (deps, PyPI-resolvable only); main package **covered** when authors are declared -- see NTIA's "Supplier Name" row above |
| Component Dependency Relationship | `Relationship`/`LifecycleScopedRelationship` | covered |
| Component Hash Value / Algorithm | `verifiedUsing` (`{"algorithm": "sha256", "hashValue": ...}`, plus a `sha512` entry on a file Pitloom reads itself); set on every `software_File` (including dataset and model files), lock-file-resolved dependencies (via SHA-256 digests in supported lock files, taking priority and applied in both online and offline builds), and PyPI-resolved deps (`_extract_release_hash` fallback, `deps_pypi.py`). The main package carries the SHA-256 Merkle root over its files (`document.py`; commented as not a single-artefact hash) on every `project` (directory), wheel and embed SBOM that has payload files (the wheel's own `.dist-info` is excluded); **not** set on sdist SBOMs, on an `ai_AIPackage` whose model file Pitloom did not read (a Hugging Face model), or on `dataset_DatasetPackage` elements outside `loom.run` | conditional -- present on deps only when a definite version resolves; on the main package, check the SBOM rather than assuming (Merkle root, not an artefact hash); the AI/dataset package-level gaps are listed under G7 below |
| Component Identifiers | `software_packageUrl` (PURL) | conditional, same as NTIA's "Other Unique Identifiers" |
| Component License | `simplelicensing_LicenseExpression` (valid SPDX expression) or `simplelicensing_SimpleLicensingText` (other text) + `hasDeclaredLicense`/`hasConcludedLicense` relationship (main package, from `project.license`, then its `License ::` classifiers; a single value is declared when the package states it, including a `loom env` package's own installed metadata, and concluded when it is a third-party record: PyPI, or a project dependency's installed copy; beside a stated licence, the project directory's detection is concluded, as is a library caller's `license_concluded`); deps from installed metadata, then installed classifiers, then the PyPI JSON API (`_extract_pypi_license`). No licence stated = **no relationship**; `NoAssertionLicense`/`NoneLicense` individuals only when a source said `NOASSERTION`/`UNKNOWN`/`NONE` | conditional (deps: installed or PyPI-resolvable only); main package usually covered when `pyproject.toml` declares a licence; a missing relationship is a **gap** |
| Component Name | `software_Package.name` | covered |
| Component Version | `software_packageVersion` | covered |

### Practices and Processes

Mostly process observations, not fields to fill: Accommodation of Updates to
SBOM Data (re-run `loom` -- covered), Coverage (Pitloom walks the full
dependency graph -- covered, but a mixed-ecosystem project has real gaps outside
Python; see `sbom-generate`'s "Known limitations"), Distribution and Delivery
(deployment concern, out of scope), Explicitly Identifying Unknown Information
(Pitloom's `"unknown"` placeholder and, for a licence a source itself calls
unknown, the `NoAssertionLicense` individual -- covered; an unstated licence has
no relationship, and this workflow's final report should follow the same
convention for anything the user declines to answer), Frequency (process
concern, out of scope), Machine-Processable Data (SPDX 3 JSON-LD -- covered).

### Checker (`-c cisa2026`, rules `BOM-CISA2026-<id>`)

14 of 23 rules are checked: META-001 author (`createdBy`, any value, so the
default software agent passes), META-003/-004 format name and version
(`specVersion`), META-005 generation context, META-006 timestamp, META-007 tool
name (`createdUsing`), COMP-001 producer (`originatedBy` on every package),
COMP-002 dependency relationship (document-level), COMP-003/-004 hash
(any `Hash` with a value, so the main package's Merkle root passes), COMP-005
identifiers, COMP-006 licence (`hasDeclaredLicense` only: a dependency with
only a PyPI-concluded licence is missing), COMP-007 name, COMP-008 version.
`out-of-scope`: META-002 signature, META-008 tool version, META-009 SBOM
version, PP-001 to PP-006. On a default run the usual misses are COMP-001 for
a model and a dataset, COMP-006 for dependencies and models, COMP-008 for a
model file, and COMP-003/-004 for a Hugging Face model or a dataset with no
hash.

## G7 SBOM for AI 2026 (additive -- apply only when an `ai_AIPackage` is present)

Checker `g7ai`: 81 rules (`BOM-G7AI2026-<id>`), 25 of them `out-of-scope`;
how much a default run fills, per cluster and model source: Pitloom's "G7 SBOM
for AI" page (<https://bact.github.io/pitloom/g7-sbom-for-ai/>).

### Models cluster

| Element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Model name | `ai_AIPackage.name` | covered (cut to 1024 characters with `...~<digest>`, controls shown as `\uXXXX`: a cap, not a gap); **gap** when `name` is only the file's stem (`Method: file_name_stem`: a stub, or a format with no name field; see `sbom-enrich`, step 3) |
| Model identifier | `software_packageUrl`: `pkg:huggingface/<owner>/<name>[@<commit>]` for a Hub model, else `pkg:generic/<file>?checksum=sha256:<digest>` for a hashed model file; DOI as `ExternalIdentifier` (type `other`) and the hub page as an `altWebPage` `externalRef`, when the source carries them | conditional; **gap** for a model with no file, no hub id and no DOI |
| Model version | `software_packageVersion`, when the format carries one (GGUF, ONNX `model_version`, PT2 `extra/model_version`, Safetensors `modelspec.version`/`version`); a Hugging Face model's version is its 40-digit commit hash (when the Hub gives one), so a new revision is a new document | conditional -- verify per model type |
| Model timestamp | `releaseTime` on the AI package: a Hugging Face model's last-modified time (its revision's commit time), when the Hub gives one. `CreationInfo.created` is when the SBOM was made, not the model's time, and does not count | conditional; **gap** for a model file, which carries no time |
| Model producer | `ai_AIPackage.originatedBy` -> one generic `Agent` (name only) per name a structured field states: ONNX `model_author` (a comma-separated list, split on commas), PT2 `extra/author`, GGUF `general.author` then `general.organization`, Safetensors `__metadata__` key `modelspec.author` (one name), the Hugging Face repository owner (`Method: repository_owner`). `suppliedBy` is set only on the Hugging Face route, to that repository owner (the same `Agent` as in `originatedBy`; the Hub repository is the distribution source; single-valued, so one owner); no model file format sets it. A model never inherits the main package's `suppliedBy`. A re-upload, quantisation or fine-tune names its uploader on both: the base model is a `descendantOf` edge, which records lineage only, so the original maker is a question for the card or the user. A GGUF `general.organization` is often guessed by the llama.cpp converter from the base model's `_name_or_path`, so it can name the base model's organisation (read as stated; the Hub route names the owner instead). PyTorch classic, Keras, HDF5, NumPy, fastText and CRFsuite carry none | conditional -- check `originatedBy` first; **gap** when the format has no author field, it is empty, or the model is a stub (`sbom-enrich`, step 3). The `Agent` says nothing of person vs organisation: when the model card states which, or names a producer the file does not, add a `Person`/`Organization` to `originatedBy` by fragment; a merge unions lists, so the generic `Agent` stays beside it and cannot be removed or retyped (recipe and merge behaviour: `examples.md`, "Model producer") |
| Model description | `ai_AIPackage.description`, when the format/source carries one (GGUF, ONNX, PT2, Safetensors, Hugging Face; distinct from the *main* `software_Package.description`). A CRFsuite model's description is Pitloom's own summary of its labels (`Method: generated_from_labels`), not the producer's | conditional -- verify per model type; a `generated_from_labels` description is a **gap** for a producer-written one; none at all when a label was over 4 KiB (a cap, see `sbom-generate`) |
| Model hash value / algorithm | `verifiedUsing` (`{"algorithm": "sha256", ...}` and `sha512`) on the `ai_AIPackage`, the model file's SHA-256 and SHA-512 (project, wheel, embed-wheel, hook, `model`, `loom.run` with `path=`); the linked `software_File` carries the same hash. A model read from Hugging Face, or declared without a file, has none | covered when a model file was read; **gap** for a pathless model. A fragment adds no `AIPackage` of its own, so it never supplies this hash |
| Model properties (architecture, parameter count, etc.) | `ai_typeOfModel` (type + architecture) and `ai_hyperparameter` (list of `DictionaryEntry`, incl. quantisation). The parameter count is the entry with key `parameters`, a decimal integer as text: SPDX 3.0.1 has no model-size property, so this entry is only the carrier, not a real hyperparameter (the package `comment` says so). Pitloom sums the tensor element counts of GGUF, Safetensors and ONNX files (`Method: tensor_element_sum` in the provenance) and takes the Hub's own sum (`safetensors.total`, else `gguf.total`, same method) for a Hugging Face model. It counts all stored tensors (buffers and tied weights included; packed or quantised weights under-count), so it is not a trainable-parameter figure: <https://bact.github.io/pitloom/ai-model-formats/#what-the-count-counts> | covered for architecture/type/hyperparameters; parameter count covered by convention (SPDX has no parameter-count field; a G7 'GAP' in the bact mapping, which only gives a `broadMatch` to `ai_hyperparameter`) when the `parameters` entry is there, a **gap** for PT2, PyTorch classic, Keras, HDF5, NumPy, fastText, CRFsuite, a GGUF split over files, a stub, a count rejected with a `WARNING:` and a Hub model with no Safetensors or GGUF metadata (a model card's prose may state it: a fragment can add the `parameters` entry, which a base entry always beats, silently; the merge adds the package's count note itself, so never type it: say in the provenance `comment` that the entry is the card's figure, not a sum of tensor elements; `examples.md`, "Model producer") |
| Model input-output properties | `ai_informationAboutApplication` (JSON string): the signature the format states (ONNX, Keras and HDF5 inputs; ONNX and PT2 inputs and outputs; PT2 only its user inputs and outputs). Weights are never written as inputs: not for Safetensors or NumPy, nor PT2 parameters. It is not an intended-use or preprocessing statement, whatever a checker's property mapping says | conditional; **gap** for Safetensors, NumPy, GGUF, PyTorch and the Hub; no format yields `intended_use` today |
| Model training properties | not distinctly modelled (see `ai_typeOfModel` for the closest overlap) | **gap** -- ask/read for training technique detail (pre-training vs. fine-tuning vs. RLHF, etc.) |
| Model license | licence relationships (declared/concluded) on the AI package -- a `LicenseExpression` for a valid SPDX id, else a `SimpleLicensingText` -- built by the same `build_license_elements` as the main package; a Hugging Face card `license: unknown` is the `NoAssertionLicense` individual; source is the model file (ONNX `model_license`, PT2 `extra/license`, GGUF `general.license`; Safetensors licence keys are not mapped), the Hugging Face card, or local model-card enrichment (`enrich/readme.py`) | conditional -- **gap** only when none of those carry a licence; then `sbom-enrich`'s prose-inference steps (2-6) are the way to fill it, reuse them rather than re-deriving |
| Model external references | `externalRef` (arXiv as `documentation`, hub page as `altWebPage`) and DOI as `ExternalIdentifier`, when the source carries them | conditional; **gap** when it carries none |

### Dataset Properties cluster

Applies to each `dataset_DatasetPackage`.

| Element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Dataset name | `dataset_DatasetPackage.name` | covered |
| Dataset description | `description`, when the source (Croissant) carries one; datasets named only in a model card or Hugging Face metadata get a name and download URL, nothing more | conditional |
| Dataset content | `dataset_datasetType`, `dataset_dataPreprocessing`, `dataset_datasetSize` (record count) | covered when a Croissant file declares them (type defaults to `noAssertion`); finer content description (format, structure) is a **gap** |
| Dataset identifier | `software_packageUrl` `pkg:generic/<name>[@<version>]?download_url=<url>` when the download URL is http(s); `software_downloadLocation` and `software_packageVersion` when known (the `spdxId` is internal) | conditional; **gap** for a dataset with no http(s) download URL |
| Dataset hash | none on a `dataset_DatasetPackage` found in a project or model card (no `verifiedUsing`, `dataset.py`); a dataset file scanned as a project file carries its SHA-256 on its own `software_File`. A `loom.run` dataset carries one when it exists on disk and is within `max-dataset-hash-bytes`: a file's SHA-256 (and `contains` that file's `software_File`), or a directory's SHA-256 Merkle root over its files' paths and content, commented as such | **gap** at package level outside `loom.run`; the hash is already on the linked `software_File` when the file ships with the project; a directory's Merkle root is not a hash of a single artefact |
| Dataset provenance | `dataset_dataCollectionProcess` (free text), creator as a `publishedBy` `Agent`, and `trainedOn`/`testedOn` relationships to the model, when the relationship exists (the fields themselves only from a Croissant file) | conditional -- origin/lineage beyond that is a **gap** -- the classic `sbom-enrich` prose-inference target |
| Dataset statistical properties | `dataset_datasetSize` only | **gap** for anything beyond record count, generally **not automatable** without the user running their own analysis |
| Dataset sensitivity | `dataset_hasSensitivePersonalInformation`, `dataset_anonymizationMethodUsed`, `dataset_knownBias`, `dataset_intendedUse`, when a Croissant file declares them | conditional -- when the source is silent, ask the user directly (PII/copyright/sensitive-data flags are not derivable from files alone) |
| Dataset dependency relationship | `Relationship` (`generates`, `hasDataFile`) captures pipeline-derivation edges already | covered for pipeline-derived datasets |
| Dataset license | a `hasDeclaredLicense` Relationship (`hasConcludedLicense` for a third-party record) from the dataset to a licence element, when the dataset metadata states a licence; no reader feeds a licence into a model SBOM yet (Croissant is library-only, Hub dataset references carry none) | conditional; **gap** for most datasets: check the dataset's Croissant file/card, then fill via fragment |

### System Level Properties

Partly covered. The checker reads the SBOM's root package as "the system". When
the SBOM's one root is a single AI model and nothing else, these rules read that
model (the report names it, `systemJudgedByModel`). A project that ships a model
has a root of its own and is not judged by the model it contains: most of these
rules are missing for it until the user supplies the system's details. Name,
version, producer and timestamp come from the model or the root package where
stated. Data flow,
data usage, intended application area and system input-output are mostly
**gaps** to fill from the user, not from repo content.

### Infrastructure, Security Properties, KPI clusters

Not modelled by Pitloom's current `ai_AIPackage` mapping at all, and not
checked by the checker -- every element in these three clusters
(Infrastructure software/hardware; Security controls/compliance/policy
info/vulnerability referencing; Security metrics, Operational performance KPIs)
is a **gap**, and several (Security Properties, KPIs) are largely **not
automatable** from repo content alone -- they describe the deployed system's
operational/security posture, not the model artefact. Treat these as the
lowest-priority tier: only pursue them if the user explicitly asks for full G7
coverage, and expect most to end up reported as open gaps rather than filled.

## BSI TR-03183-2 v2.1 (SBOM content, section 5.2; checker `bsi`)

Moved to [`minimum-elements-bsi.md`](minimum-elements-bsi.md): element table, what Pitloom
writes and what the user must supply.

## Optional extra check (not a required step)

The community `ntia-conformance-checker` (`sbomcheck`) checks an SPDX 3
document against all five standards. How to install it, run it and read its
outcomes, and what to do per `missing` rule: `minimum-elements-workflow.md`
("Cross-check with the checker"). It is optional and never replaces the
mandatory `sbom-validate` pass
(<https://github.com/bact/pitloom/blob/main/skills/sbom-validate/SKILL.md>;
minimal fallback: `pip install "pitloom[validate]>=0.20.2"` then
`loom fragment validate <file>`).
