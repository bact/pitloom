---
Created: 2026-11-14
Last-Modified: 2026-11-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Renames and migration: every old term to its new one

See also: [README.md](README.md) (the claim model and key table),
[method.md](method.md) (old `Method` values, the full table),
[source.md](source.md), [asserter.md](asserter.md),
[basis.md](basis.md), [change.md](change.md),
[conflict.md](conflict.md).

**Status:** draft. Inventory of the code at `main` 257b7260 (2026-11-14):
27 fixed and 9 dynamic source label forms, 29 method values, 5 roles, 5
evidence levels, 6 reason codes, 15 segment keys, 37 selection sites, 7
declared-or-concluded paths; 194 of 902 test files hold a provenance
literal.

## Names that only shared a word

Three names clash with the provenance vocabulary and describe something
else. Each gets its own word.

| Today | What it is | Proposed | Note |
| --- | --- | --- | --- |
| `DatasetReference.role` (`trainedOn`, `testedOn`, ...) | the type of the model-to-dataset relationship | `relationship_type` | values stay: they are SPDX `RelationshipType` names; an unlisted one still falls back to `other` with a comment |
| fragment `role` in `[[tool.pitloom.fragment.files]]`, printed as `ROLE=` (issue #154) | a free label for what a fragment describes; the merge does not read it | `describes` | printed as `DESCRIBES=`; stays free text until the merge uses it |
| `--content-type-method`, `content-type-method` (`auto`, `magika`, `extension`) | which detector to use | `--content-type-detector` | values stay; the provenance it leads to is `Method: matched` (basis `detected`) or `synthesized` (basis `inferred`) |

Ruled 2026-11-23: the three words stand. Each is in the library API, the
configuration or the CLI, so the change is seen by a user; the project
keeps no backward compatibility yet.

## Role splits into Asserter and Basis

The key `Role` (JSON `role`) is retired. Each old value becomes a pair.

| Old `Role` | `Asserter` | `Basis` |
| --- | --- | --- |
| `declared` | `originator` | `declared` (the default) |
| `detected` | `sbom-tool`; or `originator` where the value was read as stated (a licence id in `CITATION.cff`; a dataset named in card front matter) | by the method class: `measured`, `detected` or `inferred`; `declared` for the `originator` case |
| `externalReported` | `other-party` | `declared` (the default); `detected` where the field table in [asserter.md](asserter.md) says the party computed it |
| `inferred` | `ai-agent` | `inferred` (the default) |
| `sbomAuthorSupplied` | `sbom-author` | `declared` (the default) |

`detected` splits: today it is fixed by the slot a value sits in, not by how
the value was obtained.

## Evidence becomes Basis

The key `Evidence` (JSON `evidence`) becomes `Basis` (JSON `basis`; ruled
2026-11-22, [basis.md](basis.md), "The name"). Its values:

| Old | New |
| --- | --- |
| `measured_read` (written, or "no segment") | `measured`: the default of a `derived` claim by `sbom-tool` (`content-hash`, `tensor-element-sum`, `element-count`); written, as every basis is |
| `measured_stat` | `measured`, `Technique: file-stat` |
| `declared` | `declared`: the one basis of `originator`, the default of `other-party`; `detected` where the field table says the other party computed the value (a change from the released reading) |
| `lower_bound` | `lower-bound` |
| `not_measured` | `not-measured` |
| (role `detected`) | `detected`: the default of a `matched` claim |
| (role `inferred`) | `inferred`: the default of `ai-agent` and of a `synthesized` claim |
| outcome `declared_only` | dropped: the outcome is `used`; the claim's `Asserter` and `Basis` say the rest |
| reason codes | unchanged by this redesign; `main` renamed two since the inventory (`timeout` to `download-timeout`, `network-failed` to `download-network-failed`) |
| skills' `Reason: <free text>` | `Note: <free text>` |

## Source labels

| Old label | New label | Kind |
| --- | --- | --- |
| `pyproject.toml`, `setup.cfg`, `setup.py` | same | `manifest` |
| `Hatchling build backend` | same | `build-backend` |
| `wheel METADATA`, `sdist PKG-INFO` | `METADATA`, `PKG-INFO`, with `Container:` the archive | `core-metadata` |
| `<name>.egg-info \| File: PKG-INFO` | `PKG-INFO`, `Container: <name>.egg-info` | `core-metadata` |
| lock file names | same | `lock-file` |
| `requirements.txt` | same | `pin-file` |
| licence file names, `CITATION.cff`, `codemeta.json`, version files, a project file | same | `package-file` |
| a model file name; `downloaded file`; a dataset path | the file name | `artifact-content` |
| `wheel filename` | the file name, `Location: name` | `artifact-name` |
| a file with `Method: lfs_pointer` | the file name | `pointer` |
| `README.md`, a Croissant file | same | `card` |
| `Hugging Face Hub` | `Hugging Face Hub API`; or the card or file name with `Container:` the repository | `registry`; `card`; `repository` |
| `PyPI JSON API`, `PyPI` | same | `registry` |
| `installed metadata`, `deployed package metadata` | `METADATA`, `Container:` the environment | `environment` |
| `pipdeptree`, `pipdeptree (deployed environment)` | `pipdeptree` | `environment` |
| a caller script path | same | `caller` |
| `SBOM author` | the session, or the flag or config key that carried the value | `session`, `config` |
| `AI agent`, `<agent> (<vendor>)` | the source the agent read; the agent goes in `Tool` | by that source |
| `Pitloom generator` | no source | - |
| `unknown`, `Unknown source`, `lock file`, `LICENSE` (default), `AI model metadata`, `model file / Hugging Face Hub`, `Dataset metadata` | no label: record the real source at the reader, or none | - |
| `setup.py, setup.cfg` and other comma-joined labels | one claim per file | `manifest` |
| free text with no key (`Version resolved: Project lock file`, `Phantom dependency bundled in distribution artifact`) | a claim with `Rule:` or a `Note:` | - |

## Keys

| Old | New |
| --- | --- |
| `Field` (JSON `location`) | `Location` |
| `File` | `Container`, or the label itself |
| `Normalized-From` | `Written` |
| `Deprecated-License-Id` | `Superseded` |
| `Method` | `Method` (class) and `Technique` |
| `Role` | `Asserter` and `Basis` |
| `Evidence` | `Basis` |
| skills' `Date`, `Overrides` | `Note`, or registered as keys if the skills need them parsed |

## Selection facts that sat in other keys

| Old | New |
| --- | --- |
| `Method: latest-release` | `Rule: latest` |
| `Method: running-environment` | `Rule: running-environment` |
| `Note: supersedes <lock>` | a conflict record with `rule: source-order`, or nothing when the two agree |
| `Version resolved: ...` | `Rule: explicit-pin` or the source kind (`lock-file`, `environment`) |

## Code that goes away

- `TRANSPARENT_SOURCES`, `THIRD_PARTY_SOURCES`, `is_license_concluded`,
  `_source_name`: replaced by the kind and the asserter.
- `GENERATED_METHODS`: replaced by `Method: synthesized`.
- `_KEY_MAP`'s `field` to `location` rename: one name in both forms.
- The two-candidate licence slot rule (`license_concluded` filled or not):
  replaced by the asserter table.

## Hazards for the code stage

1. **The document UUID.** The `locked_dependencies` provenance string is
   hashed into the document UUID. Renaming a label or method there changes
   every SPDX id of such a document. Seed the UUID from the data (the lock
   source kind and the pins) before the rename, in its own change.
2. **Provenance strings used as data.** Five sites compare or re-parse a
   provenance string (`_setuptools_options.py` whole-string equality and
   re-parse, `_optional_dependencies.py`, `_setuptools_dynamic.py`,
   `lock/cascade.py`, `scanner.py` prefix rewrite). Each needs a typed value
   carried beside the string first.
3. **Strings a grep misses.** Suffix constants (`" | Method: comma_list"`)
   and f-strings in `extract/ai_model/` build segments without the builder.
   Route every one through the builders before renaming.
4. **Licence output changes.** Dependency licences from PyPI and the
   installed copy move from concluded to declared; a `LICENSE` match beside
   a manifest licence moves from concluded to declared, and two that differ
   are both declared; `CITATION.cff` stops being a second opinion. The
   licence points that were parked are ruled (2026-11-19 to
   2026-11-23; [asserter-licence.md](asserter-licence.md)): among
   them, `CITATION.cff` against `codemeta.json` and a model file
   against its card are both declared, and Pitloom alone writes
   no concluded licence. This reverses readings: run a probe corpus
   through HEAD and the tree and list every changed relationship.
5. **Fragments in the wild.** A fragment written with `Role: inferred` must
   still be read (as `Asserter: ai-agent`). Read the old keys and values for
   one release; write only the new ones.
6. **Readers of the comment form.** The fragment merge reads `method` and
   `evidence` back from the element comment and the `fields` Annotation
   (`_fragments_generated.py`, `_fragments_evidence.py`,
   `_fragments_model_names.py`); they move to the class and basis names.
7. **Schema versions.** `fields/1` to `fields/2`, `conflict/1` to
   `conflict/2`, `enrichment/1` to `enrichment/2`. To check: whether
   `unification/1` and `artifact-metadata/2` carry a renamed key.
8. **Drift guards to update:** `tests/test_provenance_method_rows.py`,
   `tests/test_provenance_builders_lint.py`,
   `tests/test_provenance_key_sets.py`, `tests/test_provenance_hostile_*.py`,
   `tests/messages/test_drift_sources.py`,
   `tests/messages/test_drift_quotes.py`.
9. **Docs and skills** that quote a value: 17 pages under `docs/`, 12 files
   under `skills/` (the inventory lists them); skills quote literal strings
   an agent writes, so they change in the same PR as the reader.
10. **Missing `Evidence` read as declared.** `core/evidence.py`
    (`_entry_rank`) ranks an entry with no `Evidence` segment as
    `declared`. `Basis` is always written (ruled 2026-11-23), so the
    new writer leaves none out; an old entry with no segment keeps
    the old reading.
11. **Detail level `minimal` changes output.** Today it drops entries by
    source label (`TRANSPARENT_SOURCES`), so a plain read from
    `PyPI JSON API`, `installed metadata`, `CITATION.cff` or
    `codemeta.json` is kept. The new rule (README, "Use cases") drops a
    plain `originator` read from any source. List the entries that go.
12. **The released principle calls an API value `declared`.**
    [evidence-levels.md](../evidence-levels.md) and the "caps bound
    reading" bullet of the agent instructions list an API response
    under `declared`. A value the API's party computed becomes
    `detected` (ruled 2026-11-16); both texts change with the code.
    `core/evidence.py` ranks a level it does not know as `declared`
    (`_entry_rank`): give `detected` and `inferred` an explicit rank,
    with `declared`, below `measured`. Unchanged: a value Pitloom did
    not measure never gates a cap or a read.
13. **Format gaps ledger.** Each mapping that stretches an SPDX term (the
    licence table, the basis values, a passed-over candidate) gets an
    entry in [sbom-format-gaps.md](../sbom-format-gaps.md) with the code.
14. **Names that follow the key `Basis`** (ruled 2026-11-22). In the
    code: `core/evidence.py` (`EVIDENCE_KEY`, `evidence_segment`),
    `_fragments_evidence.py`, and the JSON key `evidence`. In documents:
    [evidence-levels.md](../evidence-levels.md), the principle "every
    fact has an evidence level" in the agent instructions, and 7 files
    under `docs/` and `skills/` that hold an `Evidence:` string (counted
    2026-11-22). The new names are chosen with the code; "evidence
    level" in prose becomes "basis".
15. **A project directory given to `embed-wheel` is taken at the
    user's word** (ruled 2026-11-23: its licence file is the
    wheel's own; [asserter-licence.md](asserter-licence.md)). No
    code compares the directory's name and version with the
    wheel's. Add the comparison, with a `WARNING:` on a mismatch,
    before a wrong directory can make a declared licence or a
    conflict.

## Checked on real output (2026-11-14)

38 SBOMs generated offline with `detail = "full"`: 20 fixture projects, 17
model fixtures of 10 formats, and Pitloom itself. 549 `fields` Annotations,
1,666 field entries, 4 conflict Annotations.

- **Method:** 13 distinct values met; each has a row in one of the two
  tables of [method.md](method.md). 1,576 entries have no method
  (`read`).
- **Source:** 413 distinct labels; each falls in one kind. 106 entries have
  no `Source` at all: free text held as a note (a declared requirement, a
  `Version resolved: ...` line). They become a `Value` on a `manifest`
  source, or a `Rule`.
- **Asserter:** no field entry carries a role today (0 of 1,666); only the 8
  conflict candidates do, all `declared`. Under the new rule every entry
  carries one.
- **Location:** 10 distinct locations hold a method or a tool in
  parentheses (`config.config.layers (count)`,
  `model_weights/data.pkl (fickling)`,
  `.npy header encoding (from format version)`). By [source.md](source.md)
  rule 6 they become `Technique: element-count`, `Tool: fickling`,
  `Technique: code-lookup`.
- **Not exercised:** `Evidence`, `Reason`, the PyPI download record, the
  Hub, datasets, enrichment and fragments (offline run, no such input). For
  those the table rests on the code inventory alone.

## Swept against `main` (2026-11-23)

The draft was written against 257b7260. `main` was dd31412b that day, 135
commits on. Checked by script: of the 904 code-quoted terms of the draft,
28 file paths and 170 identifiers; each that the base has, `main` has,
but one (`list_repo_files`). Read by hand: the changes to
`core/provenance.py`, `core/evidence.py`, `extract/_license_detect.py`
and the two provenance pages under `docs/`.

| Found on `main` | The draft |
| --- | --- |
| The Hub licence-file list is the `siblings` of the `model_info` answer | [source.md](source.md), the Hub row: the list is at that state now |
| Reason codes `download-timeout`, `download-network-failed` (were `timeout`, `network-failed`) | followed earlier that day ([basis.md](basis.md), reason codes) |
| Two more `Method` values, so 31: `one_weight_per_feature` (a CRFsuite parameter count, the feature count of its `FEAT` chunk) and `hub_dataset_id` (a GGUF training dataset's name, the Hub id in a URL) | `one_weight_per_feature` is `derived`, `element-count`, `measured` (ruled that day; [method.md](method.md), the technique table): the count is the one the `FEAT` chunk gives for itself, as a GGUF array gives its length. `hub_dataset_id` (ruled that day) is two things: for a name, `parsed` by the new technique `url-path`; for a location that Pitloom writes as the dataset's page where the file states the model-path form, `read` with `Change: respelled` and the stated URL in `Written` ([change.md](change.md)). Not taken for the location: `synthesized`, which has no key for the URL the file did state |
| `tensor_element_sum` also for PT2 (`data/weights/model_weights_config.json`) | added to the `tensor-element-sum` row |
| LicenseID is pinned `>=0.9.0,<0.10` | nothing to change: the draft's runs were on 0.9.0, and 0.9.1 gives the same output on what was tried ([asserter-licence.md](asserter-licence.md)) |
| An SPDX `project.license` beside `License ::` classifiers keeps the expression and drops the classifiers, with a `WARNING:` (`license-conflict`) | agrees with the ruling on the fields of one file. The `pyproject.toml` specification (source read 2026-11-23) says only that a build tool may raise an error when both are used |
| Several licence classifiers are recorded as one expression, joined by `AND`, with a `WARNING:` (`license-ambiguous`); so at the base too | ruled that day: it stays, with the operator marked as Pitloom's choice (`Change: expanded`, `Written`; [asserter-licence.md](asserter-licence.md)) |

Not checked again: the counts of pages and skills that quote a value
(hazards 9 and 14), whether the licence conflict of the main package
still writes no warning ([conflict.md](conflict.md)), and the page
`licence-variant-evidence.md` on `main`, whose difference from the
draft is known ([asserter-licence.md](asserter-licence.md), option G).

## Gaps the inventory found, to fix at the reader

Not renames; noted so they are not lost.

- The wheel reader records no provenance for `description`,
  `requires_python`, `urls`; the sdist reader does.
- Hub licence detection has no `Tool`; in-package detection has.
- ONNX `type_of_model` is derived and has no provenance entry.
- `lower-bound`, `download-timeout`, `download-network-failed`,
  `lfs-pointer` have no writer.
