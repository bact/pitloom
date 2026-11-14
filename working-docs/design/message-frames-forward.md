---
Created: 2026-11-14
Last-Modified: 2026-11-14
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message frames forward: prefixes for catalogue PRs 5 to 18

See also: [message-frames.md](../implementation/message-frames.md) (what PR 4
built), [message-catalogue-migration-plan.md](message-catalogue-migration-plan.md)
(order, counts, rulings R1 to R7),
[message-catalogue-and-skills.md](message-catalogue-and-skills.md)
(decisions A to M).

Status: design, 2026-11-14, written during PR 3 from three read-only surveys
of `main` plus the PR 3 tree. Tags: (V) verified in code, (I) inferred.
Nothing here is built. It settles how a prefix before a catalogued line is
spelt and matched, so each later PR applies a rule instead of debating one.
Codes themselves stay each PR's plan (decision L makes them promises).

## Summary

Today a frame applies to `ERROR:` lines only (the formatter reads a
`ContextVar`, `logging_config.py` around line 110) (V), and `_text_re`
(`messages/_lines.py`) accepts at most one frame of the line's level before
**any** entry's line (V). Only `RELAY_FRAME` covers `WARNING`. Adding a
`WARNING` or `INFO` frame to `FRAMES` as it stands would make every entry's
line trusted after it: `WARNING: Git source: <an over-cap line> [over-cap]`
would pass. So the later PRs need one rule for which prefix is a template
literal, which is a subject and which is a frame, and frames that name what
they may precede.

## The rule set: a prefix by its cause

Apply the first rule that fits.

1. **A subject exists: write it as the subject**
   (`LEVEL: SUBJECT=value: CONDITION`, decision H). The line's thing (a
   file, archive, licence, URL) is a field, not a prefix. Where a family
   already spells its subject one way, keep that spelling; where one subject
   kind has several spellings, unify on the field.
2. **The line is only ever said with one fixed prefix: a template literal,
   from one constant per family.** The prefix is part of the line's
   template, so the reference, the skills and `trusted_message` see it with
   no new mechanism. The constant lives in the family's
   `pitloom.messages.<topic>` module; no call site types the text.
3. **The same catalogued line is said with and without a prefix, or under
   several prefixes, or a caller passes the prefix at run time
   (`log_prefix`): an explicit, family-restricted `Frame` on `emit`.** This
   is the case of `temp-left-behind` (six spellings today), the signal line
   of `build_signals.py`, `option-no-effect` (two templates today) and the
   archive member lines (`Build: ` or none).
4. **ERROR lines keep the command frames** (`COMMAND_FRAME`, `TOP_FRAME`,
   `HOOK_FRAME`) from the `ContextVar`, unchanged. A rule-3 frame is never
   put on an `ERROR` line or on an exception's text, so one line never
   carries two frames.

| PRs | Family area | Mechanism | Reason |
| - | - | - | - |
| 5 to 7 | ID registry | literal `ID registry: ` (rule 2); the file as subject | said only with it; `references/id-registry.md` quotes it 29 times (V) |
| 8, 9 | config | subject: the setting as the user wrote it (rule 1); `Options: ` line via `OPTIONS_FRAME` | no `Config: ` prefix exists (V) |
| 10, 11 | lock files | subject `'<p>': ` / `'<p>':N: ` kept (rule 1) | one spelling today; editor-clickable |
| 12 | project metadata | subject `FILE=` (rule 1); `Build: ` dropped from discovery fallbacks | ~29 sites, five subject spellings (V) |
| 13 | Git | `GIT_FRAME` (rule 3) | `temp_dir(log_prefix=)` and lines said also without it |
| 14 | Hub, build, temp dirs, signals, options | `BUILD_FRAME`, `HF_FRAME`, `PYPI_FRAME`, `SCAN_FRAME`, `OPTIONS_FRAME`, `HOOK_STEP_FRAME` (rule 3) | runtime `log_prefix` in `core/temp_dirs.py` and `GuardedActivity` (V) |
| 15 | fragments | literal `Merge: ` (rule 2) | a subsystem name; said only with it |
| 16 | wheels | subjects `ARCHIVE=`, `ENTRY=` (rule 1); `BUILD_FRAME` from the build route | `archive_member_names.py` takes a runtime prefix (V) |
| 17 | authors, datasets, SDK | subjects (authors); literal `dataset metadata: ` (rule 2); SDK prefix: ruling 2 | |
| 18 | licences | subjects (`LICENSE=`, `FIELD=`, `CLASSIFIERS=`); `licenseid: ` relay uncoded | foreign text, LicenseID's own grammar |

