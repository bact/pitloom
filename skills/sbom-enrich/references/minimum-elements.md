---
Created: 2026-08-12
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM minimum elements checklists

See also: [`minimum-elements-g7.md`](minimum-elements-g7.md) (G7 SBOM for
AI 2026, every cluster), [`minimum-elements-bsi.md`](minimum-elements-bsi.md)
(BSI), [`minimum-elements-questions.md`](minimum-elements-questions.md) (the
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
`minimum-elements-workflow.md`): `ntia`, `fsct3` (`fsct3-min` is a deprecated
alias that works with a `WARNING:`), `cisa2026`, `g7ai`, `bsi`. Rule ids are
`BOM-<STANDARD>-<id>`: NTIA `BOM-NTIA2021-DF-001` to `-007`; FSCT
`BOM-FSCT2024-META-001` to `-005`, `COMP-001` to `-008`; CISA
`BOM-CISA2026-META-001` to `-009`, `COMP-001` to `-008`, `PP-001` to `-006`; BSI
`BOM-BSI2025-DOC-001` to `-003`, `COMP-001` to `-017`; G7
`BOM-G7AI2026-<cluster>-<n>`, cluster `MD`, `SLP`, `MDL`, `DP`, `INF`, `SP` or
`KPI`, a recommendation under a requirement written `MDL-006.1`. A rule the
checker's rule file marks `catalogue-only` is listed but never checked, and is
reported `out-of-scope`. The checker's `present` means the property it looks for
exists, not that its value is right or that the standard's intent is met (NTIA's
and CISA's author rules accept Pitloom's own software-agent creator, for
example). The component rules of every standard judge each package reachable
from the SBOM root through composition and dependency relationships, plus
datasets and models linked by `trainedOn`/`testedOn`; a dataset linked in no way
is not judged.

