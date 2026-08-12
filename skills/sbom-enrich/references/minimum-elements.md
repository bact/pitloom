---
Created: 2026-08-12
Last-Modified: 2026-08-12
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM minimum elements checklists

Companion to `../SKILL.md`'s "Complete a standard's minimum elements" section. Three
checklists -- NTIA 2021, CISA 2026, and G7 SBOM for AI 2026 -- each mapped to the
Pitloom/SPDX 3 field that carries it today, so the agent can tell a real gap from
something the base SBOM already covers before asking the user anything.

**Which checklist applies:** CISA 2026 *supersedes* NTIA 2021 (same core principles,
renamed/split/added fields -- see the "2021 name" column below) and is the current
baseline unless the user specifically asks for the 2021 version (e.g. an older
contract or policy cites it by name). G7 SBOM for AI 2026 is **additive** -- apply it
only when the base SBOM has an `ai_AIPackage` element, on top of whichever general
checklist applies.

Status legend: **covered** -- Pitloom emits this deterministically, nothing to do.
**conditional** -- emitted only when a dependency resolves against PyPI/installed
metadata, or similar; verify per-run, don't assume. **gap** -- this workflow's actual
job. **not automatable** -- no file or answer this workflow can gather will satisfy
it; say so plainly rather than implying it can be filled.

