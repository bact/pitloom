---
Created: 2026-11-14
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Renames and migration: every old term to its new one

See also: [README.md](README.md) (the claim model and key table),
[method.md](method.md) (old `Method` values, the full table),
[source.md](source.md), [asserter.md](asserter.md),
[basis.md](basis.md), [change.md](change.md),
[conflict.md](conflict.md), [reason.md](reason.md),
[resweep-rulings.md](resweep-rulings.md) (the rulings of 2026-11-28,
written in here as hazards 16 to 21).

**Status:** draft; nothing here is built. Inventory of the code at
`main` 257b7260 (2026-11-14): 27 fixed and 9 dynamic source label forms,
29 method values, 5 roles, 5 evidence levels, 6 reason codes, 15 segment
keys, 37 selection sites, 7 declared-or-concluded paths; 194 of 902 test
files hold a provenance literal. Re-based on `main` dfa11c14 (release
0.25.1) on 2026-11-28 ("Swept against `main` again", below): 31 method
values, the same 5 levels, 6 reason codes and 15 keys (grep); every
fixed label of the table below still written (grep). Test files holding
a provenance literal: 175 of 1,158 `.py` files, by the pattern
`Source: `, `Method: `, `Role: `, `Evidence: `, `| Field: `, the JSON
keys `"method"`, `"evidence"`, `"role"`, and the values `not_measured`,
`measured_stat`, `sbomAuthorSupplied`, `externalReported`,
`Normalized-From`, `Deprecated-License-Id`, `resolved_lockfile`,
`licenseid_detection` (grep); the count of 2026-11-14 used another
pattern, so the two do not compare.

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
| reason codes | the taxonomy's own closed list, which a catalogue code maps to (ruled 2026-11-28, C2; [reason.md](reason.md); the list itself is not agreed). `main` renamed two since the inventory (`timeout` to `download-timeout`, `network-failed` to `download-network-failed`) |
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
| `installed metadata \| Package: <name> \| File: <RECORD entry>`, a licence file of an installed `.dist-info` (on `main` since 075195ea; `_deps_license_files.py:136-141`, read at dfa11c14) | open: `installed metadata` with the file as `Container`, or the file's own name | open: `environment` or `package-file` ([source.md](source.md), "Open points") |
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

- `TRANSPARENT_SOURCES`, `is_license_concluded`, `_source_name`:
  replaced by the kind and the asserter. `THIRD_PARTY_SOURCES` is gone
  already (bdf35a29, pull request 569), and `is_license_concluded` now
  asks only whether a source is named
  (`assemble/spdx3/_provenance_encoders.py:70-79`, read at dfa11c14).
