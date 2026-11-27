---
Created: 2026-11-23
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Catalogue PR 15 (fragments): plan

See also: [message-catalogue-pr15-build.md](message-catalogue-pr15-build.md)
(tests, steps and agents, gates, risks, unknowns),
[message-catalogue-migration-plan.md](../design/message-catalogue-migration-plan.md)
(row 15), [message-catalogue-pr10-11-lock-plan.md](message-catalogue-pr10-11-lock-plan.md)
(the conflict grid, section 3), [message-frames-forward.md](message-frames-forward.md)
("PR 15: fragments"), [message-catalogue-pr14-plan.md](message-catalogue-pr14-plan.md).

Status (2026-11-23): planned; built and merged as #513. Read-only plan written
by Opus against `main` at a45f9baf (#511 merged; ratchet 108); every line number
is that tree's. Branch `catalogue-fragments` (worktree
`.claude/worktrees/catalogue-fragments`). Nothing is decided: every Qn in
section 4 is the planner's recommendation.

Tags: (V) verified by reading or running on a45f9baf; (I) inferred.

## 0. Counts and ratchet

`--check` passes at **108** (V). Sites below come from
`python -m scripts.message_inventory --jsonl`, filtered with
`_scope.in_scope` and `not coded` (V).

| Module | Sites (line) | In PR 15 |
| - | - | - |
| `assemble/spdx3/fragments.py` | 191, 201, 396, 402, 510 | -5 |
| `cli/commands/fragment.py` | 72, 108, 125, 141, 163, 250, 278, 295 | -8 |
| `cli/commands/merge.py` | 59 | -1 |
| `assemble/spdx3/_fragments_envelope.py` | 114 | -1 |
| `_fragments_props.py` | 121, 195 | -2 |
| `_fragments_ids.py`, `_fragments_hashes.py` | 56; 62 | -2 |
| `_fragments_generated.py`, `_fragments_model_names.py`, `_fragments_evidence.py` | 188; 245; 120 | -3 |
| `cli/commands/enrich.py` | 74 (the "register the fragment" hint) | -1 (Q14) |
| `core/dataset_merge.py` | 101 | 0 (PR 17, Q13) |

**22 in the fragment modules** (the 2026-11-14 survey's 22 holds; the row's
"31" and its three family counts are stale). Landing: **108 to 85** with
Q13 and Q14 as recommended (86 without the enrich hint, 84 with
`dataset_merge.py`).

Out of the count already, with their reason (V):
- `_fragments_props.py:105,113`: DEBUG (keep, `Merge: ` text unchanged).
- `_fragments_unify.py:323` and `fragment.py:302`: helper calls; the text
  is counted in the helper body (`_fragments_hashes.py:62`,
  `_report_fragment`).
- `_fragments_equal.py:37,62`: internal, caught in `same_json`.
- `_fragments_read.py:45`, `fragment.py:237`, `fragments.py:217,228,390`,
  `merge.py:40,45`, `_generators_merge.py:69,72`,
  `core/_config_parse_fragment.py`: already coded
  (`text-malformed`, `input-not-found/fragment`,
  `license-relationship-invalid`, `input-not-found`, `config-invalid`).

## 1. Sites

Surfaces (V by reading; probes in section 2):
- **Project merge**: `merge_fragments` from `loom project`, `loom generate
  <dir>` (`assemble/_generators.py:396`), `loom embed-wheel`/`loom wheel
  --embed` with a project directory (`_embed_build_sbom.py:449`), the hook
  (`plugins/hatch.py:301`), the library (`generate_project_sbom`,
  `merge_fragments`), the Action (CLI).
- **`loom merge`**: `generate_merged_sbom` (`_generators_merge.py:76`), every
  `*.json` of a directory as a non-required fragment
  (`FragmentConfig(path=f)`, `required=False`).
- **`loom fragment list|validate`**: CLI only.