The "covered"/"conditional" calls below were checked against a real Pitloom-generated
AI SBOM (`examples/sentimentdemo-aibom/`'s built `sentimentdemo.spdx3.json`), not
inferred from source alone -- re-verify against a fresh `loom` run if Pitloom's
assembly code has changed since.

## NTIA 2021 (7 data fields + 6 practices)

Field names below are the 2021 originals; CISA 2026's Appendix B documents each rename.

| 2021 element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Supplier Name | dependency: `suppliedBy` -> `Agent` via `_apply_supplier`/PyPI JSON API (`deps.py`); main package: `software_Package.suppliedBy`, but only set when `[[tool.pitloom.creator]]` is configured (`document.py`'s `_build_main_package`) | conditional (deps, PyPI-resolvable only); **gap** for the main package unless `[[tool.pitloom.creator]]` is set -- same config also fixes `Author of SBOM Data` below, see the note there |
| Component Name | `software_Package.name` / `ai_AIPackage.name` | covered |
| Version of the Component | `software_packageVersion` (explicit `"unknown"` string when not resolvable -- already matches the 2021/2026 "indicate unknown" guidance) | covered |
| Other Unique Identifiers | `software_packageUrl` (PURL); main package always, deps only when resolvable | conditional |
| Dependency Relationship | `Relationship`/`LifecycleScopedRelationship` (`contains`, `dependsOn`, `hasDataFile`, `generates`, etc.) | covered |
| Author of SBOM Data | `CreationInfo.createdBy` -> `SoftwareAgent` named "Pitloom" (the *tool*, not a person/org) unless `[[tool.pitloom.creator]]` is configured | **gap** unless the project configures `[[tool.pitloom.creator]]` -- check that first before asking the user. **One config answers two elements at once:** the same creator Agent also becomes the main package's `suppliedBy` (`document.py`: "so only assert it for a real named creator -- not for the default SoftwareAgent 'Pitloom', which is the SBOM tool, not the package's supplier"), so this single fix closes both `Author of SBOM Data`/`SBOM Author` *and* `Supplier Name`/`Component Producer` for the main package in one answer -- lead with this when ranking gaps by effort-to-impact |
| Timestamp | `CreationInfo.created` | covered |

Practices (process expectations, not data fields -- report as satisfied/not by
observation, nothing to draft a fragment for): Depth (Pitloom's dependency graph has
no fixed depth limit -- covered), Known Unknowns (Pitloom's `"unknown"` string
convention -- covered), Distribution and Access Control (deployment concern, out of
scope), Accommodation of Mistakes (re-run `loom` to regenerate -- covered),
Automation Support (SPDX 3 JSON-LD is machine-processable -- covered), Frequency
(deployment/process concern, out of scope).

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
| Component Producer | dependency: `suppliedBy` via `_apply_supplier` from PyPI JSON API; main package: `software_Package.suppliedBy`, only when `[[tool.pitloom.creator]]` is configured | conditional (deps, PyPI-resolvable only); **gap** for the main package unless `[[tool.pitloom.creator]]` is set -- see NTIA's "Supplier Name" row above |
| Component Dependency Relationship | `Relationship`/`LifecycleScopedRelationship` | covered |
| Component Hash Value / Algorithm | `verifiedUsing` (`{"algorithm": "sha256", "hashValue": ...}`); set on dataset files/packages and on PyPI-resolved deps (`_extract_release_hash`); **not** set on the main project package (a `loom project`-level SBOM describes source, not a built artifact) | conditional -- present on deps only when a definite version resolves; absent by design on a source-level main package (ask whether a built-artifact hash is even expected before treating this as a gap) |
| Component Identifiers | `software_packageUrl` (PURL) | conditional, same as NTIA's "Other Unique Identifiers" |
| Component License | `simplelicensing_SimpleLicensingText` + relationship (main package, from `project.license`); deps via PyPI JSON API (`_extract_pypi_license`) | conditional (deps, PyPI-resolvable only); main package usually covered when `pyproject.toml` declares a license |
| Component Name | `software_Package.name` | covered |
| Component Version | `software_packageVersion` | covered |

### Practices and Processes

Mostly process observations, not fields to fill: Accommodation of Updates to SBOM
Data (re-run `loom` -- covered), Coverage (Pitloom walks the full dependency
graph -- covered, but a mixed-ecosystem project has real gaps outside Python; see
`sbom-generate`'s "Known limitations"), Distribution and Delivery (deployment
concern, out of scope), Explicitly Identifying Unknown Information (Pitloom's
`"unknown"`/`NOASSERTION` convention -- covered, and this workflow's final report
should follow the same convention for anything the user declines to answer),
Frequency (process concern, out of scope), Machine-Processable Data (SPDX 3
JSON-LD -- covered).

## G7 SBOM for AI 2026 (additive -- apply only when an `ai_AIPackage` is present)

### Models cluster

| Element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Model name | `ai_AIPackage.name` | covered |
| Model identifier | none seen on `ai_AIPackage` in the verified sample (no PURL/external identifier) | **gap** |
| Model version | none seen (`software_packageVersion` not set on the AI package in the verified sample) | **gap** |
| Model timestamp | `CreationInfo.created` on the AI package's own `CreationInfo` | covered |
| Model producer | none | **gap** |
| Model description | none seen on the AI package itself (the *main* `software_Package.description` is separate) | **gap** |
| Model hash value / algorithm | none seen -- `verifiedUsing` not set on `ai_AIPackage` in the verified sample even though the model file exists on disk | **gap** -- worth checking whether a newer `loom enrich`/hashing pass already closes this before asking the user; if not, this is a strong candidate to raise upstream as a Pitloom core gap, separate from this skill |
| Model properties (architecture, parameter count, etc.) | partially: `ai_hyperparameter` (list of `DictionaryEntry`), `ai_typeOfModel` | covered for hyperparameters/type; architecture/parameter-count fields are a **gap** |
| Model input-output properties | `ai_informationAboutApplication` (JSON string) | covered when the model format's extractor populates it; verify per model type |
| Model training properties | not distinctly modeled (see `ai_typeOfModel` for the closest overlap) | **gap** -- ask/read for training technique detail (pre-training vs. fine-tuning vs. RLHF, etc.) |
| Model license | none seen on `ai_AIPackage` (distinct from the main package's license) | **gap** -- this is exactly the kind of field `sbom-enrich`'s existing prose-inference steps (2-6) already target; reuse them rather than re-deriving |
| Model external references | none | **gap** |

### Dataset Properties cluster

Applies to each `dataset_DatasetPackage`.

| Element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Dataset name | `dataset_DatasetPackage.name` | covered |
| Dataset description | none seen in the verified sample | **gap** |
| Dataset content | `dataset_datasetType`, `dataset_dataPreprocessing` | covered (type + preprocessing steps); finer content description (format, structure) is a **gap** |
| Dataset identifier | none beyond the internal `spdxId` (not a public/citable identifier) | **gap** |
| Dataset hash | `verifiedUsing` | covered, when the dataset is a local file Pitloom can hash |
| Dataset provenance | not modeled | **gap** -- the classic `sbom-enrich` prose-inference target (trainedOn/testedOn relationships, origin, collection method) |
| Dataset statistical properties | not modeled | **gap**, generally **not automatable** without the user running their own analysis |
| Dataset sensitivity | not modeled | **gap** -- ask the user directly (PII/copyright/sensitive-data flags are not derivable from files alone) |
| Dataset dependency relationship | `Relationship` (`generates`, `hasDataFile`) captures pipeline-derivation edges already | covered for pipeline-derived datasets |
| Dataset license | not modeled per-dataset | **gap** |

### System Level Properties, Infrastructure, Security Properties, KPI clusters

Not modeled by Pitloom's current `ai_AIPackage` mapping at all -- every element in
these four clusters (System name/components/producer/version/timestamp/data
flow/data usage/input-output properties, Intended application area; Infrastructure
software/hardware; Security controls/compliance/policy info/vulnerability
referencing; Security metrics, Operational performance KPIs) is a **gap**, and
several (Security Properties, KPIs) are largely **not automatable** from repo
content alone -- they describe the deployed system's operational/security posture,
not the model artifact. Treat these as the lowest-priority tier: only pursue them if
the user explicitly asks for full G7 coverage, and expect most to end up reported as
open gaps rather than filled.

## Question bank (educated guesses for hard-to-derive elements)

Use these as a starting point for the "where might this information be" prompt the
skill gives the user for elements it can't resolve itself -- adapt to what's actually
in the project.

- **SBOM Author** (when `[[tool.pitloom.creator]]` isn't set): "Pitloom's own
  `CreationInfo` currently only names Pitloom itself as the generating tool, not the
  person or organization that ran it. Who should be recorded as the SBOM author --
  you, or an organization? This can also be set permanently via
  `[[tool.pitloom.creator]]` in `pyproject.toml` (note the double brackets -- it's an
  array of tables) so future runs don't need to ask -- and it also fills in Component
  Producer for the main package at the same time."
- **Component/Model Producer**: "Is this dependency/model something your
  organization built, or a third-party component? If third-party, do you know the
  maintaining organization or project (check the package's PyPI page, GitHub org, or
  model card)?"
- **SBOM Author Signature**: "This requires a detached digital signature over the
  SBOM using your organization's own signing infrastructure (see NIST SP 800-57
  Pt. 1 for key-management guidance). Pitloom doesn't generate signatures -- do you
  already have a signing process, or is this out of scope for now?"
- **Model license**: "Does the model have its own license, separate from the
  project's? Check the model card / a `LICENSE` file next to the model weights, or
  the hub page if it came from Hugging Face."
- **Dataset provenance**: "Where did this dataset come from -- collected in-house,
  downloaded from a public source, or derived from another dataset in this project?
  Check the dataset's own README/data card, or a data-collection/labeling pipeline
  doc if one exists."
- **Dataset sensitivity**: "Does this dataset contain personal data (PII),
  copyrighted material, or other sensitive content (financial, medical, national
  security)? This generally can't be inferred from the data alone -- best answered
  by whoever curated it."
- **Model training properties**: "What training approach was used -- pre-training
  from scratch, fine-tuning an existing model, RLHF, or something else? A model
  card's 'Training' or 'Methodology' section usually states this if one exists."

## Optional extra check (not a required step)

If the target standard is NTIA/CISA and the user wants an independent cross-check,
the community `ntia-conformance-checker` tool
(<https://github.com/spdx/ntia-conformance-checker>) can validate an SPDX document
against the NTIA baseline. This is a manual, optional step the user can run
themselves -- it is not wired into this skill, and its absence shouldn't block
anything here. The mandatory validation step remains the `sbom-validate` skill (see
`../SKILL.md`).