Status legend: **covered** -- Pitloom emits this deterministically.
**conditional** -- emitted only when a source has it (a dependency resolving
against installed metadata or PyPI, a format's field); verify per run. **gap**
-- this workflow's actual job. **not automatable** -- no file or answer this
workflow can gather will satisfy it; say so plainly rather than implying it can
be filled.

The "covered"/"conditional"/"gap" calls and every checker rule id, provision,
carrier and `out-of-scope` call below were compared with the assembly code
(`assemble/spdx3/`), the readers (`extract/`), the checker's rule files and real
runs on Pitloom 0.21.0, checker `82a63b9`, 2026-10-23 (the expected tables
are unchanged at the current pin `2355afc`, 2026-10-28):
`sbomcheck -s spdx3 -c <id> -r json`, all five ids, on the ten scenario SBOMs of
`tests/conformance/g7ai_shared.py` (outcomes equal to
`tests/fixtures/conformance/*-expected.tsv` rule by rule), a Hatchling
`uv.lock` project with dependencies, author e-mails, a `LICENSE`, URLs, creators
and a model (online and `--offline`), `loom model` on every format's fixture and
a real Hub model, and a `loom.run` fragment with a Croissant file. Re-verify if
the assembly code or the checker pin has changed.

## NTIA 2021 (7 data fields + 6 practices)

Field names below are the 2021 originals; CISA 2026's Appendix B documents each
rename.

| 2021 element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Supplier Name | dependency: `originatedBy` -> `Person` (with its e-mail) from installed metadata (also `--offline`) or the PyPI JSON API (`deps_originator.py`); main package: `originatedBy` -> one `Person` per `[project].authors` entry (only a contributor group such as `et al.` is an `Organization`), and `suppliedBy` only for the first creator (`[[tool.pitloom.creator]]` or `--creator-*`) that is not a `software-agent` (`document.py`) | conditional (deps, installed- or PyPI-resolvable only); main package: **covered** by `originatedBy` when authors are declared, a **gap** for `suppliedBy` unless a person, organisation or generic-agent creator is set -- the same config fixes `Author of SBOM Data` below; an AI model: `originatedBy` from structured fields, `suppliedBy` only on the Hugging Face route (see `minimum-elements-g7.md`, "Model producer") |
| Component Name | `software_Package.name` / `ai_AIPackage.name` | covered |
| Version of the Component | `software_packageVersion` (explicit `"unknown"` string when not resolvable -- already matches the 2021/2026 "indicate unknown" guidance) | covered |
| Other Unique Identifiers | `software_packageUrl` (PURL): main package `pkg:pypi/...` when its version is known; deps only when resolvable; a model `pkg:huggingface/...` or `pkg:generic/<file>?checksum=...` (see `minimum-elements-g7.md`, "Model identifier"); a dataset only with an http(s) download URL | conditional |
| Dependency Relationship | `Relationship`/`LifecycleScopedRelationship` (`contains`, `dependsOn` with scope `runtime`, `hasOptionalDependency` for extras, `generates`, etc.; `hasDataFile` from a `.py` file to a model file only with `--scan-model-usage`, and from a `loom.run` script to a model it uses, `use_model()`; `set_model()` gives `generates`). The checker counts only `contains`, `dependsOn`, `hasStaticLink` and `hasDynamicLink` | covered for a project; **gap** for a single-model SBOM |
| Author of SBOM Data | `CreationInfo.createdBy` -> `SoftwareAgent` named "Pitloom" (the *tool*, not a person/org) unless `[[tool.pitloom.creator]]` or `--creator-name`/`--creator-type`/`--creator-email` names one | **gap** unless the project configures `[[tool.pitloom.creator]]` (or the run passed `--creator-*`) -- check that first before asking the user. **One config answers two elements at once:** the same creator also becomes the main package's `suppliedBy` unless it is a `software-agent` (a program that made the SBOM did not supply the package), closing `Author of SBOM Data`/`SBOM Author` *and* the supplier in one answer -- lead with this when ranking gaps by effort-to-impact |
| Timestamp | `CreationInfo.created` | covered |

Checker (`-c ntia`, rules `BOM-NTIA2021-DF-001` to `-007`, in the table's
order: supplier, name, version, identifier, dependency relationship, author,
timestamp): the supplier rule reads `suppliedBy` on every package, so it is
missing for a model file or a model in a project, for every dataset and
dependency (Pitloom sets no `suppliedBy` on them) and for the main package
without a non-`software-agent` creator; the author rule accepts the default
`Pitloom` software agent; the dependency rule is document-level: a `contains`,
`dependsOn`, `hasStaticLink` or `hasDynamicLink` between two elements of the
document (no other type counts), so it is missing for a single-model SBOM.

Practices (process expectations, not data fields: report satisfied/not by
observation, nothing to draft): Depth (no fixed depth limit -- covered), Known
Unknowns (the `"unknown"` string -- covered), Distribution and Access Control
and Frequency (out of scope), Accommodation of Mistakes (re-run `loom` --
covered), Automation Support (SPDX 3 JSON-LD -- covered).

## FSCT 2024 (baseline attributes, minimum expected level; checker `fsct3`)

Rule ids are `BOM-FSCT2024-<id>`. "Pitloom" says what a default run writes,
checked with `loom model`/`loom project` and `sbomcheck -c fsct3` on
2026-10-23 (Pitloom 0.21.0).

| Id | Element | SPDX 3 field the checker reads | Pitloom | Checked |
| :--- | :--- | :--- | :--- | :--- |
| META-001 | Author Name | `CreationInfo.createdBy` | fills (the default `Pitloom` software agent counts; FSCT means the SBOM's author, so name a person or organisation: `--creator-name`/`--creator-type`/`--creator-email` or `[[tool.pitloom.creator]]`) | yes |
| META-002 | Timestamp | `CreationInfo.created` | fills | yes |
| META-003 | SBOM Type | `software_sbomType` | fills | yes |
| META-004 | Primary Component | `rootElement` | fills (the `software_Sbom` names the root package or model) | no (`out-of-scope`) |
| META-005 | Dependency Relationship | a `contains`, `dependsOn`, `hasStaticLink` or `hasDynamicLink` between two elements of the document (`hasOptionalDependency` does not count) | fills for a project (its `contains` and `dependsOn` links); none in a single-model SBOM, and a `loom model` base merges no fragment | yes |
| COMP-001 | Component Name | `name` | fills | yes |
| COMP-002 | Version | `software_packageVersion` | the main package and lock- or PyPI-resolved dependencies; a model only when its format states one, or a Hugging Face model's commit (see `minimum-elements-g7.md`, "Model version"); a dataset only when its source states one (a Hub dataset's commit) | yes |
| COMP-003 | Supplier Name | `suppliedBy` | the main package only with `[[tool.pitloom.creator]]` or `--creator-*` (the first creator that is not a `software-agent` becomes its supplier); a Hugging Face model (its owner); never a dependency, a dataset, a model file or a model in a project: the user must supply it | yes |
| COMP-004 | Unique Identifier | `software_packageUrl`, `software_contentIdentifier` or a packageUrl/cpe/swid/swhid/gitoid `externalIdentifier` | fills (a PURL on every package with a known version or a hashed model file; a dataset needs an http(s) download URL) | yes |
| COMP-005 | Cryptographic Hash | `verifiedUsing` | see CISA's hash row | no |
| COMP-006 | Relationship (per component, with completeness) | -- | Pitloom writes no `completeness` | no |
| COMP-007 | License | `hasConcludedLicense` only (not `NoAssertionLicense`) | the main package's only when it states a licence and the LicenseID database (`licenseid update --source packaged`) detects one in its licence files -- the stated licence itself is `hasDeclaredLicense`, which does not count, and with no stated licence the detection becomes the declared one; not a dependency's licence (from its installed copy, its licence files or PyPI: declared, its originator's statement), nor the licence a model's or dataset's own source states, which is declared (dependencies, models and datasets are `missing`; for dependencies that is expected since #569, not a defect in the SBOM): the user can conclude one by fragment | yes |
| COMP-008 | Copyright Notice | `software_copyrightText` (`NOASSERTION` counts as missing) | the main package when its licence files carry copyright lines (else `NOASSERTION`); a dependency when its installed copy's licence files do; a model or dataset none | yes |

## CISA 2026 (current baseline; 10 metadata + 7 component fields + 6 practices)

The tables follow the standard's own elements. The checker counts 23 rules: 9
metadata (the dependency relationship is a component rule), 8 component (hash
value and hash algorithm are two) and 6 practices.

### SBOM Metadata

| Element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| SBOM Author | see NTIA 2021's "Author of SBOM Data" row above -- same gap, same one-config fix | **gap** unless `[[tool.pitloom.creator]]` configured |
| SBOM Author Signature | none | **not automatable** -- needs the project's own signing infrastructure (NIST SP 800-57 Pt. 1); ask whether one exists, never fake it |
| SBOM Data Format Name | implicit: `@context` is the SPDX 3 JSON-LD context | covered (self-describing by format, no explicit field needed) |
| SBOM Data Format Version | `CreationInfo.specVersion` (e.g. `"3.0.1"`) | covered |
| SBOM Generation Context | `software_Sbom.software_sbomType` (`source`/`build`/`analyzed`/`deployed`/`runtime`; CISA 2026's "before build"/"build"/"after build" map onto it) | covered |
| SBOM Timestamp | `CreationInfo.created` | covered |
| SBOM Tool Name | `Tool.name` (e.g. `"Pitloom"`) | covered |
| SBOM Tool Version | `Tool.summary` text (`"Pitloom 0.23.0"`) and the `Tool`'s `packageUrl` `externalIdentifier` (`pkg:pypi/pitloom@0.23.0`): **SPDX 3.0.1 has no `Tool.version` property** (added in 3.1-dev; `creation_info.py`) | covered through these workarounds only -- a spec-version limitation, not something a fragment can fix; `META-008` is `out-of-scope` |
| SBOM Version | none -- no field tracks a version for the SBOM document itself, distinct from the tool's version | **gap** this workflow cannot fill safely (it needs a real versioning scheme for the SBOM outputs) -- report it as unaddressed, never fabricate a `"1.0"` |
| SBOM Dependency Relationship | see Component Dependency Relationship below -- same field, same coverage | covered for a project; **gap** for a single-model SBOM |

### Component Data

| Element | Pitloom/SPDX 3 field | Status |
| :--- | :--- | :--- |
| Component Producer | dependency: `originatedBy` via `_apply_originator` (`deps_originator.py`) from installed metadata or the PyPI JSON API; main package: `originatedBy` from `[project].authors`, and `suppliedBy` only for a non-`software-agent` creator; an AI model: `originatedBy`, see `minimum-elements-g7.md`, "Model producer"; a dataset: none (its creator is a `publishedBy` relationship, which the checker's `COMP-001` does not read) | conditional (deps, installed- or PyPI-resolvable only); main package **covered** when authors are declared -- see NTIA's "Supplier Name" row above; a dataset a **gap** always |
| Component Dependency Relationship | `Relationship`/`LifecycleScopedRelationship` (what counts: NTIA's "Dependency Relationship" row above) | covered for a project; **gap** for a single-model SBOM |
| Component Hash Value / Algorithm | `verifiedUsing` (`{"algorithm": "sha256", "hashValue": ...}`, plus a `sha512` entry on a file Pitloom reads itself); set on every `software_File` (dataset and model files too), on dependencies from a supported lock file's SHA-256 (online and offline), else PyPI's (`deps_pypi.py`). The main package carries a SHA-256 Merkle root over its payload files, commented as not a single-artefact hash, in a project, wheel and embed SBOM; **not** on an sdist SBOM, a Hugging Face model, or a `dataset_DatasetPackage` outside `loom.run` | conditional -- deps only when a definite version resolves; the main package's is a Merkle root, not an artefact hash; AI/dataset package-level gaps: `minimum-elements-g7.md` |
| Component Identifiers | `software_packageUrl` (PURL) | conditional, same as NTIA's "Other Unique Identifiers" |
| Component License | `simplelicensing_LicenseExpression` (a valid SPDX expression, or a `LicenseRef-loom-text-<hash>` whose `customIdToUri` maps to a `simplelicensing_SimpleLicensingText` holding other text) + `hasDeclaredLicense`/`hasConcludedLicense` relationship (main package, from `project.license`, then its `License ::` classifiers: declared when the package states it, including a `loom env` package's own metadata; beside a stated licence, the licence-file detection and a library caller's `license_concluded` are concluded); deps from installed metadata, then classifiers, then their installed licence files, then the PyPI JSON API, each declared (the dependency's own statement; a stated text and a different file licence are both declared, with a conflict annotation). No licence stated = **no relationship**; `NoAssertionLicense`/`NoneLicense` individuals only when a source said `NOASSERTION`/`UNKNOWN`/`NONE` | conditional (deps: installed or PyPI-resolvable only); main package usually covered when `pyproject.toml` declares a licence; a missing relationship is a **gap** |
| Component Name | `software_Package.name` | covered |
| Component Version | `software_packageVersion` | covered |

### Practices and Processes

Process observations, not fields to fill: Accommodation of Updates (re-run
`loom` -- covered), Coverage (the full Python dependency graph -- covered; a
mixed-ecosystem project has real gaps outside Python, see `sbom-generate`'s
"Known limitations"), Distribution and Delivery and Frequency (out of scope),
Explicitly Identifying Unknown Information (the `"unknown"` placeholder and, for
a licence a source calls unknown, `NoAssertionLicense` -- covered; an unstated
licence has no relationship, and the final report follows the same convention
for anything the user declines to answer), Machine-Processable Data (SPDX 3
JSON-LD -- covered).

### Checker (`-c cisa2026`, rules `BOM-CISA2026-<id>`)

14 of 23 rules are checked: META-001 author (`createdBy`, any value, so the
default software agent passes), META-003/-004 format name and version
(`specVersion`), META-005 generation context, META-006 timestamp, META-007 tool
name (`createdUsing`), COMP-001 producer (`originatedBy` on every package),
COMP-002 dependency relationship (document-level), COMP-003/-004 hash (any
`Hash` with a value, so the main package's Merkle root passes), COMP-005
identifiers, COMP-006 licence (`hasDeclaredLicense` only; a dependency's
licence from PyPI or its installed copy is declared), COMP-007 name, COMP-008 version.
`out-of-scope`: META-002 signature, META-008 tool version, META-009 SBOM
version, PP-001 to PP-006. Usual misses (all in `cisa2026-expected.tsv`):
COMP-001 for every dataset and for a model whose source names no producer,
COMP-002 for a single-model SBOM, COMP-006 for dependencies (their licence is
concluded) and for a model whose source states no licence, COMP-008 for a model
file that states no version, and COMP-003/-004 for a Hugging Face model or any
dataset outside `loom.run` (no hash).

## G7 SBOM for AI 2026 (additive -- apply only when an `ai_AIPackage` is present)

Moved to [`minimum-elements-g7.md`](minimum-elements-g7.md): every cluster
(Models, System Level Properties, Dataset Properties, Infrastructure,
Security Properties, KPI), what the checker reads and what the user must
supply.

## BSI TR-03183-2 v2.1 (SBOM content, section 5.2; checker `bsi`)

Moved to [`minimum-elements-bsi.md`](minimum-elements-bsi.md): element table,
what Pitloom writes and what the user must supply.

## Optional extra check (not a required step)

The community `ntia-conformance-checker` (`sbomcheck`) checks an SPDX 3
document against all five standards. How to install it, run it and read its
outcomes, and what to do per `missing` rule: `minimum-elements-workflow.md`
("Cross-check with the checker"). It is optional and never replaces the
mandatory `sbom-validate` pass
(<https://github.com/bact/pitloom/blob/main/skills/sbom-validate/SKILL.md>;
minimal fallback: `pip install "pitloom[validate]>=0.25.0"` then
`loom fragment validate <file>`).