| # | file:line | Lvl | Text now (abridged) | Reached by | Untrusted text | Quoted by | Maps to |
| - | - | - | - | - | - | - | - |
| F1 | fragments:191 | W | `<id>'s <prop> references <target>, which isn't part of this document -- likely ... (regenerate the base SBOM, then re-run enrichment, before merging again)` | every merge | ids from fragments | `sbom-enrich/SKILL.md:223-231` (no quote), `docs/fragments.md:113` | `reference-not-found` W |
| F2 | fragments:201 | E | `N dangling reference(s) after fragment merge -- regenerate ...` (`FragmentMergeError`) | every merge | none | same | `reference-not-found` E |
| F3 | fragments:396 | W | `Failed to read SBOM fragment '<abs path>': <exc>[ -- merge will fail.]` | every merge | the exception text quotes fragment keys and values | `pre-merge-check.md:15` (no quote) | `fragment-unreadable`, `fragment-invalid` |
| F4 | fragments:402 | W | `SBOM fragment '<p>' is the document being merged into (<id>); skipped[ -- merge will fail.]` | project merge | id | `docs/fragments.md:111` | `fragment-unusable` |
| F5 | fragments:510 | E | `N required fragment(s) could not be merged: a, b -- check the configured path(s) under [tool.pitloom.fragment]` | project merge | configured paths | none | `fragment-missing` E |
| L1 | fragment:72 | I | `fragment validate: N document(s) valid` | `fragment validate` | none | `sbom-validate/SKILL.md:111` | Summary |
| L2-L4 | fragment:108, 125, 141 | W | F3's text (OS read, JSON parse, SPDX 3 parse) | `fragment list` | as F3 | none | as F3 |
| L5 | fragment:163 | W | `SBOM fragment '<p>' SHA-256 mismatch: configured <c>, actual <a>` | `fragment list` | configured text unchecked (Q8) | none | `fragment-digest-invalid` |
| L6 | fragment:250 | W | F4's text | `fragment list` | id | none | `fragment-unusable` |
| L7 | fragment:278 | W | `fragment list: project metadata unreadable, SAME_DOCUMENT unknown: <exc>` | `fragment list` | a coded metadata error's text, its code dropped | none | relay (Q9) |
| L8 | fragment:295 | I | `fragment list: no fragments configured` | `fragment list` | none | `sbom-enrich/references/examples.md:317` | Summary |
| M1 | merge:59 | I | `merge: merged N fragment(s)`; N counts files, not merged ones (S1) | `loom merge` | none | `manual_cli_checks/_sequences.py:195-196` (S6 pins `merged {count} `) | Summary (Q2) |
| E1 | envelope:114 | W | `merge: no fragment states a creation time; created set to 1970-01-01T00:00:00Z` | `loom merge`, `generate_merged_sbom` | none | none | Q1 |
| U1 | props:121 | W | `Merge: conflicting '<pyname>' on <Type> <id> '<name>': keeping <v>, dropping <v>.` | every merge (base or earlier fragment vs later) | values unbounded today (S7) | `docs/fragments.md:52,88`, `id-registry-log-lines.md:129` | `fragment-conflict` |
| U2 | props:195 | W | `Merge: conflicting '<pyname>' key '<k>' on ...` | every merge | same | `examples.md:258`, `minimum-elements.md:214`, `docs/fragments.md:48` | `fragment-conflict` |
| U3 | ids:56 | W | `Merge: <Type> '<name>' shares spdxId <id> with a <Type>[ of a different SHA256 hash]; keeping both, it gets new id <id>.` | every merge | name via `%r` | `examples.md:242`, `id-registry-log-lines.md:119` | `fragment-id-conflict` |
| U4 | hashes:62 | W | `Merge: <Type> '<name>' appears with two different SHA-256 hashes (a vs b); keeping both as separate elements.` | every merge | name | none | `fragment-hash-conflict` |
| G1 | generated:188 | I | `Merge: '<p>' on <el>: keeping the fragment's <v>, replacing the value generated from the model file, <v>.` | project merge | values | `docs/fragments.md:59` | `generated-value-conflict` |
| G2 | model_names:245 | I | `Merge: 'name' on <el>: keeping the fragment's <v>, dropping the project's <v>.` | project merge | names | `examples.md:251`, `id-registry-log-lines.md:124`, `docs/fragments.md:85` | `generated-value-conflict` |
| G3 | evidence:120 | I | `Merge: '<p>' on <el>: keeping the merged value, dropping the not_measured provenance of '<f>'.` | every merge | none | `minimum-elements.md:212,215` (`INFO: Merge: ...`) | `generated-value-conflict` |
| N1 | enrich:74 | I | `enrich: register the fragment under [tool.pitloom.fragment] and re-run 'loom project'/'loom generate' ...` | `loom enrich` | none | none | Summary (Q14) |

