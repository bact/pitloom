---
Created: 2026-10-18
Last-Modified: 2026-10-29
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

Checker rules `BOM-G7AI2026-DP-001` to `-010` (23 with sub-rules; `DP-003.1`
domain, `.2` format, `DP-006.4` synthetic method, `DP-008.2`/`.3` copyright and
sensitive category are `out-of-scope`). A rule marked *any-of* is `present` when
any sub-rule is. It reads: `DP-001` `name`; `DP-002` *any-of* lifecycle role
(a `trainedOn`/`testedOn` pointing at the dataset), `dataset_datasetAvailability`,
`dataset_confidentialityLevel`; `DP-003` *any-of* `dataset_datasetType` (`noAssertion`
does not count); `DP-004` `software_packageUrl`, an `externalIdentifier` or
`software_contentIdentifier`; `DP-005` `verifiedUsing` on the package; `DP-006`
*any-of* `originatedBy`, `dataset_dataCollectionProcess`,
`dataset_dataPreprocessing`; `DP-007` `dataset_datasetSize` (bytes)
or `dataset_knownBias` (a Croissant record count is not recorded and does not
satisfy it: SPDX 3.0.1 has no property for one); `DP-008` *any-of* `dataset_hasSensitivePersonalInformation`
or `dataset_anonymizationMethodUsed`; `DP-009` `dependsOn` or `descendantOf`
from the dataset; `DP-010` `hasDeclaredLicense` only. Verified on Pitloom 0.21.0
(checker `82a63b9`, 2026-10-23; the expected tables are unchanged at the
current pin `2355afc`) with a mocked and a real Hugging Face model
with Hub datasets, a library-built model with a dataset and a `loom.run`
fragment with a local Croissant file (see the note in
[`minimum-elements.md`](minimum-elements.md)). A Croissant file is read only by
`loom.run` (`croissant=`) and the library's `read_croissant()` (alias
`read_dataset()`), never from a
project directory or a Hub dataset.

| Element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Dataset name | `dataset_DatasetPackage.name` | covered |
| Dataset description | `description`, when the source carries one: a Croissant file, or the first prose paragraph of a Hugging Face dataset card (for a dataset a Hub model card lists, looked up with the model); a dataset named only in a local model card gets a name, nothing more | conditional |
| Dataset content | `dataset_datasetType`, `dataset_dataPreprocessing` | covered when a Croissant file or a library caller declares them (type defaults to `noAssertion`, which `DP-003` does not count: every Hub dataset gets it); finer content description (format, structure) is a **gap** |
| Dataset identifier | `software_packageUrl` `pkg:generic/<name>[@<version>]?download_url=<url>` when the download URL is http(s); `software_downloadLocation` and `software_packageVersion` when known (a Hub dataset's version is its repository's commit hash; the `spdxId` is internal) | conditional; **gap** for a dataset with no http(s) download URL |
| Dataset hash | none on a `dataset_DatasetPackage` found in a project or model card (no `verifiedUsing`, `dataset.py`); a dataset file scanned as a project file carries its SHA-256 and SHA-512 on its own `software_File`. A `loom.run` dataset carries one when it exists on disk and is within `max-dataset-hash-bytes`: a file's SHA-256 and SHA-512 (and `contains` that file's `software_File`), or a directory's SHA-256 Merkle root over its files' paths and content, commented as such | **gap** at package level outside `loom.run`; the hash is already on the linked `software_File` when the file ships with the project; a directory's Merkle root is not a hash of a single artefact |
| Dataset provenance | `dataset_dataCollectionProcess` (free text), creator as a `publishedBy` relationship to an `Agent` (a Croissant creator, a library caller's `creator`, or a Hub dataset's repository owner, its provenance `Method: repository_owner`; `DP-006.1` reads `originatedBy`, so this creator never satisfies it), and `trainedOn`/`testedOn` relationships to the model, when the relationship exists (the collection process only from a Croissant file) | conditional -- origin/lineage beyond that is a **gap** -- the classic `sbom-enrich` prose-inference target |
| Dataset statistical properties | `dataset_datasetSize` (size in bytes; set for a `loom` single-file dataset, else only by a library caller's `byte_size`) and `dataset_knownBias` (a Croissant file's `rai:dataBiases`); `DP-007` reads either. A Croissant record count is not recorded and never copied into `dataset_datasetSize` | **gap** unless a size or known biases is declared (a `loom` single-file dataset has its size); else ask once for the dataset's size in bytes or its known biases; non-interactively leave `DP-007` missing and report the gap. Generally **not automatable** without the user running their own analysis |
| Dataset sensitivity | `dataset_hasSensitivePersonalInformation` (what `DP-008.1` reads, with `dataset_anonymizationMethodUsed`), when a Croissant file declares `rai:personalSensitiveInformation`; `dataset_anonymizationMethodUsed` and `dataset_intendedUse` only when a library caller sets them (no reader fills them) | conditional -- when the source is silent, ask the user directly (PII/copyright/sensitive-data flags are not derivable from files alone) |
| Dataset dependency relationship | `trainedOn` / `testedOn` from the model to the dataset (a Hub or local model card's `datasets:` list, as `trainedOn`, or `loom.run`); references to one dataset (a Hub id in any case, from any of these) give one dataset package with one relationship per role, a later reference filling only fields still unset; `loom.run` also records `hasInput` from an output dataset to the input datasets it came from, and `generates` from its script to its outputs. The checker follows `trainedOn`/`testedOn`, so a dataset linked this way is judged by every standard, but `DP-009` reads a `dependsOn`/`descendantOf` from the dataset, which Pitloom never writes: it stays `missing` | conditional -- **gap** for a dataset no source links to its model; `DP-009` a **gap** always |
| Dataset license | a `hasDeclaredLicense` Relationship (`hasConcludedLicense` for a third-party record, which `DP-010` does not count) from the dataset to a licence element, when the dataset metadata states a licence. Two kinds of dataset get one from a reader. A `loom.run` dataset: from its `declared_license=`, its local Croissant file (`croissant=`), or a directory dataset's `README.md` card frontmatter (`license`; `other` with `license_name`/`license_link`); a source's `unknown`, `NOASSERTION`, blank or bare `other` gives none, and so does the caller's own `unknown`, blank or bare `other` (the next source may then state one); only the caller's `declared_license="NOASSERTION"` (any case) is written, as the `NoAssertionLicense` individual, and a `declared_license=` on any call beats every Croissant file and card (of two declared, the first call's). A source's list of several licences gives one relationship each (in order, once each; a bare `other` in it gives none) and a dataset package `comment` that the source does not say whether they combine as AND or OR: do not merge them into one expression without evidence. A dataset a Hugging Face model card lists: from its Hub dataset card's `license`, by the same rules (up to 20 datasets, only when the model is looked up; a failed request is a `WARNING:` and the dataset keeps its name) | conditional; **gap** for a dataset named only in a local model card, or whose card states none: check its Croissant file/card, then fill via fragment |