- `GENERATED_METHODS`: replaced by `Method: synthesized`.
- `_KEY_MAP`'s `field` to `location` rename: one name in both forms.
- The licence slot rule: replaced by the asserter table. On `main` it
  has three modes (`assemble/spdx3/deps_license.py:164-202`, read): one
  licence, declared unless it has no source; two candidates, declared
  and concluded (the main project's own files, G2); and, since
  bdf35a29, two declared (a dependency's licence file beside its stated
  text, both candidates `role: declared`, `:296-305`).

## Hazards for the code stage

1. **The document UUID.** The `locked_dependencies` provenance string is
   hashed into the document UUID. Renaming a label or method there changes
   every SPDX id of such a document. Seed the UUID from the data (the lock
   source kind and the pins) before the rename, in its own change. Holds
   at dfa11c14 (read): `core/models.py:192-199`; the strings come from
   `extract/lock/cascade.py:274-285` and the hand-built
   `extract/project/pyproject.py:358`.
2. **Provenance strings used as data.** Each site needs a typed value
   carried beside the string first. At dfa11c14 (read), the five of the
   base: `extract/project/_setuptools_options.py:225,307` (re-parse) and
   `:456` (whole-string `==`); `_optional_dependencies.py:61-62`;
   `_setuptools_dynamic.py:288-289`; `extract/lock/cascade.py:240-262`;
   `extract/scanner.py:231` (prefix rewrite, since 7e5d3715 also of each
   dataset's provenance, `:216-232`) and `:275` (the same rewrite of log
   text). Not in the list before:
   - `assemble/spdx3/_license_elements.py:318-326` (`_is_noted`:
     whole-string `!=`, and a re-parse for `normalized-from`; new in
     4eed8f25);
   - `assemble/spdx3/deps_license.py:216` (`is_license_concluded` on the
     parsed string);
   - `assemble/spdx3/_fragments_generated.py:61,73`,
     `_fragments_model_names.py:89-90`, and `_fragments_evidence.py:62,71`,
     a substring test `NOT_MEASURED in (obj.statement or "")` on the
     spelling `not_measured` (hazard 6);
   - `assemble/spdx3/deps_installed.py:295`: conflict candidates deduped
     by `(value, role, source)`, the provenance string in the key;
   - `export/_spdx3_credentials/_find.py:140,177`: the credential scan
     reads the comment form and the fields Annotation (added by
     04f2d124, after the base);
   - `scripts/extract_wheel_sbom.py:51,112-125`: a regex on
     `content_type: ... | (Method|Role): ` and the JSON `method`, `role`.
3. **Strings a grep misses.** Suffix constants (`" | Method: comma_list"`)
   and f-strings in `extract/ai_model/` build segments without the builder.
   Route every one through the builders before renaming. Holds: 118
   hand-built segment lines, 58 under `extract/ai_model/`, the same at
   6cb6183f and dfa11c14 (grep); the lint test is still loose for
   `Field:` and `Method:` (`tests/test_provenance_builders_lint.py:44,57`).
4. **Licence output changes.** Dependency licences from PyPI and the
   installed copy move from concluded to declared; a `LICENSE` match beside
   a manifest licence moves from concluded to declared, and two that differ
   are both declared; `CITATION.cff` stops being a second opinion. The
   licence points that were parked are ruled (2026-11-19 to
   2026-11-23;
   [asserter-licence-points.md](asserter-licence-points.md)): among
   them, `CITATION.cff` against `codemeta.json` and a model file
   against its card are both declared, and Pitloom alone writes
   no concluded licence. This reverses readings: run a probe corpus
   through HEAD and the tree and list every changed relationship.
   Half done on `main`: bdf35a29 (pull request 569) made a dependency's
   licence from PyPI, its installed metadata or its installed licence
   files declared, and a stated text beside a different file licence two
   declared licences with a conflict. Left (read at dfa11c14): a
   project's `LICENSE` match beside a manifest licence is still
   concluded (`extract/_license.py:159-178`; `resolve_license_concluded`,
   `:149-156`, also used by `_embed_overlay.py:71-88`), and the default
   `Source: LICENSE | Method: licenseid_detection` remains
   (`assemble/spdx3/deps_license.py:522-527`). `CITATION.cff`: not
   checked again.
5. **Fragments in the wild.** A fragment written with `Role: inferred` must
   still be read (as `Asserter: ai-agent`). Read the old keys and values for
   one release; write only the new ones.
6. **Readers of the comment form.** The fragment merge reads `method` and
   `evidence` back from the element comment and the `fields` Annotation
   (`_fragments_generated.py`, `_fragments_evidence.py`,
   `_fragments_model_names.py`); they move to the class and basis names.
   Holds at dfa11c14: `_fragments_generated.py:44,61,73,113-126`,
   `_fragments_evidence.py:38,62,71,73,109`,
   `_fragments_model_names.py:50,89-90` (read).
7. **Schema versions.** `fields/1` to `fields/2`, `conflict/1` to
   `conflict/2`, `enrichment/1` to `enrichment/2`. Checked at dfa11c14
   (read): `unification/1` (`schema`, `kind`, `criterion`, `unified`,
   `fragments`) and `artifact-metadata/2` (`format`, `metadata`,
   `truncated` and the budget keys) carry no renamed key
   (`assemble/spdx3/provenance.py:153-162,232-242`); they stay. The
   strings that move with a schema: `provenance.py:62,83,86,89` and
   `_provenance_encoders.py:107-108`; the configuration value
   `DEFAULT_PROVENANCE_SCHEMA = "pitloom/1"` and
   `KNOWN_PROVENANCE_SCHEMAS` (`core/provenance.py:33-36`); the message
   text "one of pitloom/1" (`messages/_config_place.py:253`);
   `annotation_fields_statement` (`provenance.py:514`); and the
   credential scan's own literal `PROVENANCE_SCHEMA`
   (`export/_spdx3_credentials/_fields.py:135`), compared with `==` at
   `_find.py:140`: a new schema silently stops the splitting of notes
   there. The comment form carries no version.
8. **Drift guards to update:** `tests/test_provenance_method_rows.py`,
   `tests/test_provenance_builders_lint.py`,
   `tests/test_provenance_key_sets.py`, `tests/test_provenance_hostile_*.py`,
   `tests/messages/test_drift_sources.py`,
   `tests/messages/test_drift_quotes.py` (it quotes "dropped its
   not_measured provenance", `:187`); all at dfa11c14 (read). Also
   `tests/provenance_helpers.py`,
   `tests/extract/dataset/test_provenance_hostile_labels.py`, and the
   manual check `scripts/manual_cli_checks/_checks_loom.py:357-359`
   (`Evidence: not_measured | Reason: over-cap`,
   `Evidence: measured_stat`). Most tests compare whole strings: 561
   lines with a `"Source: ` literal in 141 files, no shared helper
   (grep).
9. **Docs and skills** that quote a value: 17 pages under `docs/`, 12 files
   under `skills/` (the inventory lists them); skills quote literal strings
   an agent writes, so they change in the same PR as the reader. Counted
   again by the pattern of the status line (grep): 11 docs and 13 skill
   files at the base, 17 and 18 at dfa11c14. Of those, generated from
   the message catalogue:
   `docs/message-codes-{datasets,files,fragments,licences}.md` and
   `skills/*/references/messages-{datasets,files,fragments,licences}.md`
   (hazard 17).
10. **Missing `Evidence` read as declared.** `core/evidence.py`
    (`_entry_rank`) ranks an entry with no `Evidence` segment as
    `declared`. `Basis` is always written (ruled 2026-11-23), so the
    new writer leaves none out; an old entry with no segment keeps
    the old reading. Holds: `core/evidence.py:221-224` (read at
    dfa11c14).
11. **Detail level `minimal` changes output.** Today it drops entries by
    source label (`TRANSPARENT_SOURCES`), so a plain read from
    `PyPI JSON API`, `installed metadata`, `CITATION.cff` or
    `codemeta.json` is kept. The new rule (README, "Use cases") drops a
    plain `originator` read from any source. List the entries that go.
    Holds: `_provenance_encoders.py:22-32,49-67` (read at dfa11c14).
    Also: element ids are counters per document
    (`core/models.py:223-229`), so a fields Annotation kept or dropped
    renumbers the later `Annotation-n` ids.
12. **The released principle calls an API value `declared`.**
    [evidence-levels.md](../evidence-levels.md) lists an API response
    under `declared` (`:47,181`, and the rule's full text at `:240-254`,
    "The `AGENTS.md` rule"). The "caps bound reading" bullet of the
    agent instructions no longer names the API since 202d379a
    (`AGENTS.md:47` at dfa11c14: "**declared** (with its source, never
    passed off as measured)"), but it spells `not_measured` (hazard 14).
    A value the API's party computed becomes
    `detected` (ruled 2026-11-16); both texts change with the code.
    `core/evidence.py` ranks a level it does not know as `declared`
    (`_entry_rank`): give `detected` and `inferred` an explicit rank,
    with `declared`, below `measured` (still so: `core/evidence.py:224`,
    read at dfa11c14). Unchanged: a value Pitloom did
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
    2026-11-22; 9 at dfa11c14, grep: also
    `docs/ai-model-scan-limits-caps.md` and
    `skills/sbom-generate/references/known-limitations.md`; 3 of the 9
    are generated from the catalogue). The new names are chosen with the code; "evidence
    level" in prose becomes "basis".
15. **A project directory given to `embed-wheel` is taken at the
    user's word** (ruled 2026-11-23: its licence file is the
    wheel's own;
    [asserter-licence-points.md](asserter-licence-points.md)). A name
    check exists already, for the authors only:
    `adopt_project_authors` compares the PEP 503 names and on a
    mismatch warns (`metadata-conflict`) and keeps the wheel's authors
    (`_embed_overlay.py:119-129`, read at dfa11c14). No version is
    compared, and the licence is still taken with no check
    (`add_concluded_license`, `:71-88`). Extend the comparison to the
    version and to the licence, with the `WARNING:`, before a wrong
    directory can make a declared licence or a conflict.
