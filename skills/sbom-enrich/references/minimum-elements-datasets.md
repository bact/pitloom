---
Created: 2026-10-18
Last-Modified: 2026-10-18
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM minimum elements: G7 SBOM for AI 2026, Dataset Properties cluster

See also: [`minimum-elements.md`](minimum-elements.md) (the other G7
clusters and standards),
[`minimum-elements-questions.md`](minimum-elements-questions.md).

Applies to each `dataset_DatasetPackage`, only when an `ai_AIPackage` is
present (the G7 checklist is additive).

| Element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Dataset name | `dataset_DatasetPackage.name` | covered |
| Dataset description | `description`, when the source carries one: a Croissant file, or the first prose paragraph of a Hugging Face dataset card (for a dataset a Hub model card lists, looked up with the model); a dataset named only in a local model card gets a name, nothing more | conditional |
| Dataset content | `dataset_datasetType`, `dataset_dataPreprocessing`, `dataset_datasetSize` (record count) | covered when a Croissant file declares them (type defaults to `noAssertion`); finer content description (format, structure) is a **gap** |
| Dataset identifier | `software_packageUrl` `pkg:generic/<name>[@<version>]?download_url=<url>` when the download URL is http(s); `software_downloadLocation` and `software_packageVersion` when known (a Hub dataset's version is its repository's commit hash; the `spdxId` is internal) | conditional; **gap** for a dataset with no http(s) download URL |
| Dataset hash | none on a `dataset_DatasetPackage` found in a project or model card (no `verifiedUsing`, `dataset.py`); a dataset file scanned as a project file carries its SHA-256 and SHA-512 on its own `software_File`. A `loom.run` dataset carries one when it exists on disk and is within `max-dataset-hash-bytes`: a file's SHA-256 and SHA-512 (and `contains` that file's `software_File`), or a directory's SHA-256 Merkle root over its files' paths and content, commented as such | **gap** at package level outside `loom.run`; the hash is already on the linked `software_File` when the file ships with the project; a directory's Merkle root is not a hash of a single artefact |
| Dataset provenance | `dataset_dataCollectionProcess` (free text), creator as a `publishedBy` `Agent` (a Croissant creator, or a Hub dataset's repository owner, its provenance `Method: repository_owner`), and `trainedOn`/`testedOn` relationships to the model, when the relationship exists (the collection process only from a Croissant file) | conditional -- origin/lineage beyond that is a **gap** -- the classic `sbom-enrich` prose-inference target |
| Dataset statistical properties | `dataset_datasetSize` only | **gap** for anything beyond record count, generally **not automatable** without the user running their own analysis |
| Dataset sensitivity | `dataset_hasSensitivePersonalInformation`, `dataset_anonymizationMethodUsed`, `dataset_knownBias`, `dataset_intendedUse`, when a Croissant file declares them | conditional -- when the source is silent, ask the user directly (PII/copyright/sensitive-data flags are not derivable from files alone) |
| Dataset dependency relationship | `trainedOn` / `testedOn` from the model to the dataset (a Hub card's `datasets:` list, a Croissant file, or `loom.run`); `loom.run` also records `hasInput` from an output dataset to the input datasets it came from, and `generates` from its script to its outputs. The checker follows `trainedOn`/`testedOn`, so a dataset linked this way is judged by every standard | conditional -- **gap** for a dataset no source links to its model |
| Dataset license | a `hasDeclaredLicense` Relationship (`hasConcludedLicense` for a third-party record) from the dataset to a licence element, when the dataset metadata states a licence. Two kinds of dataset get one from a reader. A `loom.run` dataset: from its `declared_license=`, its local Croissant file (`croissant=`), or a directory dataset's `README.md` card frontmatter (`license`; `other` with `license_name`/`license_link`); a source's `unknown`, `NOASSERTION`, blank or bare `other` gives none, and so does the caller's own `unknown`, blank or bare `other` (the next source may then state one); only the caller's `declared_license="NOASSERTION"` (any case) is written, as the `NoAssertionLicense` individual, and a `declared_license=` on any call beats every Croissant file and card (of two declared, the first call's). A source's list of several licences gives one relationship each (in order, once each; a bare `other` in it gives none) and a dataset package `comment` that the source does not say whether they combine as AND or OR: do not merge them into one expression without evidence. A dataset a Hugging Face model card lists: from its Hub dataset card's `license`, by the same rules (up to 20 datasets, only when the model is looked up; a failed request is a `WARNING:` and the dataset keeps its name) | conditional; **gap** for a dataset named only in a local model card, or whose card states none: check its Croissant file/card, then fill via fragment |