Out of PR 15, with reasons:
- `core/dataset_merge.py:101` and `core/dataset_names.py:76` (and the
  `_loom_dataset.py:326` call): model-card dataset references, not
  fragments. The conflict grid gave them to PR 17
  (`dataset-field-conflict`, `dataset-name-conflict`) (Q13).
- `cli/commands/utils.py:370,385` (`_validate_spdx3_documents`, the
  spdx3-validate relays shared by `fragment validate` and `validate-wheel`):
  PR 16, with `validate-wheel`, whose skill (`sbom-validate`) reads both.
- `enrich/__init__.py:54` (`Enricher ... failed`): final sweep.
- `license-relationship-invalid` (released in 0.24.0): its text is not
  changed (Q5).

## 2. Probes and surprises (run on a45f9baf; HEAD baseline for the sweep)

Probe trees were under the session scratchpad (`pr15-probe/`), deleted.

- **S1. `loom merge` counts files, not merged fragments (V).** A directory of
  8 `*.json`, 4 unreadable: four `WARNING: Failed to read ...` (no
  "merge will fail": `required=False`), then `INFO: merge: merged 8
  fragment(s)`, exit 0. The hook's summary uses `merge_fragments`' return
  value (`hatch.py:301`), so the two surfaces disagree.
- **S2. An empty `loom merge` succeeds (V).** A directory whose every
  fragment fails to read writes an SBOM with no element, dated
  `1970-01-01T00:00:00Z`, with E1 and `merged 1 fragment(s)`, exit 0. E1 is
  reachable only this way (S3): every element needs a `creationInfo` and
  every `CreationInfo` a `created`.
- **S3. A fragment whose `CreationInfo` lacks `created` crashes late (V).**
  It reads and merges, then the export raises: `ERROR: loom merge: Property
  'created' in CreationInfo (4457297536) is required (currently None)`, exit
  1, uncoded, with a memory address and no fragment named. E1 is printed
  first and is misleading.
- **S4. `fragment list` and the merge use two readers (V).** The list
  reads with `read_bytes` + `json.loads` + `deserialize_data`
  (`fragment.py:105-145`), the merge with `read_fragment_set` (lone-surrogate
  escape and the RFC 8785 check). A required fragment holding `2**60`
  lists as `REQUIRED=true ... SAME_DOCUMENT=false`, exit 0, while `loom
  project` fails on it. The list's docstring claims "the same per-fragment
  conditions".
- **S5. Dangling references print in set order (V, I).**
  `_find_dangling_references` walks `object_set.objects`, a `set`; six
  dangling relationships printed `r3 r1 r5 r0 r4 r2` (the same on five runs,
  by allocation; not promised across platforms or Pythons). The licence
  range check sorts.
- **S6. Absolute paths (V).** F3, F4, L2-L6 and the shipped
  `input-not-found/fragment` name the resolved absolute path; F5 names the
  configured `frag.path`. One page, two spellings (Q6).
- **S7. Merge values are unbounded (V).** `describe_value` is masked and
  repr'd but not cut: a fragment with a 10 MB `description` that conflicts
  prints a 10 MB `WARNING:` line. The `kept`/`dropped` fields cut at 120
  characters (`excerpt`).
- **S8. Exception text is attacker text (V).** A fragment key
  `https://u:pw@evil/\nWARNING: fake [over-cap]\x1b[31m` reaches F3 as
  `"Unknown property 'https://***:***@evil.example/\nWARNING: fake
  [over-cap]\x1b[31m'"`: masked and escaped (the `KeyError` repr and the
  handler), but a trusted-looking `[over-cap]` sits inside; the `failure`
  field (masked, one line, 500 characters, memory addresses dropped) must
  carry it.
