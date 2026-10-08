---
Created: 2026-08-12
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM minimum elements checklists

Companion to
[`../SKILL.md`](https://github.com/bact/pitloom/blob/main/skills/sbom-enrich/SKILL.md)'s
"Complete a standard's minimum elements" section. Three checklists -- NTIA 2021,
CISA 2026, and G7 SBOM for AI 2026 -- each mapped to the Pitloom/SPDX 3 field
that carries it today, so the agent can tell a real gap from something the base
SBOM already covers before asking the user anything.

**Which checklist applies:** CISA 2026 *supersedes* NTIA 2021 (same core
principles, renamed/split/added fields -- see the "2021 name" column below) and
is the current baseline unless the user specifically asks for the 2021 version
(e.g. an older contract or policy cites it by name). G7 SBOM for AI 2026 is
**additive** -- apply it only when the base SBOM has an `ai_AIPackage` element,
on top of whichever general checklist applies.

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
never carried. Re-verify if the assembly code has changed since.

## NTIA 2021 (7 data fields + 6 practices)

Field names below are the 2021 originals; CISA 2026's Appendix B documents each
rename.

| 2021 element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Supplier Name | dependency: `originatedBy` -> `Agent` via `_apply_originator`/PyPI JSON API (`deps_originator.py`, called from `deps.py`'s `_enrich_from_pypi`); main package: `software_Package.suppliedBy`, but only set when `[[tool.pitloom.creator]]` is configured (`document.py`'s `_build_main_package`) | conditional (deps, PyPI-resolvable only); **gap** for the main package unless `[[tool.pitloom.creator]]` is set -- same config also fixes `Author of SBOM Data` below, see the note there. Note the field differs: deps get `originatedBy`, only the main package gets `suppliedBy` |
| Component Name | `software_Package.name` / `ai_AIPackage.name` | covered |
| Version of the Component | `software_packageVersion` (explicit `"unknown"` string when not resolvable -- already matches the 2021/2026 "indicate unknown" guidance) | covered |
| Other Unique Identifiers | `software_packageUrl` (PURL); main package always, deps only when resolvable | conditional |
| Dependency Relationship | `Relationship`/`LifecycleScopedRelationship` (`contains`, `dependsOn`, `hasDataFile`, `generates`, etc.) | covered |
| Author of SBOM Data | `CreationInfo.createdBy` -> `SoftwareAgent` named "Pitloom" (the *tool*, not a person/org) unless `[[tool.pitloom.creator]]` is configured | **gap** unless the project configures `[[tool.pitloom.creator]]` -- check that first before asking the user. **One config answers two elements at once:** the same creator Agent also becomes the main package's `suppliedBy` (`document.py`: "so only assert it for a real named creator -- not for the default SoftwareAgent 'Pitloom', which is the SBOM tool, not the package's supplier"), so this single fix closes both `Author of SBOM Data`/`SBOM Author` *and* `Supplier Name`/`Component Producer` for the main package in one answer -- lead with this when ranking gaps by effort-to-impact |
| Timestamp | `CreationInfo.created` | covered |

Practices (process expectations, not data fields -- report as satisfied/not by
observation, nothing to draft a fragment for): Depth (Pitloom's dependency graph
has no fixed depth limit -- covered), Known Unknowns (Pitloom's `"unknown"`
string convention -- covered), Distribution and Access Control (deployment
concern, out of scope), Accommodation of Mistakes (re-run `loom` to regenerate
-- covered), Automation Support (SPDX 3 JSON-LD is machine-processable --
covered), Frequency (deployment/process concern, out of scope).

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
| Component Producer | dependency: `originatedBy` via `_apply_originator` (`deps_originator.py`) from PyPI JSON API; main package: `software_Package.suppliedBy`, only when `[[tool.pitloom.creator]]` is configured | conditional (deps, PyPI-resolvable only); **gap** for the main package unless `[[tool.pitloom.creator]]` is set -- see NTIA's "Supplier Name" row above |
| Component Dependency Relationship | `Relationship`/`LifecycleScopedRelationship` | covered |
| Component Hash Value / Algorithm | `verifiedUsing` (`{"algorithm": "sha256", "hashValue": ...}`); set on every `software_File` (including dataset and model files), lock-file-resolved dependencies (via SHA-256 digests in supported lock files, taking priority and applied in both online and offline builds), and PyPI-resolved deps (`_extract_release_hash` fallback, `deps_pypi.py`). The main package carries the SHA-256 Merkle root over its files (`document.py`; commented as not a single-artefact hash) on every `project` (directory), wheel and embed SBOM that has payload files (the wheel's own `.dist-info` is excluded); **not** set on sdist SBOMs or `ai_AIPackage`/`dataset_DatasetPackage` elements | conditional -- present on deps only when a definite version resolves; on the main package, check the SBOM rather than assuming (Merkle root, not an artefact hash); the AI/dataset package-level gaps are listed under G7 below |
| Component Identifiers | `software_packageUrl` (PURL) | conditional, same as NTIA's "Other Unique Identifiers" |
| Component License | `simplelicensing_LicenseExpression` (valid SPDX expression) or `simplelicensing_SimpleLicensingText` (other text) + `hasDeclaredLicense`/`hasConcludedLicense` relationship (main package, from `project.license`, then its `License ::` classifiers; a single value is declared when the package states it, including a `loom env` package's own installed metadata, and concluded when it is a third-party record: PyPI, or a project dependency's installed copy; beside a stated licence, the project directory's detection is concluded, as is a library caller's `license_concluded`); deps from installed metadata, then installed classifiers, then the PyPI JSON API (`_extract_pypi_license`). No licence stated = **no relationship**; `NoAssertionLicense`/`NoneLicense` individuals only when a source said `NOASSERTION`/`UNKNOWN`/`NONE` | conditional (deps: installed or PyPI-resolvable only); main package usually covered when `pyproject.toml` declares a license; a missing relationship is a **gap** |
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

## G7 SBOM for AI 2026 (additive -- apply only when an `ai_AIPackage` is present)

### Models cluster

| Element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Model name | `ai_AIPackage.name` | covered (cut to 1024 characters with `...~<digest>`, controls shown as `\uXXXX`: a cap, not a gap); **gap** when `name` is only the file's stem (`Method: file_name_stem`: a stub, or a format with no name field; see `sbom-enrich`, step 3) |
| Model identifier | DOI as `ExternalIdentifier` (type `other`) and the hub page as an `altWebPage` `externalRef`, when the source carries them; no PURL or hub-id identifier | conditional; **gap** when the model has neither a DOI nor a hub page |
| Model version | `software_packageVersion`, when the format carries one (GGUF, ONNX `model_version`, PT2 `extra/model_version`, Safetensors `modelspec.version`/`version`); never from Hugging Face, whose reader sets no version | conditional -- verify per model type |
| Model timestamp | `CreationInfo.created` on the AI package's own `CreationInfo` | covered |
| Model producer | none -- the Hugging Face Hub `author` is captured into `extra_data` only, never emitted as an `Agent` | **gap** |
| Model description | `ai_AIPackage.description`, when the format/source carries one (GGUF, ONNX, PT2, Safetensors, Hugging Face; distinct from the *main* `software_Package.description`). A CRFsuite model's description is Pitloom's own summary of its labels (`Method: generated_from_labels`), not the producer's | conditional -- verify per model type; a `generated_from_labels` description is a **gap** for a producer-written one; none at all when a label was over 4 KiB (a cap, see `sbom-generate`) |
| Model hash value / algorithm | none -- `verifiedUsing` is not set on `ai_AIPackage` (`_build_ai_package`), even though the shipped model file's own `software_File` carries a SHA-256 and is linked by `contains` | **gap** -- do not recompute; the hash is already in the SBOM on the linked `software_File`, so a fragment can reuse it. A core wiring fix is planned, separate from this skill |
| Model properties (architecture, parameter count, etc.) | `ai_typeOfModel` (type + architecture) and `ai_hyperparameter` (list of `DictionaryEntry`, incl. quantization) | covered for architecture/type/hyperparameters; parameter count is a **gap** (not promoted to its own field, even where a format's raw metadata exposes it) |
| Model input-output properties | `ai_informationAboutApplication` (JSON string) | covered when the model format's extractor populates it; verify per model type |
| Model training properties | not distinctly modelled (see `ai_typeOfModel` for the closest overlap) | **gap** -- ask/read for training technique detail (pre-training vs. fine-tuning vs. RLHF, etc.) |
| Model license | licence relationships (declared/concluded) on the AI package -- a `LicenseExpression` for a valid SPDX id, else a `SimpleLicensingText` -- built by the same `build_license_elements` as the main package; a Hugging Face card `license: unknown` is the `NoAssertionLicense` individual; source is the model file (ONNX `model_license`, PT2 `extra/license`, GGUF `general.license`; Safetensors licence keys are not mapped), the Hugging Face card, or local model-card enrichment (`enrich/readme.py`) | conditional -- **gap** only when none of those carry a license; then `sbom-enrich`'s prose-inference steps (2-6) are the way to fill it, reuse them rather than re-deriving |
| Model external references | `externalRef` (arXiv as `documentation`, hub page as `altWebPage`) and DOI as `ExternalIdentifier`, when the source carries them | conditional; **gap** when it carries none |

### Dataset Properties cluster

Applies to each `dataset_DatasetPackage`.

| Element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Dataset name | `dataset_DatasetPackage.name` | covered |
| Dataset description | `description`, when the source (Croissant) carries one; datasets named only in a model card or Hugging Face metadata get a name and download URL, nothing more | conditional |
| Dataset content | `dataset_datasetType`, `dataset_dataPreprocessing`, `dataset_datasetSize` (record count) | covered when a Croissant file declares them (type defaults to `noAssertion`); finer content description (format, structure) is a **gap** |
| Dataset identifier | `software_downloadLocation` and `software_packageVersion` when known; no public/citable identifier beyond that (the `spdxId` is internal) | conditional; **gap** for a citable ID |
| Dataset hash | none on `dataset_DatasetPackage` (no `verifiedUsing`, `dataset.py`); a dataset file scanned as a project file carries its SHA-256 on its own `software_File` | **gap** at package level; the hash is already on the linked `software_File` when the file ships with the project |
| Dataset provenance | `dataset_dataCollectionProcess` (free text), creator as a `publishedBy` `Agent`, and `trainedOn`/`testedOn` relationships to the model, when the relationship exists (the fields themselves only from a Croissant file) | conditional -- origin/lineage beyond that is a **gap** -- the classic `sbom-enrich` prose-inference target |
| Dataset statistical properties | `dataset_datasetSize` only | **gap** for anything beyond record count, generally **not automatable** without the user running their own analysis |
| Dataset sensitivity | `dataset_hasSensitivePersonalInformation`, `dataset_anonymizationMethodUsed`, `dataset_knownBias`, `dataset_intendedUse`, when a Croissant file declares them | conditional -- when the source is silent, ask the user directly (PII/copyright/sensitive-data flags are not derivable from files alone) |
| Dataset dependency relationship | `Relationship` (`generates`, `hasDataFile`) captures pipeline-derivation edges already | covered for pipeline-derived datasets |
| Dataset license | none emitted -- `DatasetMetadata.license` is extracted (Croissant) but `dataset.py` never reads it | **gap** in the output; check the dataset's Croissant file/card first, then fill via fragment. A core wiring fix is planned |

### System Level Properties, Infrastructure, Security Properties, KPI clusters

Not modelled by Pitloom's current `ai_AIPackage` mapping at all -- every element
in these four clusters (System name/components/producer/version/timestamp/data
flow/data usage/input-output properties, Intended application area;
Infrastructure software/hardware; Security controls/compliance/policy
info/vulnerability referencing; Security metrics, Operational performance KPIs)
is a **gap**, and several (Security Properties, KPIs) are largely **not
automatable** from repo content alone -- they describe the deployed system's
operational/security posture, not the model artefact. Treat these as the
lowest-priority tier: only pursue them if the user explicitly asks for full G7
coverage, and expect most to end up reported as open gaps rather than filled.

## Question bank (educated guesses for hard-to-derive elements)

Use these as a starting point for the "where might this information be" prompt
the skill gives the user for elements it can't resolve itself -- adapt to what's
actually in the project.

- **SBOM Author** (when `[[tool.pitloom.creator]]` isn't set): "Pitloom's own
  `CreationInfo` currently only names Pitloom itself as the generating tool, not
  the person or organisation that ran it. Who should be recorded as the SBOM
  author -- you, or an organisation? This can also be set permanently via
  `[[tool.pitloom.creator]]` in `pyproject.toml` (note the double brackets --
  it's an array of tables) so future runs don't need to ask -- and it also fills
  in Component Producer for the main package at the same time."
- **Component/Model Producer**: "Is this dependency/model something your
  organisation built, or a third-party component? If third-party, do you know
  the maintaining organisation or project (check the package's PyPI page, GitHub
  org, or model card)?"
- **SBOM Author Signature**: "This requires a detached digital signature over
  the SBOM using your organisation's own signing infrastructure (see NIST SP
  800-57 Pt. 1 for key-management guidance). Pitloom doesn't generate signatures
  -- do you already have a signing process, or is this out of scope for now?"
- **Model license**: "Does the model have its own license, separate from the
  project's? Check the model card / a `LICENSE` file next to the model weights,
  or the hub page if it came from Hugging Face."
- **Dataset provenance**: "Where did this dataset come from -- collected
  in-house, downloaded from a public source, or derived from another dataset in
  this project? Check the dataset's own README/data card, or a
  data-collection/labelling pipeline doc if one exists."
- **Dataset sensitivity**: "Does this dataset contain personal data (PII),
  copyrighted material, or other sensitive content (financial, medical, national
  security)? This generally can't be inferred from the data alone -- best
  answered by whoever curated it."
- **Model training properties**: "What training approach was used --
  pre-training from scratch, fine-tuning an existing model, RLHF, or something
  else? A model card's 'Training' or 'Methodology' section usually states this
  if one exists."

## Optional extra check (not a required step)

If the target standard is NTIA/CISA and the user wants an independent
cross-check, the community `ntia-conformance-checker` tool
(<https://github.com/spdx/ntia-conformance-checker>) can validate an SPDX
document against the NTIA baseline. This is a manual, optional step the user can
run themselves -- it is not wired into this skill, and its absence shouldn't
block anything here. The mandatory validation step remains the `sbom-validate`
skill
(<https://github.com/bact/pitloom/blob/main/skills/sbom-validate/SKILL.md>;
minimal fallback: `pip install "pitloom[validate]>=0.20.1"` then
`loom fragment validate <file>`).
