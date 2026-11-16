---
Created: 2026-11-14
Last-Modified: 2026-11-16
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message catalogue PRs 6 and 7: ID registry ids, keys and saves

See also: [message-catalogue-migration-plan.md](message-catalogue-migration-plan.md)
(rows 6 and 7, R1), [message-frames-forward.md](message-frames-forward.md)
(rule 2, the `ID registry: ` literal),
[message-catalogue-families.md](../implementation/message-catalogue-families.md)
(PR 5, #485), [id-registry-followups.md](id-registry-followups.md)
("Message codes after catalogue PR 5").

Status: PR 6 merged (#486); PR 7 merged (#492, 2026-11-16; ratchet 328 to
316). What was built, and where it departs from
this plan (six summaries, not five; more `WARNING` twins; the deserialiser's
refusal coded `sbom-invalid`): [message-catalogue-families.md](../implementation/message-catalogue-families.md)
"ID registry saves, left-out files and summaries". The plan as written,
2026-11-14, on `main` 99483287 (PR 5 merged): every site below was listed
by `PYTHONPATH=src python -m scripts.message_inventory --jsonl` filtered by
`_scope.in_scope` and `coded`, then read in the source. Rulings: section 8.

## 0. Counts against the migration plan

The plan's classifier (`classify.py`, 2026-10-29) is not in the tree, so
its family split (collision 7, miss-new-id 7, key-decision 20, passthrough 1;
not-saved 5, left-out 6, summary 4) cannot be re-run. Re-listed by hand:
50 uncoded in-scope sites mention the registry, as the plan's 35 + 15. Three
belong to other PRs by family: `assemble/spdx3/_fragments_ids.py:56`
(`Merge: `, PR 15), `core/_config_parse.py:169` (config, PR 8) and
`extract/project/_sdist_scan.py:184` (`ARCHIVE=`, PR 16). So:

- **PR 6: 35 sites** (as planned), 366 -> **331**.
- **PR 7: 12 sites**, not 15, 331 -> **319** (built PR 6 ended at 328:
  `core/iri.py`'s three namespace raises became one; so 328 -> 316).

Also coded, at zero ratchet effect (bare `"%s"` relays, out of scope
today): `content_gate_message` (`_harvest.py:312,459,470`) and
`ambiguous_keys_message` (`cli/id.py:375`) in PR 6, `_persist.py:206` in
PR 7. Out of both: `_loom_model.py:130,284` and `_loom_caller.py:108,145`
(PR 17).

## 1. PR 6: ids, keys and lookups

Built in #486; the site table, entries, fields and helpers as built are in
[message-catalogue-families.md](../implementation/message-catalogue-families.md)
("ID registry ids and keys") and the generated `docs/message-codes-id-registry-ids.md`.
The plan's per-site table (35 sites) is in this file's history. Decisions kept
for PR 7 and later:

- **Topic and entries.** New topic `id-registry-ids`, module
  `pitloom.messages.id_registry_ids`; families `registry-conflict` (variants
  `/concurrent`, `/spelling`, `/held`, `/type`), `registry-hash-conflict`
  (`/gate`), `registry-hash-missing`, `registry-entry-missing` (stays a
  `WARNING`: no level change in a coding PR; level review in
  [id-registry-followups.md](id-registry-followups.md)),
  `registry-key-ambiguous`, `registry-path-key-unusable`,
  `registry-identity-missing`, `registry-key-moved`, `index-path-no-effect`.
  An INFO decision is coded by its condition (R1), actor `none`.
- **Reuse over new codes.** "No id left to mint" is a `registry-malformed`
  line; a non-IRI SBOM namespace on import is an `sbom-invalid` `WARNING`
  line with no `ID registry: ` prefix (its subject is the SBOM, Q2).
- **Wording.** `loom: ` -> `ID registry: ` (Q4); no trailing periods; `%r`
  and raw values become fields, a control character escaped (regression
  test). Every template starts with `REGISTRY_PREFIX` (rule 2).
- **Summary kind (R1).** `Summary(template, level="INFO")`: a `Line` without
  a code; `say_summary` renders through the fields with no `pitloom_code`;
  the inventory scope rule leaves a `say_summary` call out by its shape,
  never its text (a plain counted `log.info` stays counted); the generator
  lists a topic's summaries uncoded; `trusted_message` never trusts one.
- **Fields.** `spdx_id`, `claimant`, `entity` (URL credentials masked),
  `held` (sorted), closed `element_kind` and closed `KEY_REASONS` with a
  drift test; `_fields.py` split before it passed ~400 lines. The messages
  modules never import `pitloom.id_registry`.
- **Not in PR 6.** The remote registry's unpinned `INFO` (remote entries
  unbuilt) is born coded `revision-unpinned` in its own PR, which PR 14's
  Hub "without a pinned revision" `WARNING`s join.

## 2. PR 7: saves, left-out files, summaries, PR 5 leftovers

### 2.1 Sites

| # | Site | Level | Text today | Condition | Code / kind |
| - | - | - | - | - | - |
| 1 | `cli/id.py:226` (`_save`) | ERROR | `ID registry: failed to save {path}: {exc}` (`failed_to_save_message`) | inner exception | the inner code (2.2) |
| +0 | `id_registry/_persist.py:206` | WARNING | `"%s"`, same text | inner exception | the inner code, WARNING line |
| 2 | `id_registry/_persist.py:169` (`warn_no_registry_path`; callers `_persist.py:199`, `_loom_model.py:358`, `_generators_shared.py:112`) | WARNING | `no file path resolved; skipping auto-update.` | an in-memory registry, nothing to save to | `registry-file-missing` |
| 3 | `core/walk_rules.py:150` (`warn_registry_left_out`; callers `walk_rules.py:301`, `_embed_build_sbom.py:63`) | WARNING | `ID registry: %s is inside the project's file set; left out of it` | the registry is in its own input | `registry-conflict/file-set` |
| 4 | `_loom_dataset.py:486` (`REGISTRY_IN_DATASET_WARNING`) | WARNING | `loom: ID registry %s is inside dataset directory %r; left out of its Merkle root` | same | `registry-conflict/file-set` |
| 5, 6 | `cli/id.py:318,360` | ERROR | `print_error(str(exc), code=code_of(exc))` under `except (ValueError, OSError)` | relay | drop the `try`: `cli_error_handler` says it (relay shape, out of scope) |
| 7 | `cli/id.py:368` (`_import_failure_text`) | ERROR | `failed to import SBOM {path}: {exc}` for an uncoded exception | relay with own text | drop: the handler relays; each raise under `import_sbom` is coded after PR 6 (AST list in the PR) |
| 8 | `cli/id.py:214` | INFO | `ID registry: holds %d id(s)` | count | Summary |
| 9 | `id_registry/_persist.py:212` | INFO | `ID registry: added %d new id(s) to %s` | count | Summary |
| 10 | `id_registry/_persist.py:220` | INFO | `ID registry: updated stale entries in %s` | report | Summary |
| 11 | `cli/_id_entity.py:97` (`ENTITY_STORED_AS_INFO`) | INFO | `ID registry: -e %s stored as %s` | report | Summary |
| 12 | `cli/_id_target.py:201` | INFO | `ID registry: to use this registry, %s: id-registry = %s` | hint | Summary |

### 2.2 The save line (the PR 5 leftovers)

`failed_to_save_message` goes (it stacks `ID registry: `, names the file
twice and drops the inner code); the inner text already names the file as
given (`IdRegistry.path`, PR 5). The save adds no condition, so it says the
inner line (frames-forward, "Wrappers keep the inner code"):

- CLI `loom id generate` / `id import`: `print_error(str(exc),
  code=code_of(exc))`: one `ERROR:` line, its own code, exit 1.
- A run whose SBOM is written (`loom generate`, `project`, `wheel`,
  `embed-wheel`, the library, `loom.Run`): the same text as a `WARNING:`
  with the same code. Each `ERROR` line of `registry-malformed`,
  `-unknown-key`, `-wrong-format`, `-unusable` and `json-malformed` gains
  its `WARNING` twin (same template, built by a comprehension, decision E);
  `file-unreadable` has one. One helper `say_save_failure(log, exc, *,
  fatal)` in `pitloom.messages.id_registry`; an uncoded `ValueError`
  reaching it raises `InternalError` (none is known: `save()`'s no-path
  raise is guarded).
- An `OSError` on write (`os.replace`, permissions, a full disk): Q1;
  recommended `file-unwritable` (`FILE=%(file)s: could not write %(use)s;
  %(failure)s`, ERROR and WARNING, `use` = `for the ID registry`), topic
  `files`.
- `registry-file-missing` (`missing`, actor `caller`, effect `none`):
  `ID registry: no file to save to; the ids this run added are not saved`.
  Library only in practice (an `IdRegistry()` without `path`); the CLI and
  the hook always name a file.
- `registry-conflict/file-set` (advice: move the registry out of the
  project or dataset, or accept it): `ID registry: FILE=%(file)s: inside
  the project's file set; left out of it` and `ID registry:
  FILE=%(file)s: inside dataset directory %(dir)s; left out of its Merkle
  root`. Said once per run (the embed batch memo `_REGISTRY_LEFT_OUT`, the
  loom `_first_time` key), kept.

Fixed with it (verified in code):

- The build hook never saves the registry (`plugins/hatch.py` calls
  `resolve_registry` and `assemble_spdx3`, never `_sync_registry` or
  `persist_registry`), yet PR 5's `_DID` and `REGISTRY_UNUSABLE.did` say it
  re-reads the file to save; PR 7 rewrites both.
- `VERSION_LINE` loses its bracket advice: `version %(value)s, expected 4
  (no migration support)`. The advice is the entry's, by version; the line
  said "delete it" to a newer file too. Unreleased (0.24.1), no `replaces`.
- `loom id generate -e` logs its decision `INFO:`s before an `ERROR:` that
  writes nothing: `entity_entry` returns its notes, said after `_save`
  succeeds.

Left in [id-registry-followups.md](id-registry-followups.md): `loom id
generate ""` (a behaviour change, not a message), `option-invalid` exit 2
vs 1 (a reference note, not these families), the partly indexed registry.

## 3. Cross-PR split

PR 6: every condition met looking up, minting or keying an id, and the
summary mechanism. PR 7: saving, the registry inside its own input, the
other summaries, PR 5's leftovers; it needs PR 6's `Summary`,
`registry-conflict` and topic page.

## 4. Topic pages (guard 30,000 bytes, `generate_message_reference.py:143`)

Now: `id-registry` 10,399 bytes, `files` 22,582, `targets` 20,878. PR 6's
families (about 30 lines, 1.5 to 2 KB per entry) would put `id-registry`
near 27 KB, so PR 6 adds the topic `id-registry-ids` after `id-registry`
(`docs/message-codes-id-registry-ids.md`, the skills' copies, `mkdocs.yml`,
the index): about 18 to 22 KB; split conflicts from keys if over 26 KB.
`id-registry` with PR 7's twins: about 14 KB; `files` with
`file-unwritable`: about 24 KB.

## 5. Docs and skills to change

PR 6: `docs/id-registry-keys.md` (lines 79, 108, 117, 154, 183, 193-204,
224-241, the "Event | Line" table 252-263 gains a code column, 274-275
`loom:` lines); `docs/id-registry.md` (80, 156, 241, 277-279, 349);
`docs/python-api.md:470`; `docs/messages.md` (summary kind);
`skills/sbom-generate/references/id-registry-log-lines.md` (8.7 KB, 15
quotes: each bullet cites its code and the generated page instead of the
full text; it shrinks); `references/id-registry.md` (220 skipped PATH,
318 the `loom:` miss line); `skills/sbom-enrich/SKILL.md:295-296` (the
claim-collision quote: append `[registry-conflict]`, about 20 bytes of 251
headroom); `sbom-enrich/references/dangling-references.md:46`;
`references/known-limitations.md:306-309` (identity unknown).

PR 7: `docs/id-registry.md` (119-125 the stacked save line, 173 hint,
218-219 left out, 307 save WARNING, 337); `docs/id-registry-keys.md:303`
and `references/id-registry.md:245` (`VERSION_LINE`); `id-registry.md`
(261-262 hint, 272-273 left out, 309);
`id-registry-log-lines.md` (14-18, 84-90, 134);
`sbom-generate/SKILL.md:278-279` only if the pointer changes (319 bytes
headroom; prefer no body edit). Run `--quotes` before and after. No flag
or subcommand changes: no skill `description` or `_matrix_plan.py` edit.
Each entry's `advice` is the skills' agent instruction; the skills point
at the code's page and never copy it. Read changed skill files in full.

## 6. Tests

Per family, one file in `tests/messages/`, parametrised, short `ids=`:
PR 6 `test_registry_conflict.py`, `test_registry_keys.py` (hash, entry,
path key, identity, moved, index PATH), `test_summaries.py` (mechanism,
scope rule); PR 7 `test_registry_save.py`, `test_file_unwritable.py`.

- **Surfaces**: CLI (`loom id generate`/`import` stderr line, `[code]`,
  exit; `loom generate --id-registry` for the conflict and save WARNING),
  library (`pitloom_code` on the record via `caplog`; `generate_project_sbom`
  with an `IdRegistry`; `loom.Run` for the SDK lines), hook (a staged build
  with a registry holding a colliding id: the claim line coded; no save
  line, as the hook never saves, asserted), Action through the CLI.
- **Adversarial**: a newline, `\x1b` and a lone surrogate in a key, an
  spdxId, a claimant and a dataset name (the content-changed INFO printed
  `name` raw: fails on base); a URL dataset name with `user:pass@` masked in `entity`;
  a Windows registry path (`.\ids.json`, `C:\p\ids.json` through
  `PureWindowsPath` into the `file` writer) named as typed; the typed
  spelling (`./x/../ids.json`) kept in the save line; said once (claim per
  id, alias tie per type and key, outside-root per path, left-out per run
  and per embed batch, identity-unknown per batch) with a repeated input;
  sorted `held` lists under reversed input order (determinism).
- **Save (PR 7)**: one `ERROR:` line, `FILE=` once, `[registry-unusable]`,
  no second `ID registry: ` (fails on base); the WARNING twin with
  `pitloom_code`; an `OSError` on write by spying `os.replace` (not
  `chmod`, Windows); a coded inner and an uncoded one (`InternalError`).
- **Ratchet**: the summary rule exempts `say_summary` calls only (mutant:
  exempt by text). `A and B` rules (R-kept INFO only when `imported`;
  persist INFO only when `pending and added`): one test per leg.
- **Mutation targets**: `_session._claim`, `_persist.replay_changes`'s
  refusal loop, `persist_registry` added vs stale, `_dataset_key`'s reason,
  `say_save_failure` (coded/uncoded, fatal), `report_imported`'s
  `written()`, the scope rule.
- **Platform**: classify each file (`-m platform --collect-only -q`);
  left-out, skipped-directory, Windows-path and `os.replace` tests get
  `pytestmark = pytest.mark.platform`; label both PRs `test-all-os`.
- **Fail-on-base**: `PYTHONPATH` pinned to a 99483287 archive (PR 6), to
  PR 6's merge (PR 7). **Drift**: `REGISTRY_PREFIX` on every template;
  field tables against their source constants.

Ratchet: PR 6 **366 -> 331**: `id_registry._generate` 3->0, `_harvest`
2->0, `_registry` 4->0, `_session` 4->0, `_types` 1->0, `import_keys` 3->0,
`_persist` 4->3, `_loom_caller` 6->2, `_loom_dataset` 3->1,
`_loom_dataset_keys` 3->0, `_loom_model` 3->2, `assemble._model_generator`
1->0, `_document_file_hits` 1->0, `assemble.spdx3.ai` 1->0,
`cli._id_entity` 5->1. PR 7 **331 -> 319**: `_persist` 3->0, `cli.id`
5->0, `cli._id_entity` 1->0, `cli._id_target` 1->0, `core.walk_rules`
1->0, `_loom_dataset` 1->0. No `pitloom.id_registry.*` module is left in
the baseline.

Gates as policy. Manual checks: `_checks_core.py` and `_order_failures.py`
assert the save line (PR 7 updates them). Stderr sweep vs `main`:
identical but for `[code]` and the decided wording.

## 7. CHANGELOG

Fold into `[Unreleased]` (PR 6 is #486 unless an issue takes the number;
check `gh pr list --state all --limit 3` at PR time; PR 7's number is
asked):

- Added: "Input, option, SBOM, target and ID registry errors and decisions
  carry a message code; see `docs/message-codes.md` ([#482], [#485],
  [#486], [#492])".
- Changed, the reworded bullet gains: "`loom.run` ID registry lines start
  `ID registry:`" ([#486]).
- Fixed (PR 7; 0.24.0 printed `ID registry: failed to save '<abs>': ID
  registry file ...`): "A failed ID registry save prints one line naming
  the file as given, with its code ([#492])".

## 8. Rulings (maintainer, 2026-11-14: all four as recommended)

Q1: `file-unwritable` (new condition `unwritable`), PR 7. Q2: `FILE=`
after `ID registry: ` is the registry file only; PR 6 rewrites PR 5's two
lines. Q3: the summary kind covers the seven report lines. Q4: the SDK's
registry lines take `ID registry: ` in the PR that owns them; PR 17's list
drops them. The questions as asked:

- **Q1. A failed write: a new condition word?** [Add `unwritable` to
  `CONDITIONS` and a family `file-unwritable` in `files`: the advice
  (permissions, disk, read-only file system) is the same for every file
  Pitloom writes, and PRs 12 and 16 will need it for `-o`, fragments and
  wheels; decision D keeps one code.] Alternative, no vocabulary change:
  `registry-unusable/unwritable`, which a later `file-unwritable` could
  never absorb (decision L).
- **Q2. `FILE=` after `ID registry: ` names only the registry file?**
  [Yes. An indexed file or PATH is `PATH %(path)s` in the condition, and a
  line whose subject is another file (the SBOM's namespace) drops the
  prefix and names it `FILE=`, as its own family does. PR 6 then rewrites
  PR 5's two lines (`not inside the project root`, the unencodable file
  name), unreleased.]
- **Q3. Summary kind: pure counts only, or reports too?** R1 says "pure
  counts". [Reports too: the key written (`-e NAME stored as KEY`,
  `dataset X keyed by its path`, `model X keyed by the registry's file`),
  `updated stale entries`, and the config hint state what a run did under
  its own rule, with no condition to code; seven lines in all. A
  condition-bearing line never qualifies.]
- **Q4. The SDK's registry lines take `ID registry: `, not `loom SDK: `?**
  [Yes (rule 2: one literal per family); frames-forward's PR 17 list drops
  `_loom_caller.py:198-219` and `_loom_dataset.py:111,116`. `loom SDK: `
  stays for the SDK's own lines.]

## 9. Order, overlap, agents, risks

Order: PR 6 from fresh `main` in a new worktree; PR 7 after PR 6 merges,
in its own worktree from the new `main`. Never in parallel.

Overlap: `_persist.py` (6: line 117; 7: save, summaries), `cli/id.py`
(6: 375; 7: 214-368), `cli/_id_entity.py` (6: 109-148; 7: 97, deferred
notes), `_loom_dataset.py` (6: 348, 450; 7: 486),
`messages/_registry_file.py`, `_topics.py`, `_fields.py`. Only PR 6:
`id_registry/_types.py`; only PR 7: `core/walk_rules.py`.

Agents: PR 6, Opus for entries, fields, the summary mechanism and scope
rule; Sonnet for the 35 sites and tests, file ownership fenced (messages
vs `id_registry/` vs `_loom_*`, `assemble/`, `cli/`); Opus review, then a
fresh-context sweep. PR 7: Sonnet, Opus review of the save semantics.

Risks: stacked prefixes (a helper never adds `ID registry: `; a fixture
asserts no stderr line holds it twice); wording pinned by
`test_registry_harvest_content_gate.py`, `tests/cli/test_cli_id*.py`,
`tests/id_registry/*` (one family at a time); realpath, case and
`os.replace` on Windows; determinism (messages only: the SBOM diff vs
`main` is empty with `--creation-datetime` pinned); `since` 0.24.1 moves if
a tag is cut between the PRs; skill bodies (251 and 319 bytes headroom:
edit references); the page guard (measure per family).