- **S9. `sha256` in `[tool.pitloom.fragment]` is unchecked (V).**
  `_optional_str` only: `sha256 = "00"` is accepted and lists
  `SHA256=mismatch`. The `declared` field's shape (`[0-9a-f]{64}`) would
  raise on it (Q8).
- **S10. L7 drops a code (V).** The relayed text is a `metadata-invalid`
  line, and `relay_extra("metadata-invalid", "WARNING", text)` finds its
  WARNING twin; ruling 2 of the PR 8-12 plan (R6 general) says forward it.
- **S11.** `test_fragments_generated.py` is 851 lines, over the hard limit;
  any edit there splits it first. `test_cli_fragment_list.py` is 504,
  `test_drift_quotes.py` 538.
- **S12.** U3's text says "with a Agent" (examples.md quotes it); the
  rewrite drops the article.

## 3. Contradictions (plans versus the tree)

- **C1. Row 15's families are stale.** "fragment-unusable 13;
  merge-conflict-kept 9; source-conflict-kept 9" (31) predates the 2026-11-14
  survey (22) and the 2026-11-17 grid, which already names
  `fragment-conflict`, `generated-value-conflict` and `fragment-id-conflict`
  and rules out a generic `source-conflict`.
- **C2. The grid lumps U3 and U4 into `fragment-id-conflict`.** Their advice
  differs (an id reused for another element, against two files of one name
  with different bytes), so decision D splits them (Q4).
- **C3. The grid says "fragment against fragment" for U1/U2.** The canonical
  is the project's element in a project merge, and `ModelNames.finish`
  calls `_merge_scalar` for the base model's name; the line must not say
  "fragments" only.
- **C4. frames-forward counts "7 in scope, 4 WARNING, 3 INFO" for
  `Merge: `.** The tree has 8 in-scope `Merge: ` sites (U1 to U4, G1 to G3,
  plus E1's lowercase `merge: `); the counts hold for the capitalised ones.
- **C5. frames-forward: make `_fragment_read_failure_message` and
  `_same_document_message` public.** Rather than make two text builders
  public, PR 15 replaces them with say-helpers in `pitloom.messages`
  (`warn_fragment_unread`, `warn_same_document`): the text then lives in
  one entry, and `fragments.__all__` loses both names.
- **C6. Review round 2 (open) says `fragments.py` "relays a coded
  `json-malformed` / `file-unreadable` text".** On a45f9baf
  `read_fragment_set` raises plain exceptions (V); nothing coded is relayed
  there. The round's other item (`MemoryError` filed as an input fault at
  `fragments.py:393` and `fragment.py:126,135`) still holds and is fixed
  here (3.3 of the design).
- **C7. `input-not-found/fragment`'s `did` says "the merge then fails with an
  uncoded ERROR:".** F5 becomes coded; the `did` changes with it.

## 4. Design

### 4.1 Prefixes and subjects