## The Frame interface (sketch)

Lands with the first PR that needs it (PR 13); PR 14 adds the rest.

```python
@dataclass(frozen=True, kw_only=True)
class Frame:
    levels: frozenset[str]
    template: str
    surface: str
    #: The families whose lines it may precede; None: any (ERROR-only frames).
    families: frozenset[str] | None = None
```

- `__post_init__`: a frame whose `levels` hold `WARNING` or `INFO` must name
  `families`; only an `ERROR`-only frame may leave it `None`. So the three
  command frames stay as they are, and `RELAY_FRAME` gains the families of
  the `models` and `model-fields` topics (derived from `_topics.py`, not
  listed twice).
- A code `family/variant` matches its family; restriction is by family so a
  new variant needs no frame edit.
- `_text_re(message, level)` takes a frame only when
  `level in f.levels and (f.families is None or message.family in
  f.families)`. Still at most one frame. `relay_extra` and `says` follow,
  since they call `_text_re`.
- `emit(log, M, level, *, frame=None, frame_values=None, ...)`: the record's
  text is `frame.render(frame_values)` then the line. A frame that does not
  allow `M`'s family or `level` raises the same `ValueError` as a line that
  does not fit (a programming error, caught by the call's own test). No
  `frame=` on `CodedValueError` and its siblings (rule 4).
- `temp_dir(prefix, *, frame)`, `remove_temp_dir(path, frame)`,
  `rmtree_quietly`, `warn_if_left_behind` and
  `GuardedActivity(name, frame)` replace `log_prefix: str`. The debug lines
  in them render `frame.render({})` as plain text (`DEBUG` is out of scope).
- `archive_member_names.py` (lines 107, 181, 215) takes `frame: Frame |
  None`.

Test-visible effects (`tests/messages/test_frames.py`):

- Per frame, a line of an allowed family is trusted after it, and a line of
  a family outside `families` (for example `over-cap` after `Git source: `)
  is not; parametrised over `FRAMES`, short ids.
- `FRAMES` grows from four to about ten; `test_the_table_is_the_four_frames`
  becomes a table test naming each frame's surface.
- A drift test: every `emit(..., frame=X)` call site's message family is in
  `X.families` (AST walk, like the hook test).
- The reference shows each family's frames next to its lines (generator).

## Per-PR notes

Only what each PR must know; the PR's own Opus plan re-lists sites by AST.

### PRs 5 to 7: ID registry

- `REGISTRY_PREFIX = "ID registry: "` in `pitloom.messages.id_registry`;
  every line of the family's templates starts with it. About 30 INFO, 11
  WARNING, 5 ERROR sites use the literal today (V, survey count).
- Stacked prefixes are a bug to fix, not to catalogue:
  `ID registry file 'p': ID registry: key ... cannot be encoded` (V). Rule:
  a helper that builds part of a line (`unencodable_message`,
  `failed_to_save_message`) never adds the family prefix; the line's template
  adds it once. `registry_file_error` (`id_registry/_types.py:180`, 26
  callers) becomes the subject form `ID registry: <file subject>:
  CONDITION`; the PR picks the field (`path` quoted, as the 26 lines write it
  now, is the least change).
- `failed_to_save_message` wraps `{exc}`: the outer line states its own
  condition (`registry-unwritable` or the plan's name) with the inner text as
  `(detail)`. The inner code is not printed (one line, one code), which is
  right only because the outer condition differs (see "Wrappers" below).
- One helper, two levels: `unencodable_message` is ERROR at PR 5's sites and
  WARNING at `_harvest.py:447`; `failed_to_save_message` WARNING at
  `_persist.py:206`, ERROR at `cli/id.py:221`. One entry with an ERROR and a
  WARNING line each (decision E).
- `ambiguous_keys_message` is INFO or DEBUG at run time; a `Line` has one
  level. The INFO case goes through `emit`; the DEBUG case stays a plain
  `log.debug` (developer-only, out of scope). Same rule for every dynamic
  INFO/DEBUG site (PR 18's `_license_resolve:221`).
- `warn_claim_collision` is called from library code: `emit` is fine there.
- The stray `loom: model %r ...` WARNINGs (`_loom_model.py:84,87`) are PR 17's
  (ruling 2), not the registry's.
- The two `PATH '<p>'` ERRORs (`cli/id.py`, `_types.py:364`) and
  `_types.py:329` are PR 5's (forward requirement from PR 3).
- Applied in PR 5 (#485): `registry_file_error` became the subject form
  `ID registry: FILE=<file>: CONDITION` (the file as given, URL masked);
  `unencodable_message` became `text-malformed/registry` (an `ERROR` and
  two `WARNING` lines). Left: `failed_to_save_message` (PR 7), so the
  `registry-unusable` code is not yet printed on the CLI.

### PRs 8 and 9: configuration

- No `Config: ` prefix exists (V). The subject is the setting, today a TOML
  table written literally. `_config_parse.py` hardcodes `[tool.pitloom...]`
  even for `setup.cfg` (V): the subject names the file's own spelling
  (ruling 3).
- The field name `key` is taken (`CAP_KEYS`); the helper is
  `say_config_invalid(setting, value, expected)` or similar, never `key`.
  `CONFIG_TABLES` (closed) holds two tables; PR 8 extends it.
- `config_cascade.py:202` re-raises a plain `ValueError` and drops the inner
  `pitloom_code` (V): fix under "Wrappers" below.
- `config_cascade.py:205` writes `Options: ` (`INERT_LOG_PREFIX`) by hand:
  it becomes an `OPTIONS_FRAME` line once PR 14 lands it; if PR 9 lands
  first, it keeps the literal and PR 14 converts it.
- `_warn_unknown` prints its source raw (V): through a field.
- Not config (V): `iri.py`'s 4 sites (a `cli/id.py` option-invalid, the
  registry key encoding, an adoption WARNING) and `_models_wheel_types.py`'s
  3 (already `option-invalid` from PR 3, or caller misuse for PR 17).

### PRs 10 and 11: lock files

- Code lives in `extract/lock/` (V).
- Subject stays the bare quoted path `'<p>': ` or `'<p>':N: ` (ruling 4).
- Entry lines `Skipping <format> entry %r: ...` with a runtime `lock_file`:
  the format is a field, not text built at run time.
- Runtime lead-ins become fixed lines: `warn_missing_name(context, ...)`
  (free-text `context` from five callers) becomes one line per caller kind
  or a closed field; `_uv_graph.py:108`'s optional path prefix becomes two
  lines; `_lock_io.py:106`'s runtime verb (`Cannot read` or `Failed to
  parse`) is two conditions: `file-unreadable` reuse and the lock's
  malformed line.

### PR 12: project metadata

- About 29 sites with their own subjects (`setup.py: `, `pyproject.toml: `,
  `poetry-core: `, `PDM `, `Flit `) (V): unify on `FILE=`; no frame.
- The six file-discovery-fallback WARNINGs in
  `core/_models_wheel_dispatch.py` (lines 100, 112, 122, 129, 255, 265) start
  with `Build: ` though no build runs (V). PR 12 owns them and drops
  `Build: ` (a decided wording change, listed in the PR's stderr sweep).
  `_models_wheel_types.py:86` has no prefix.
- The hook can reach the Hatchling `file discovery failed` line
  (`plugins/hatch.py:177`): test the hook surface too.
- PR 12 goes before 14, so `BUILD_FRAME.families` never includes discovery.

### PR 13: Git

- `GIT_FRAME` (`Git source: `), WARNING and INFO, families of the Git lines
  (and `temp-left-behind` once PR 14 catalogues it). About 14 sites (V):
  10 INFO (`_git_redirect.py:59,68`; `git.py:105,324,405,507,524,528`;
  `_git_run.py:190`; `messages/_config_unsafe.py:27`), 3 WARNING, 0 ERROR.
- `_config_unsafe.py:27` is catalogued with the prefix inside its template:
  PR 13 moves it to the frame (printed text unchanged; the reference's shape
  changes).
- The relay `git.py:225` prints `WARNING: Git source: <ERROR text>` with no
  code; the exception then reaches the CLI, which prints the ERROR again (V).
  It can never pass `trusted_message`. Same at `pypi.py:457,466` without a
  prefix. Drop the duplicate (ruling 5); where a route swallows the error
  instead, code it as the entry's WARNING line (`RemoteSourceError.said`).
- Already coded through `pitloom_code`: `git.timeout`, `git.too-large`,
  `git.output-too-large`, `git.offline`, network `git.clone-failed` (V). The
  plan's `timeout` and `network-failed` are the shipped
  `download-timeout` and `download-network-failed`. Uncoded: `git.not-found`,
  `git.url-invalid`, `git.ref-not-found`, `git.too-many-redirects`,
  `git.no-project`, the other `git.clone-failed`; missing `git` is
  `_git_run.py:181`.
- Threads do not log (V): no `ContextVar` propagation needed. Do not open a
  `ContextVar` around `fetch_git_checkout`: it would leak past its `yield`.

### PR 14: Hub, build, temp directories, signals

- Frames: `BUILD_FRAME` (`Build: `), `HF_FRAME` (`Hugging Face source: `),
  `PYPI_FRAME` (`PyPI source: `), `SCAN_FRAME` (`AI model scan: `, from
  `GuardedActivity`, `build_signals.py:85`), `OPTIONS_FRAME` (`Options: `),
  `HOOK_STEP_FRAME` (the hook's WARNING/INFO prefix, ruling 1).
- `Build: ` lines are only WARNING/INFO (V): `_models_wheel_dispatch.py:198`,
  `build_and_read.py:110,178,189,200`, `temp-left-behind`,
  `_models_wheel_build_kill.py:125,136`, `build_signals.py:102` (signal
  handler, main thread), the `option-no-effect` build line.
- No `ContextVar` for `Build: `: `option-no-effect` and the discovery
  fallbacks print with no build running (V).
- `option-no-effect` collapses to one template, same code, same printed
  text; its helpers take `frame: Frame` (`OPTIONS_FRAME` or `BUILD_FRAME`)
  instead of `build: bool`.
- `build_and_read.py:200` relays exceptions (an interpreter-missing
  `RuntimeError`, `BuildSubprocessError` carrying the build's last output):
  the build's own output is third-party text in `(detail)`, `loggable`, one
  line; the line's code is the build condition's, never the inner one.
- Hub: no `Hub: ` prefix (V); HF lines use `URL=`/`FILE=` subjects, and
  `Hugging Face source: ` appears only on `temp-left-behind`.
- Evidence pairing PR-C1 is PR 14's only (the HF file left out,
  `_http_errors.py:111`); see "Cross-PR interfaces".
- New topic `build` (build, temp directories, signals); Hub lines go to
  `network` (12.1 KB of 30 KB, V).

### PR 15: fragments

- `MERGE_PREFIX = "Merge: "`; nine templates use it with no shared constant
  (`_fragments_evidence:58`, `_generated:52`, `_hashes:63`, `_ids:57`,
  `_model_names:64`, `_props:106,114,122,196`; 7 in scope: 4 WARNING,
  3 INFO; 2 DEBUG) (V).
- Unify the spellings: lowercase `merge: ` (`_fragments_envelope.py:115`,
  WARNING; `cli/commands/merge.py:50`, an INFO count, R1) and the shipped
  `license-relationship-invalid` ("Fragment merge left ..."). The shipped
  line's text changes only with decision L's rules (a wording change, same
  code).
- `merge_fragments` runs under `loom merge`, `loom generate`, the hook and
  `generate_merged_sbom`: `Merge` names the subsystem, never `loom merge: `.
- `_fragment_read_failure_message` and `_same_document_message` copy the
  optional/required pair of `warn_fragment_not_found` (PR 3). Their private
  names imported by `cli/commands/fragment.py:25-26` count one text as three
  sites: make them public in the messages module.
- 22 sites in scope, not 31.

### PR 16: wheels

- Subjects `ARCHIVE=`, `ENTRY=`; the field `archive` is new (`entry`
  exists). Suffix ` -- wheel refused` is the effect, kept in the template.
- `archive_member_names.py:34` (`_MSG = "%sARCHIVE=%s ENTRY=%s: "`) with
  runtime `log_prefix` (the build passes `Build: `, `_sdist_scan` none): the
  lines take `frame=BUILD_FRAME` or none. Line 162 hides four templates
  behind `args[0]`: four lines, not one passthrough.
- `verify-wheel: `, `validate-wheel: `, `embed-wheel: ` in INFO lines are
  summaries (R1), not frames; no rename.
- Mismatch logic is duplicated: `embed.py:138,145,147` (library
  `ValueError`) and `verify_wheel.py:96,103,105`: one helper.
  `verify_wheel.py:103` is a `log.error` the formatter frames (V); it
  becomes `emit`.
- `action.yml:544,548` strips `ERROR: ` and `WARNING: ` and keeps frame and
  code inside `::error::`: unchanged.
- The `_embed_generate.py` byte order mark WARNING is PR 16's (from PR 3).

### PR 17: authors, datasets, SDK, escaped text

- Authors already use `%s=%s:` subjects: no frame, no prefix.
- `DATASET_PREFIX = "dataset metadata: "` from the four constants in
  `extract/dataset/values.py:58-76`.
- The SDK's `loom: ` on about 13 constants (`_loom_dataset*.py`,
  `_loom_model.py:84`, `_loom_caller.py:199-220`, `_loom_active_run.py:372`)
  is the text of `TOP_FRAME`. As `TOP_FRAME` is ERROR-only it is never
  matched as a frame, but a reader takes it for one (ruling 2).
- Escaped text: 3 sites in scope (`_embed_generate:96`,
  `_loom_dataset_meta:283`, `_ai_package:398`), not 5.
- `core/provenance.py:88,92` are detail of PR 3 (`option-invalid`) and PR 8
  (`config-invalid`), not PR 17's. `provenance.py:414` becomes
  `InternalError` (R7).

### PR 18: licences

- Subjects `LICENSE=`, `FIELD= LICENSE=`, `CLASSIFIERS=`; `pyproject.py:230`
  has none and gains one. 8 sites.
- `_DB_PREFIX = "licenseid database"` (`_license_text_match.py:62`) is a
  subject phrase, used by line 97 (INFO, not found) and 107 (WARNING
  embedding LicenseID's `one_line(exc)` as detail). Two lines, counted once
  (the plan listed them twice).
- `_license_resolve:221` decides INFO or DEBUG at run time: R1 and the
  dynamic-level rule above.
- `_classify:94` duplicates `warn_lone_surrogates` (`text-malformed`): call
  the helper.
- The relay `licenseid: ` (`_licenseid_relay.py:64`) prefixes a
  `LicenseIdWarning`'s text, in LicenseID's own grammar (subject, condition,
  detail, action), with no code. Decision: it stays uncoded and out of
  `FRAMES` (it is not Pitloom's prefix to promise), documented in
  `docs/messages.md` as a relayed foreign line. Its ratchet exclusion moves
  from the bare `%s` template (`PASSTHROUGH_PAT`) to a relay shape in
  `scripts/message_inventory/_relay.py`: the warning's own text, in the
  relay function's body, prefixed by the module constant (ruling 6).
- Codes are spelt `license-*` (identifiers are American, CLAUDE.md; the
  shipped `license-relationship-invalid` sets the pattern); the plan's
  `licence-*` names are working names.
- Quoted by: `sbom-generate/SKILL.md:82-93` (preflight),
  `sbom-enrich/SKILL.md:63,212`, `sbom-validate/SKILL.md:85`,
  `known-limitations.md:329-368`, `examples.md:97`, `docs/github-action.md:40`,
  `docs/hatchling-build-hook.md:53`,
  `docs/metadata-provenance-licences.md:160-166`.
- T14: only its task 4 (the Reason code) waits for PR 18; tasks 1 and 2 may
  go first.

## Cross-PR interfaces

- **Wrappers keep the inner code.** A wrapper that only adds where (a file,
  a table) re-raises the inner exception unchanged, or puts the where into
  the inner line's subject; it never raises a plain exception around a coded
  one (`config_cascade.py:202` today). A wrapper that states a new condition
  raises its own coded exception `from` the inner one; the inner text is
  `(detail)`. A ratchet rule flags `raise ValueError(...) from e` where `e`
  can carry a `pitloom_code` (I: needs an AST shape; PR 8 builds it).
- **Reason equals the message's code** (the rule `core/evidence.py` states
  and the four shipped reasons follow: `over-cap`, `lfs-pointer`,
  `file-unreadable`, `dir-unlistable`). The placeholders `timeout` and
  `network-failed` in `REASON_CODES` become `download-timeout` and
  `download-network-failed`; no SBOM writes them yet (V: no writer), so
  nothing printed changes, and `PENDING` in
  `tests/messages/test_drift_sources.py` empties. Rejected: Reason equals the
  message's condition, which would rename the four shipped reasons
  (`file-unreadable` would become `unreadable`). May land with PR 14 or
  alone.
- **`since`**: a new entry takes the next release after the last tag at the
  time it merges. PR 3 uses 0.24.1 (maintainer, 2026-11-13); later PRs check
  `git tag` before choosing.
- **Topic pages** (`messages/_topics.py`, page guard 30 KB): new topics
  `id-registry` (5 to 7), `config` (8, 9), `lock-files` (10, 11),
  `metadata` (12, and PR 17's author and dataset lines unless the page
  nears the guard), `build` (14), `fragments` (15), `wheels` (16). Git and
  Hub go to `network` (12.1 KB). `targets` (19.1 KB) and `files` (17.5 KB)
  take no new family without measuring.
- **R1 first.** R1 (INFO decision and summary lines) must be ruled before
  PRs 6, 7, 13, 14, 15, 16, 17 and 18 (PR 4, which the plan also listed, is
  built).
- **Ordering.** PRs 5 to 11 branch from `main` after PR 3 merges (PR 3
  touches 83 source files). PR 12 before 14 (it removes `Build: ` from
  discovery). PR 13 lands `Frame.families` and `emit(frame=)`; PR 14 lands
  `temp_dir(frame=)`, `GuardedActivity(frame)` and the other frames, and
  changes the Git `temp_dir` call. PR 16 shares `archive_member_names.py`
  with 14: whichever lands second rebases; PR 14 changes only the parameter
  type there. PR 18 last, then T14 task 4.

## Rulings needed from the user

Recommendation in brackets. **Decided 2026-11-14** (the user took the
recommendation): 1, 2, 5 and 7. Open: 3, 4 and 6.

1. **Decided: rename.** The hook's WARNING/INFO prefix `Pitloom: ` (`plugins/hatch.py:58`)
   differs from its ERROR frame `Pitloom build hook: `. [Spell both
   `Pitloom build hook: `: one name per surface; `HOOK_STEP_FRAME` has the
   same text as `HOOK_FRAME`, a separate table row because it is
   family-restricted.]
2. **Decided: `loom SDK: `.** The SDK's `loom: ` prefix on WARNING lines reads as `TOP_FRAME`. [Replace
   it by a literal `loom SDK: ` family constant (rule 2); a decided wording
   change in PR 17.]
3. Config subject spelling. [The setting as written in the file read
   (`[tool.pitloom.scan]` in `pyproject.toml`, the file's own section in
   `setup.cfg`); field name chosen by PR 8, not `key`.]
4. Lock-file subject. [Keep `'<p>': ` and `'<p>':N: `; no `FILE=` rewrite
   of about 40 lines quoted in `lockfile-discovery.md`.]
5. **Decided: drop** (PR 13 still confirms the exception always reaches the
   ERROR line before the relay goes). Drop the duplicate relays `git.py:225`, `pypi.py:457,466` (a printed
   line disappears). [Drop, after the PR 13 plan confirms the exception
   always reaches the ERROR line.]
6. `licenseid: ` relay: uncoded, outside `FRAMES`, excluded by relay shape.
   [Yes. The alternative, one Pitloom code for any LicenseID diagnostic,
   would promise a condition Pitloom does not own.]
7. **Decided: code decisions by the condition they answer; pure counts are
   a "summary" kind left out of the ratchet by an explicit scope rule, never
   by raising a count.** R1 itself (migration plan). [As recommended there.]
   Gates PRs 6, 7 and 13 to 18; PR 4b (command summaries) follows it.

## Not decided

- Whether `RELAY_FRAME` may stand before an `ERROR` record logged under a
  command frame (I: `scanner.py:258-268` relays `record.levelno`; an ERROR
  record would print `loom model: FORMAT=...: ...`, two frames, not
  trusted). PR 14's plan checks whether a reader ever logs at ERROR; if so,
  allow the ordered pair command frame then relay frame, or relay at
  WARNING.
- How `--report` carries a frame (a separate field, likely).
- The codes of each family (each PR's plan).
- Whether a frame's text appears in the generated reference per line or once
  per topic.

## Tried and rejected

- **A `ContextVar` for non-ERROR frames.** `Build: ` lines print with no
  build running (`option-no-effect`, discovery fallbacks); a `ContextVar`
  around a generator (`fetch_git_checkout`) leaks past its `yield`; a worker
  thread does not inherit it.
- **One unrestricted `SOURCE` or `Git source: ` frame in `FRAMES`.** Every
  catalogued line would be trusted after it (`Git source: <over-cap line>`).
- **A bare `%s` template exemption** for relays (`licenseid: `, the CLI
  handler): it exempts any new `log.warning("%s", text)`; message-frames.md
  rejected the same shape for `{e}`.
- **A literal prefix in the template for Build and Git.** `temp-left-behind`
  alone would need six templates of one condition.
- **Reason equals the message's condition** (see "Cross-PR interfaces").
