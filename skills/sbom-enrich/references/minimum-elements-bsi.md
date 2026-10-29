---
Created: 2026-10-18
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM minimum elements: BSI TR-03183-2 v2.1

See also: [`minimum-elements.md`](minimum-elements.md) (the other standards),
[`minimum-elements-questions.md`](minimum-elements-questions.md).

## BSI TR-03183-2 v2.1 (SBOM content, section 5.2; checker `bsi`)

Rule ids are `BOM-BSI2025-<id>`. BSI asks the most of the five: on a default
run most component rules are missing. "If it exists" rules are
`not-applicable` for a package that does not give the element; "optional"
ones never block. Each rule is reported on its own, as for the other
standards. Checked as for FSCT in
[`minimum-elements.md`](minimum-elements.md) (Pitloom 0.21.0, checker
`82a63b9`, 2026-10-23; the expected tables are unchanged at the current pin
`2355afc`), plus a fragment merged into a Hatchling project base:
the "user must supply" rows below (a wheel `software_File` with its SHA-512 and
`hasDistributionArtifact`, `dependsOn` with `completeness`, including to
`NoneElement` and `NoAssertionElement`, `software_additionalPurpose`
`container`, a `securityPolicy` `externalRef`) were merged, validated with
`loom fragment validate` and re-checked: each turned `present` for the packages
it covered.

| Id | Element | SPDX 3 field the checker reads | Pitloom | Checked |
| :--- | :--- | :--- | :--- | :--- |
| DOC-001 | Creator of the SBOM | a `Person`/`Organization` in `createdBy` with an `email` identifier (or an http(s) `urlScheme`/`other` one) | **user must supply**: the default `Pitloom` software agent never counts; `--creator-name N --creator-type person\|organization --creator-email E` (any target) or `[[tool.pitloom.creator]]` with `email` (project) passes. Pitloom records an e-mail, not a URL | yes |
| DOC-002 | Timestamp | `created` | fills | yes |
| DOC-003 | BOM-URI | `spdxId` | always there | no |
| COMP-001 | Component creator | a `Person`/`Organization` with e-mail or URL in `originatedBy` of every package | the main package when a `[project].authors` entry has an e-mail; a dependency when its installed metadata (also `--offline`) or PyPI gives an author e-mail; never a model (a generic `Agent`) nor a dataset (its creator is `publishedBy`, not `originatedBy`) | yes |
| COMP-002 | Component name | `name` | fills | yes |
| COMP-003 | Component version | `software_packageVersion` | as FSCT COMP-002 | yes |
| COMP-004 | Filename | `hasDistributionArtifact` to a named element | **user must supply**: Pitloom writes none; a fragment can add a `software_File` named after the built archive and the relationship | yes |
| COMP-005 | Dependencies, with completeness | a `dependsOn`/`contains` from every package with `completeness` set | **user must supply**: Pitloom sets no `completeness`; a package with none says so with `dependsOn` to `NoneElement`, `completeness` `complete`; `NoAssertionElement` with `noAssertion` says the list is unknown, which BSI allows. State `complete` only when the user confirms it | yes |
| COMP-006 | Distribution licence | `hasConcludedLicense` (not `NoAssertionLicense`) | as FSCT COMP-007 | yes |
| COMP-007 | Hash of the deployable component | a **SHA-512** `Hash` on the package or its distribution artifact | a model file Pitloom read, and a `loom.run` dataset that is one file (SHA-256 and SHA-512; a directory dataset gets only a SHA-256 Merkle root); **not** a project's main package (a SHA-256 Merkle root over its files, not a deployable archive), **not** a dependency (only the lock file's SHA-256 exists, so it cannot be met), **not** a Hugging Face model or a Hub dataset (no hash). The user can supply the built archive's SHA-512 on the COMP-004 `software_File` | yes |
| COMP-008, COMP-009 | Executable, archive property | -- | stated by leaving the purpose out | no |
| COMP-010 | Structured property | `container` (structured) or `firmware` (unstructured) in `software_primaryPurpose`/`software_additionalPurpose` of the package or its artifact | **user must supply**: Pitloom writes `library`, `model` and the like; a fragment restating the package can add `software_additionalPurpose` (lists merge as a union). It is the user's statement about the component, never the agent's guess | yes |
| COMP-011 | Source code URI (if it exists) | `externalRef` of type `vcs` | Pitloom writes none (a `[project.urls]` `Source`, else `Homepage`, URL becomes `software_downloadLocation`), so `not-applicable` | yes |
| COMP-012 | URI of the deployable form (if it exists) | `software_downloadLocation` or an `altDownloadLocation`/`binaryArtifact` ref | the main package when `[project.urls]` gives a `Source` or `Homepage` URL; a dataset with a download URL (a Hub dataset's page); `not-applicable` for a package with none | yes |
| COMP-013 | Other unique identifiers (if they exist) | as FSCT COMP-004 | fills | yes |
| COMP-014 | Original licences (if they exist) | `hasDeclaredLicense` | the project's stated licence (with none stated, the one its licence files show); a model's or dataset's when its source states one | yes |
| COMP-015 | Effective licence (optional) | `hasConcludedLicense` | as COMP-006 (they pass or fail together) | yes |
| COMP-016 | Hash of the source code (optional) | -- | SPDX 3.0.1 has no link the mapping names | no |
| COMP-017 | security.txt URL (optional) | `externalRef` of type `securityPolicy`/`securityOther` | **user must supply** | yes |

**Git LFS pointers (COMP-007).** A pointer file in a checkout or Git URL scan
has the content's SHA-256 (the `oid`) only, because Pitloom does not read the
content, so a SHA-512 check on it is not met until the user follows the
advice in Pitloom's `WARNING:` outside the tool and regenerates. Leave the
SHA-512 out and report the pointer count from the `WARNING:`.