- `MERGE_PREFIX = "Merge: "` (rule 2), one constant in
  `messages/_fragments_merge.py`, on every line said only while folding:
  U1 to U4, G1 to G3, F1 (Q5). Not on the read lines (F3/F4 are also
  `fragment list`'s), not on ERROR lines (the command frame stands there).
- Subjects (rule 1): `FILE=` for a fragment file (F3, F4, L2-L6, and the
  shipped `input-not-found/fragment` if Q6); `ELEMENT=` (a new subject key,
  value an spdxId through the masked `spdx_id` writer) for the merge lines.

### 4.2 Codes (new, `since="0.25.0"`; topic `fragments`, "SBOM fragments")

Templates are proposals; step 1 fixes them against `template_problem` and
`test_no_two_entries_share_a_line`.

| Code | Lvl | Cond | Effect / actor | Sites | Template (proposal) |
| - | - | - | - | - | - |
| `fragment-unreadable` | W x2 | unreadable | thinner / user | F3, L2 (`OSError`) | `FILE=%(file)s: could not read the SBOM fragment (%(failure)s); not merged`; required: `... the required SBOM fragment (%(failure)s); the merge will fail` |
| `fragment-invalid` | W x4 | invalid | thinner / user | F3, L3, L4 | `FILE=%(file)s: SBOM fragment is not valid JSON (%(failure)s); not merged`; `FILE=%(file)s: SBOM fragment is not SPDX 3 JSON-LD Pitloom can merge (%(failure)s); not merged`; each with its required twin (`; the merge will fail`) (Q3) |
| `fragment-unusable` | W x2 | unusable | thinner / user | F4, L6 | `FILE=%(file)s: SBOM fragment is the document being merged into (%(spdx_id)s); not merged` + required twin |
| `fragment-missing` | E | missing | not-written / user | F5 | `%(number)s required SBOM fragment(s) not merged: %(files)s; fix each as its WARNING says` |
| `fragment-digest-invalid` | W | invalid | none / user | L5 | `FILE=%(file)s: SHA-256 %(measured)s does not match the configured %(declared)s` (Q8) |
| `fragment-conflict` | W x2 | conflict | thinner / user | U1, U2 | `Merge: ELEMENT=%(spdx_id)s: %(property)s differs; kept %(kept)s, dropped %(dropped)s`; `Merge: ELEMENT=%(spdx_id)s: %(property)s key %(entry)s differs; kept %(kept)s, dropped %(dropped)s` |
| `fragment-id-conflict` | W x2 | conflict | weaker / user | U3 | `Merge: ELEMENT=%(spdx_id)s: a %(element_type)s here is held by a %(holder_type)s; both kept, the later is now %(new_id)s`; same id and type, SHA-256 apart: `...: two elements of one type hold different SHA-256; both kept, the later is now %(new_id)s` |
| `fragment-hash-conflict` | W | conflict | none / user | U4 | `Merge: ELEMENT=%(spdx_id)s: an element named %(name)s holds another SHA-256 (%(measured)s, not %(other_sha256)s); both kept` |
| `generated-value-conflict` | I x3 | conflict | none / none | G1, G2, G3 | `Merge: ELEMENT=%(spdx_id)s: %(property)s generated from the model file replaced by a fragment's; kept %(kept)s, dropped %(dropped)s`; `Merge: ELEMENT=%(spdx_id)s: name replaced by the one the fragments agree on; kept %(kept)s, dropped %(dropped)s`; `Merge: ELEMENT=%(spdx_id)s: %(property)s now holds a value; dropped its not_measured provenance of %(provenance_field)s` |
| `reference-not-found` | W, E | not-found | not-written / user | F1, F2 | W `Merge: ELEMENT=%(spdx_id)s: %(property)s names %(reference)s, which is not in the document; regenerate the base SBOM, then run the enrichment again`; E `%(number)s reference(s) to elements not in the merged document; regenerate the base SBOM, then run the enrichment again` |

Advice per family (sketch; decision G wording at step 1): unreadable:
read access, as `file-unreadable`; invalid: fix or regenerate the fragment,
check it with the pre-merge one-liner (`sbom-enrich`
`references/pre-merge-check.md`); unusable: point the entry at the
enrichment's fragment, not an earlier SBOM of the project; missing: each
fragment's WARNING above names why; digest: the fragment changed since its
digest was configured, re-pin or restore; conflict: "the SBOM states
<kept>; <dropped> is not recorded" (grid default), fix whichever source is
wrong and generate again; id: the fragment reuses an id of another element,
give it its own; hash: if they are one artefact a digest is stale, else
nothing; generated: nothing to do (by design); reference: as the
`dangling-references.md` causes, never retry the same merge, never write an
ID registry (copy the skill's rule).

Summaries (R1, out of the ratchet by kind; topic `fragments`): M1 `merge:
merged %(number)s fragment(s)` (Q2), L1 `fragment validate: %(number)s
document(s) valid`, L8 `fragment list: no fragments configured`, N1 the
enrich hint (Q14). Texts unchanged except M1's number.

E1: Q1 (recommended: removed with S2's fix; else `datetime-missing`, W,
weaker/user, `Merge: no fragment states a creation time; created set to
%(datetime)s`).

L7 (Q9): `relay_coded_warning(log, exc, quiet=False)` from
`messages/_metadata_say.py` (the shipped relay); stdout's `SAME_DOCUMENT=-`
already says the effect.

Changes to shipped codes:
- `input-not-found/fragment` (0.25.0, unreleased): `FILE=` subject and
  "SBOM fragment not found; not merged" (Q6); `did`: the merge then fails
  with `fragment-missing`.
- `license-relationship-invalid` (0.24.0): none (Q5).

### 4.3 Reading a fragment: one reader, one classifier

- `read_fragment_set` (the only reader; S4: `fragment list` calls it too,
  passing the bytes it read once for the digest, so a broken file still
  gets its hash) raises `FragmentReadError(stage, cause)`: stage `read`
  (an `OSError`), `json` (`UnicodeDecodeError`, `JSONDecodeError`,
  `RecursionError` from deep nesting), `spdx` (the deserialiser, the RFC
  8785 domain check). `InternalError` and `MemoryError` propagate before
  any wrapping (C6). The class goes in `_scope.DETAIL_EXC` (its text is the
  detail of the line, like `MemberReadError`).
- One say-helper, `warn_fragment_unread(log, path, exc, *, required)`, maps
  the stage to the line; `failure` is `exc.cause` through `failure_text`
  (masked, memory addresses dropped, cut at 500). `warn_same_document(log,
  path, spdx_id, *, required)` says F4/L6. Both in
  `messages/_fragments_say.py`; `warn_fragment_not_found` stays in
  `_input_not_found_say.py`.
- `FragmentMergeError` becomes `CodedValueError` (F2 with
  `reference-not-found`, F5 with `fragment-missing`);
  `FragmentLicenseRangeError` keeps its bases. The hook's ERROR
  (`code_extra_of`) and `cli_error_handler` then print `[code]`.
- `_find_dangling_references` returns sorted triples (S5).

### 4.4 Merge values (S7)

`kept`/`dropped` keep their writers (`excerpt`: one line, masked, 120
characters). The call site passes a `str` value as it is (quoted once) and
any other value as `describe_value(v)` wrapped so the writer does not quote
it again; step 1 picks the wrapper (a `str` subclass the writer knows, or a
new `value_text` writer in `_fields_fragments.py`). No import of
`pitloom.export` into `pitloom.messages` (cycle risk: `test_import_cycles`
both orders).

### 4.5 New fields (`messages/_fields_fragments.py`)

- `property`: the property as the SPDX 3 JSON-LD document names it
  (`description`, `software_downloadLocation`, `from`), never the binding's
  Python name (`from_`) (Q7). Shape `[A-Za-z][A-Za-z0-9_]*`.
- `reference`, `new_id`, `other_sha256`, `holder_type`,
  `provenance_field`: shapes as their neighbours (`spdx_id` masked free
  text; `measured`; `element_type` quoted). Reuse first: `spdx_id`,
  `file`, `files`, `failure`, `number`, `kept`, `dropped`, `entry`,
  `name`, `element_type`, `measured`, `declared`. Each new field gets a
  `SAMPLES` value.

### 4.6 Must not change

- SBOM bytes on every route (`--creation-datetime` pinned), except S2's
  empty `loom merge`, which then writes nothing (Q1).
- Exit codes, except S2 (exit 1) and S4 (`fragment list` exits 1 for a
  required fragment the merge rejects).
- Merge order and survivor rules (`docs/fragments.md`).

### 4.7 Example (stderr, `loom project` with three configured fragments)

```text
WARNING: FILE='frags/bad.json': SBOM fragment is not valid JSON (Expecting property name enclosed in double quotes: line 1 column 2 (char 1)); the merge will fail [fragment-invalid]
WARNING: FILE='frags/missing.json': SBOM fragment not found; not merged [input-not-found/fragment]
WARNING: Merge: ELEMENT=https://spdx.org/spdxdocs/demo#DatasetPackage-1: description differs; kept 'A small image dataset', dropped 'Another text' [fragment-conflict]
ERROR: loom project: 1 required SBOM fragment(s) not merged: frags/bad.json; fix each as its WARNING says [fragment-missing]
```

## 5. Rulings (Qn: recommendation, then the alternative)

**User, 2026-11-23: Q2 to Q16 accepted as recommended; Q1 takes the
alternative "in this PR"**: the empty-merge raise is built here, born
coded (no separate fix PR, no uncoded intermediate), E1 is removed with it,
and a CHANGELOG `Changed` bullet says `loom merge` of a directory whose
every fragment fails to read now exits 1 and writes nothing.

- **Q1. Empty `loom merge` (S2) and E1.** [A small fix PR before PR 15
  (PR 14 Q11's precedent): `generate_merged_sbom` raises when no fragment
  merged (`fragment-missing`'s second ERROR line, "no SBOM fragment in
  <dir> could be merged"), so E1 becomes unreachable and is removed.] Alt:
  keep the behaviour and code E1 as `datetime-missing`.
- **Q2. M1's count (S1).** [Count merged fragments: `generate_merged_sbom`
  gains a keyword-only `on_merged` callback or the CLI calls the three steps
  itself; S6's `merged {count} ` pin still holds.] Alt: say the summary
  inside `generate_merged_sbom` (a library entry point then prints an INFO
  count).
- **Q3. One family for "not a fragment".** [`fragment-invalid` for JSON and
  SPDX 3/RFC 8785 failures: one advice (decision D); two line pairs say
  which.] Alt: `fragment-malformed` (JSON) beside `fragment-invalid` (SPDX
  3), as `json-malformed`/`sbom-invalid` split for SBOM input.
- **Q4. U3 and U4 as two codes (C2).** [`fragment-id-conflict` and
  `fragment-hash-conflict`.] Alt: the grid's one `fragment-id-conflict`.
- **Q5. `Merge: ` scope.** [On U1 to U4, G1 to G3 and F1; not on F3/F4
  (shared with `fragment list`) nor on ERRORs; `license-relationship-invalid`
  (released) unchanged, noted as an inconsistency.] Alt: also reword the
  licence WARNING lines (a decision L wording change).
- **Q6. File spelling (S6).** [`FILE=` with the path as configured
  (`frag.path`; for `loom merge`, the directory as given joined with the
  name), the same as F5 and `PATH=`; `input-not-found/fragment` takes it too
  (0.25.0 is unreleased).] Alt: keep the absolute path Pitloom opened.
- **Q7. Property names.** [The JSON-LD key (`from`, not `from_`).] Alt: the
  binding's name, as today.
- **Q8. A malformed `sha256` (S9).** [`config-invalid` at read: "a SHA-256 in
  hex (64 characters)", upper case accepted and lower-cased; a build with a
  bad digest then fails, as every other bad `[tool.pitloom]` value does.]
  Alt: a free `configured` field that takes any text.
- **Q9. L7 (S10).** [Relay with `relay_coded_warning`; an uncoded exception
  then raises `InternalError`, held by a probe over PR 12's metadata error
  corpus through `project_document_id`.] Alt: a new fragments line for the
  uncoded rest (keeps the listing alive on a reader bug).
- **Q10. `fragment list` reads with the merge's reader (S4).** [Yes, in PR
  15: the two lines must share one classifier anyway.] Alt: a separate fix
  PR.
- **Q11. S3 (a `CreationInfo` without `created`).** [Roadmap and
  known-bugs: check required properties at read (a `fragment-invalid` line
  "misses a required property"); not in PR 15.] Alt: in the Q1 fix PR.
- **Q12. Effect of `fragment-conflict`.** [thinner: the dropped value is
  recorded nowhere (row 15's "weaker" fits `metadata-conflict`, which
  records both).] Alt: weaker.
- **Q13. `dataset_merge.py:101`.** [PR 17, as the grid says.] Alt: here as
  `dataset-field-conflict` (the dataset pages then split across PRs).
- **Q14. The enrich hint (N1).** [A Summary in PR 15, topic `fragments`.]
  Alt: final sweep.
- **Q15. Topic.** [New `fragments` page ("SBOM fragments"; about 15 KB, I);
  `targets` (26,728 B) and `files` (26,059 B) take nothing.] Alt: none
  fits.
- **Q16. `reference-not-found` name.** [Condition `not-found`, as an id
  named and looked up.] Alt: `fragment-reference-missing`.