16. **The reason mapping** (ruled 2026-11-28, C2;
    [reason.md](reason.md)). A reason is the taxonomy's own closed list
    and a catalogue code maps to it: one table from each catalogue code
    that can stand behind a recorded outcome to its reason, and a drift
    test that holds the two together, in place of the equality that
    `tests/messages/test_drift_sources.py:22,55-57` holds today. The
    list is not agreed (its six classes are a proposal). Later, after
    the code stage and not a condition of it, the catalogue may make its
    families the same as the reasons, the variants below them for
    advice.
17. **Catalogue lines that quote old terms change in the same
    change.** The catalogue says a provenance term in its lines and
    texts (read at dfa11c14): `caller-info-unreadable`, a `WARNING:`
    line naming "Source ... 'unknown'; Method: inspect_caller"
    (`messages/_loom_sdk.py:33-41,57-58`); `generated-value-conflict`,
    an `INFO:` line "dropped its not_measured provenance"
    (`messages/_fragments_merge.py:153-157,173-175`); the `did` texts of
    `file-unreadable` and `dir-unlistable` ("Evidence: not_measured |
    Reason: ...", `messages/_file_unreadable.py:101-102,263-264`) and of
    the `license-expression-*` entries ("Method: licenseid_resolution,
    Resolution-1", `messages/_license_expression.py:136-137`). The
    taxonomy leads and the message is reworded to fit it: the lines in
    `src/pitloom/messages`, the pages written by
    `scripts/generate_message_reference.py` (`docs/message-codes-*.md`,
    `skills/*/references/messages-*.md`) and `test_drift_quotes.py` move
    in the change that renames the term. Credential lines print
    pointers built from the parsed key names (`/comment/<field>/<key>`,
    `export/_spdx3_credentials/_find.py:177-182`), so they move too.
18. **The outcome of a source** (ruled 2026-11-28, C1;
    [basis.md](basis.md#outcome-of-a-source)). A source that Pitloom
    failed or refused to read is recorded once per source, on the
    element, for any field: a new record shape, so a schema version of
    its own or a new version of the one it sits in. Where it sits is
    open.
19. **`tie-break` and the sites that drop a loser** (ruled 2026-11-28,
    C3; [conflict.md](conflict.md)). A selection by the tool's fixed
    order is recorded as rule `tie-break`; `no-rule` keeps its real
    sites. A site that drops the loser today is work for this stage, and
    one that moves to `no-rule` loses a value written today: a sweep of
    output before and after. Which sites drop a loser is in the table
    "Sites of rules 9 and 10" of
    [conflict.md](conflict.md#sites-of-rules-9-and-10), read at
    dfa11c14.
20. **`escaped`, and `cut` at `WARNING:`** (ruled 2026-11-28, C5;
    [change.md](change.md)). A fifth `Change` kind for a value written
    with escapes (`\uXXXX`, or U+FFFD); the message that a value was
    cut is at `WARNING:` already, with the code `over-cap`, at every cut
    site (`extract/ai_model/limits.py:225`,
    `assemble/spdx3/_ai_package.py:218`,
    `assemble/spdx3/provenance.py:361,365`): ruling C5 corrects the
    draft's table only, and no message changes level. Today a model name over the cap gets
    `Note: cut to 1024 characters` (`core/ai_metadata.py:117,529`, read).
21. **A released term is never renamed or reused** (ruled 2026-11-28,
    C10). A term that can no longer occur is marked retired and stays.
    The rule binds from the first release that writes the new
    vocabulary, so the old vocabulary is renamed once, here, and that
    first release must be right: every name, value and key of this
    folder is final when it ships.

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
| LicenseID is pinned `>=0.9.0,<0.10` (on dfa11c14: `>=0.10.0,<0.11`, `pyproject.toml:68`) | nothing to change: the draft's runs were on 0.9.0, and 0.9.1 gives the same output on what was tried ([asserter-licence-measurement.md](asserter-licence-measurement.md)); 0.10.0 not run for this page |
| An SPDX `project.license` beside `License ::` classifiers keeps the expression and drops the classifiers, with a `WARNING:` (`license-conflict`) | agrees with the ruling on the fields of one file. The `pyproject.toml` specification (source read 2026-11-23) says only that a build tool may raise an error when both are used |
| Several licence classifiers are recorded as one expression, joined by `AND`, with a `WARNING:` (`license-ambiguous`); so at the base too | ruled that day: it stays, with the operator marked as Pitloom's choice (`Change: expanded`, `Written`; [asserter-licence-points.md](asserter-licence-points.md)) |

Not checked again: the counts of pages and skills that quote a value
(hazards 9 and 14), and the page
`licence-variant-evidence.md` on `main`, whose difference from the
draft is known ([asserter-licence-points.md](asserter-licence-points.md),
option G).

## Swept against `main` again (2026-11-28)

`main` dfa11c14 (release 0.25.1), 238 commits after 6cb6183f. Read by
hand: the diff of `src/pitloom` for provenance strings, the builders and
their readers, the message catalogue entries that quote a provenance
term. The changes are written into the hazards above; the rest:

| Found on `main` | The draft |
| --- | --- |
| No new key, `Method` value, evidence level or reason code since 6cb6183f; `core/evidence.py` unchanged, `core/provenance.py` changed only for coded type errors (2eacceb9) | nothing to change |
| A dependency's licence files read when its Core Metadata names no SPDX licence (075195ea), with a new source form | a row in "Source labels"; its kind open ([source.md](source.md)) |
| A stated licence body that LicenseID reads as the file's licence is that licence, the text kept as `Normalized-From` (32f92cee; `_deps_license_files.py:181-183`) | a step of [change.md](change.md) (not this page's) |
| A licence-file search stops at a file of several licence texts (d49e7e20; `extract/_license.py:115-117`, `huggingface_fetch.py:306-307`) | a selection site of [conflict.md](conflict.md) (not this page's) |
| A Hub model the Hub does not know is refused; a URL revision is read at the default branch with a `WARNING:` | [source.md](source.md), the Hub row and rule C |
| The licence conflict of the main package still writes an Annotation and no warning (`deps_license.py:287-317`, read) | checked (the point was in the list "not checked again" above) |

## Gaps the inventory found, to fix at the reader

Not renames; noted so they are not lost.

- The wheel reader records no provenance for `description`,
  `requires_python`, `urls`; the sdist reader does.
- Hub licence detection has no `Tool`; in-package detection has.
- ONNX `type_of_model` is derived and has no provenance entry.
- `lower-bound`, `download-timeout`, `download-network-failed`,
  `lfs-pointer` have no writer.
