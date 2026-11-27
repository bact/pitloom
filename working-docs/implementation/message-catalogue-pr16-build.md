---
Created: 2026-11-23
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Catalogue PR 16 (wheels and embedding): build log

See also: [message-catalogue-pr16-plan.md](message-catalogue-pr16-plan.md)
(counts, sites, probes, contradictions, design, rulings),
[message-catalogue-pr16-plan-steps.md](message-catalogue-pr16-plan-steps.md)
(steps, agents, tests, verification, risks),
[message-catalogue-pr15-build.md](message-catalogue-pr15-build.md) (the
layout this log follows).

Status: built and merged as #515. Section numbers continue the plan's;
sections 6 to 10 were never filled in (the plan and its steps page hold
them).

## 11. Step 1 result

Step 1 (core) built in the worktree `catalogue-wheels`, uncommitted.
Linters clean on every touched file (ruff, flake8, mypy, pyright, pylint
on `src/` and `tests/`, bandit; pyrefly: nothing new in `src/`). New tests
242 pass (`tests/messages/test_wheels_core{,_sboms,_hostile,_worst_case}.py`,
all `platform`). Reference regenerated, `--check` passes. Import order
checked both ways (`pitloom.messages` before and after
`core.wheel_dist_info`). Tier 1: 4019 pass; the 3 failures left are the
integrator's (`test_drift_quotes.py` `_MARKERS`, the ratchet baseline).

### 11.1 Modules

| Module | Holds |
| --- | --- |
| `messages/_fields_wheels.py` | `WHEEL_FIELDS`, `exception_label(exc)`, `IDENTITY_PARTS`, `SHOWN_NAMES = 10` |
| `messages/_wheels.py`, `_wheels_say.py` | topic `wheels`: entries and lines; `WheelRefused`, `refuse_*`, `warn_dist_info`, `warn_metadata_missing`, `say_signature_removed` |
| `messages/_archive_members.py`, `_archive_members_say.py` | `archive-member-*`: `warn_archive_member`, `warn_shared_paths` |
| `messages/_wheel_sboms.py`, `_wheel_sboms_say.py` | topic `wheel-sboms` ("Embedded SBOMs"): entries, summaries, `IdentityMismatch`, `CrossCheckGap`, sayers |
| `messages/_sbom_validation_say.py` | the `spdx3-validate` relay (`targets.py` exports it) |
| `messages/wheels.py`, `wheel_sboms.py` | public modules (`__all__`) |

Variants added to existing families: `library-unusable/hatchling`
(`_hook.py`, via `models.py`), `json-malformed/bom` (`files.py`),
`file-unwritable/mode` (`files.py`), `option-missing/project-dir`
(`options.py`); four `sbom-invalid` lines (`_sbom_input.py`).
`BUILD_FRAME.codes` gains `archive-member-conflict`, `-invalid`, `-unsafe`.

### 11.2 Fields

`archive` (a `str` or a path, by its last component as given, never
resolved; `None` refused), `member`, `later_member`, `install_name`,
`sbom_filename` (each a name: `quoted_name_text`), `members`,
`project_paths` (free: names shown the same way, the first 10 then "and N
more"), `exception_type` (the type name only), `identity_part`
(`name` | `version`), `wheel_value`, `sbom_value` (free; masked, cut to
the excerpt, escaped), `extension`, `skipped` (number), `minimum_version`.
`option` (existing) carries `--allow-signed-wheel` so the family core does
not match `cli/options.py`.

**Compared values** (review rounds 1-2): `wheel_value` and `sbom_value`
are written by `messages/_compared_value.py` (`compared_text`,
`compared_pair`, `ComparedValue`), not `excerpt_text`, which collapsed
white space (`'demo\t'` printed as `'demo'`). Rule:

1. Source: a `str` as stated; any other value as JSON (`sort_keys=True`,
   `ensure_ascii=True`), else its `repr`. Never collapsed.
2. Mask the whole source with `log_masking.masked_text` (URL credentials,
   secret-named parameters with or without a URL; never raises) before any
   cut or slice, so a cut cannot part a secret from its `token=` label.
   `_field_writers.masked` (used by `cut_name` for names) now masks the
   same way, plus temporary directories.
3. Shown form: cut to `EXCERPT_CHARS` (120) with `...`, backslashes
   doubled (so `\t` written by the escaper is never a literal `\` and
   `t`), then `quote_source` (quotes, control characters and white space
   other than a plain space escaped). One-to-one on the cut text.
4. `compared_pair` (inside `say_identity_mismatches` and
   `identity_mismatch_error`; signatures unchanged): when the masked values
   differ and either the two shown forms are equal or either holds a
   non-ASCII character (NFC against NFD, an astral character), both sides
   add `(from character N: <rest>)`: N is the first differing character
   of the MASKED value (a masked credential or an escape shifts it), rest
   is the masked value from there, cut alike, as an ASCII literal
   (`'e\u0301'`). Distinct ASCII shown forms get no note.

Not handled, by design: values equal once masked (two credentials) look
alike; the comparison is of raw text, so a difference PEP 503 or PEP 440
ignores within the first 120 characters can hide a real one past the cut
(no note: the shown forms already differ).

**Name display cap** (ruling after step 1, plan Q18):
`_field_writers.NAME_CHARACTERS = 500`, `NAME_CUT_MARK = "..."`.
`cut_name(text)` masks (URL credentials, temporary directories), then cuts,
then appends the mark; `quoted_name_text(value)` quotes and escapes the
result (the mark inside the quotes). Every name field above uses it;
`sbom_name_conflict` and the relay's coded `FILE=` lines pass their names
through `cut_name` before the `file`/`path` writers. A display cap: it
bounds the report only, the member is read and compared in full. Worst
case (every character `\U0001000c`, ten characters escaped): a name is at
most 5,005 characters, the 10-name list line about 55,200, under
`LONGEST_LINE` (65,536). `tests/messages/test_wheels_core_worst_case.py`
renders every line of every new entry at its longest and asserts
`trusted_message` keeps the code (63 cases; raising the cap to 5,000 fails
29 of them).

### 11.3 Templates per code

`ARCHIVE=%(archive)s ENTRY=%(member)s: ` is shortened to `A E:` below;
`A:` is `ARCHIVE=%(archive)s:`. ERROR lines of a refusal end `; wheel
refused`; the matching dist-info WARNING lines end `; identity unknown`.

- `wheel-unreadable`: `A: could not open as a ZIP archive
  (%(exception_type)s)`; `A E: could not read (%(exception_type)s)`.
- `wheel-invalid`: `A E: NUL in member name`; `A E: duplicate member name`.
- `wheel-unusable`: `A E: .dist-info member under a non-conforming name`.
- `wheel-unusable/signed`: E `A E: signs the RECORD the embed rewrites;
  %(option)s removes it (re-sign the wheel after)`; I `A E: signature
  removed; re-sign the wheel`.
- `dist-info-missing`: E/W `A: no top-level .dist-info directory`; W `A E:
  not in the wheel` (METADATA).
- `dist-info-ambiguous`: E/W `A: several top-level .dist-info directories
  match the file name`, `... the file name is not a wheel name and several
  top-level .dist-info directories exist`, `... several top-level
  .dist-info directories, none the one the file name names`.
- `dist-info-conflict`: W `A: the file name names no top-level .dist-info;
  using %(member)s`.
- `archive-member-unsafe`: `A E: no safe install location; not listed` /
  `; not copied` (build frame); `A E: resolves outside the extraction
  directory; not copied`.
- `archive-member-conflict`: `A E: overwritten by later entry
  %(later_member)s; ...`; `A E: also a directory of other entries; ...`;
  `A: members share a project path (%(project_paths)s); they would share
  one ID registry key`.
- `archive-member-invalid`: `A E: non-conforming name; listed as
  %(install_name)s` / `copied as`; `A E: directory entry carries data;
  ...`.
- `wheel-sbom-missing`: `A: no SBOM under .dist-info/sboms/` [` named
  %(sbom_filename)s`].
- `wheel-sbom-ambiguous`: `A: %(number)s SBOMs under .dist-info/sboms/
  (%(members)s); pass --sbom-filename`.
- `wheel-sbom-wrong-format`: `A E: SBOM does not end in %(extension)s, its
  format's recommended extension`; `A E: SBOM format not recognised;
  extension not checked`; `A E: no validator for the SBOM's format; not
  validated`.
- `wheel-sbom-unusable`: `A: SBOM <name|version> not cross-checked: <why>`,
  eleven static lines, one per gap cause (`GAP_*`).
- `wheel-sbom-conflict`: W/E `A: SBOM %(identity_part)s %(sbom_value)s
  differs from the wheel's METADATA %(wheel_value)s`.
- `wheel-sbom-conflict/held`: W `A E: a Pitloom SBOM, not a build or
  analyzed one of this wheel's name and version; kept`; I `A E: an earlier
  Pitloom SBOM of this wheel; removed`.
- `datetime-not-recordable`: I `A: SBOM entry dated 1980-01-01, the
  earliest a ZIP archive can record; the SBOM's created keeps the true
  date`.
- `sbom-name-conflict`: E `FILE=%(file)s: also the name, ignoring case, of
  sbom-files entry %(path)s; set another sbom-basename in [tool.pitloom] or
  drop the entry`.
- `library-unusable/hatchling`: `Hatchling %(version)s cannot embed an
  SBOM (PEP 770 needs %(minimum_version)s or later); upgrade Hatchling`;
  `Hatchling version unknown (no package metadata found); PEP 770 needs
  %(minimum_version)s or later, reinstall Hatchling`.
- `json-malformed/bom`: W `FILE=%(file)s: SBOM starts with a byte order
  mark, which JSON text must not have; dropped`.
- `file-unwritable/mode`: W `FILE=%(file)s: file mode not restored;
  %(failure)s`.
- `option-missing/project-dir`: I `--project-dir not given; the SBOM is
  built from the wheel alone, not from the project in the current
  directory`.
- `sbom-invalid`: `FILE=%(file)s: not valid SPDX 3 (%(number)s finding(s)
  above)`; `the SBOMs together are not valid SPDX 3 (...)`;
  `FILE=%(file)s: could not be validated; spdx3-validate says why above`;
  `the SBOMs could not be validated; spdx3-validate says why above`.
- Summaries: `verify-wheel: %(number)s wheel(s) OK`, `validate-wheel:
  %(number)s wheel(s) valid`, `... valid, %(skipped)s skipped (no
  validator for their format)`.

### 11.4 Helpers (signatures)

`Archive` is `str | os.PathLike[str]` (a `TYPE_CHECKING` alias).

- `refuse_unopenable(archive, exc)`, `refuse_unreadable_member(archive,
  member, exc)`, `refuse_nul_name(archive, member)`,
  `refuse_duplicate_name(archive, member)`, `refuse_non_conforming(archive,
  member)`, `refuse_signed(archive, member)`, `refuse_dist_info(archive,
  problem)`: each returns a `WheelRefused` (a `CodedValueError`, so a
  `ValueError`).
- `say_signature_removed(log, archive, member)`; `warn_dist_info(log,
  archive, problem, *, chosen=None)` (`chosen` required with
  `DIST_INFO_OTHER`, refused otherwise); `warn_metadata_missing(log,
  archive, member)`. Problem ids: `DIST_INFO_NONE`, `_SEVERAL_MATCH`,
  `_NOT_A_WHEEL_NAME`, `_SEVERAL_NONE_MATCH`, `_OTHER`
  (`DIST_INFO_PROBLEMS`); `resolve_own_dist_info` now returns these.
- `warn_archive_member(log, kind, archive, raw, *, frame=None, later=None,
  listed_as=None)`, kinds `MEMBER_UNSAFE`, `_OVERWRITTEN`, `_SHADOWED`,
  `_NORMALISED`, `_DIRECTORY_DATA`, `_OUTSIDE` (build frame only);
  `warn_shared_paths(log, archive, paths)`.
- `IdentityMismatch(part, wheel_value, sbom_value)`, `CrossCheckGap(cause,
  part=None, value=None)`; `compare_name_version` and
  `check_spdx3_name_version` return `(list[IdentityMismatch],
  list[CrossCheckGap])`.
- `warn_cross_check_gaps(log, archive, gaps)`,
  `say_identity_mismatches(log, archive, mismatches, *, level=WARNING)`,
  `identity_mismatch_error(log, archive, mismatches) -> CodedValueError`
  (all but the last logged at ERROR, the last returned),
  `wheel_sbom_missing(archive, sbom_filename=None)`,
  `wheel_sbom_ambiguous(archive, members)`, `warn_wrong_extension(log,
  archive, member, extension)`, `warn_format_unknown(log, archive,
  member)`, `warn_no_validator(log, archive, member)`, `say_held_sbom(log,
  archive, member, *, removed)`, `say_entry_date_floored(log, archive)`,
  `sbom_name_conflict(file, path)`.
- `relay_validator_text(text, *, names=None) -> int`,
  `say_validation_findings(findings, *, names=None, per_document=True) ->
  int`, `say_validator_failure(exc, *, file=None, names=None)`; relayed
  lines are `ERROR: spdx3-validate: ...`, uncoded, cut to 1,000 characters.

Name display: `cut_name(text) -> str`, `quoted_name_text(value) -> str`
(`messages/_field_writers.py`).

Transitional, for the integrator to remove after step 2:
`wheel_dist_info.refusal()` and `unreadable_member_error()` (old text for
`_embed_wheel.py` 200/210/221), `_sbom_format.format_name_version_mismatch`.

### 11.5 Pages

| Page | Bytes | Lines |
| --- | --- | --- |
| `message-codes-files.md` | 28,433 | 432 |
| `message-codes-targets.md` | 27,547 | 432 |
| `message-codes.md` (index) | 21,433 | 257 |
| `message-codes-models.md` | 20,402 | 337 |
| `message-codes-wheels.md` (new) | 20,086 | 297 |
| `message-codes-wheel-sboms.md` (new) | 14,427 | 238 |

`mkdocs.yml` lists both new pages after "SBOM fragments". `files` and
`targets` are near the 30,000-byte cap: the next entry there splits them.

### 11.6 Changes from the plan, and why

- No `why`, `part` or `problem` field: one static line per cause instead
  (`why` and `part` already mean other things); `identity_part` names the
  side.
- `library-unusable/hatchling` is a variant, not a family.
- New fields `members`, `project_paths`, `later_member`, `install_name`,
  `sbom_filename`; the option name rides on `%(option)s` (a literal
  matched `cli/options.py` as a family core).
- The validator relay lives in `messages/` (a mechanism), so
  `scripts/message_inventory/_relay.py` is unchanged.
- Exact repeat findings are printed once (the plan said keep; the brief
  said no longer twice). Relayed lines stay `ERROR`.
- The validator-failure line carries no `%(failure)s`: the text named a
  temporary path.
- A4 shows 10 names, not 5 (`SHOWN_NAMES`, shared by both list fields).
- E8 reuses `invalid_value(Parameter(...), "file-name")`; no new line.
- Advice and `did` texts reworded to the drift rules ("Tell the user ...
  Do not ..."; no "As" outside `ERROR` entries).

### 11.7 Changes outside the fence (for steps 2-3)

Done in the follow-up round (no longer failing): `test_drift_sources.py`
(three shrink-only sets, `_UNSAID_UNTIL_CONVERTED`,
`_FAMILY_TEXT_UNTIL_CONVERTED`, `_BARE_CALLS_UNTIL_CONVERTED`, each equal to
what the scan finds: the conversion step empties and drops them),
`test_frames_build.py` (`_TABLE` codes; `_member_said_at` reads a frame
handed to a lister or `warn_archive_member`), `test_file_unreadable.py`
(`_OTHER_CAUSES` empty), `test_messages_quote_paths.py` (`_QUOTING_CALLS`).

Tests that failed before that round (kept for the record):

- `tests/test_message_ratchet.py`: baseline (`--write-baseline` by the
  integrator); `_embed_wheel.py` 200/210/221 stay uncoded until step 2.
- `tests/messages/test_drift_sources.py`: `FILE_UNWRITABLE_MODE`,
  `JSON_MALFORMED_BOM`, `LIBRARY_UNUSABLE_HATCHLING` unused; family texts
  at `_embed_wheel.py:463`, `_sdist_scan.py:184`, `verify_wheel.py`.
- `tests/messages/test_drift_quotes.py`: `_MARKERS` entries for every new
  family.
- `tests/messages/test_frames_build.py`: `_TABLE[BUILD_FRAME]` adds the
  three `archive-member-*` codes; `_said_at` must see a frame passed to
  `zip_file_members`/`file_members`/`archive_members` and
  `warn_archive_member(frame=BUILD_FRAME)`.
- `tests/messages/test_file_unreadable.py`: `_OTHER_CAUSES` drops
  `core/wheel_dist_info.py`.
- `tests/test_messages_quote_paths.py`: `_QUOTING_CALLS` adds every
  `refuse_*`, `wheel_sbom_missing`, `wheel_sbom_ambiguous`,
  `identity_mismatch_error`, `sbom_name_conflict`.
- pyrefly in tests pinning the old API: `tests/assemble/test_sbom_format.py`
  (`.error`, mismatch strings), `test_embed_core.py`,
  `test_embed_internals.py`, `test_validate_wheel_cli.py`,
  `test_wheel_sbom_location_identity.py`, `tests/core/test_wheel_dist_info.py`
  (`PROBLEM_*`; `exception_label` now from `pitloom.messages.wheels`),
  `tests/extract/test_wheel_identity.py`.

Call sites for step 2: `_embed_wheel.py` 200 `refuse_unreadable_member`,
210 `refuse_non_conforming`, 221 `refuse_signed`, 463 `emit(...,
FILE_UNWRITABLE_MODE, file=, failure=)`; `embed.py`, `verify_wheel.py`:
`warn_cross_check_gaps` plus `say_identity_mismatches` or
`identity_mismatch_error`; `_embed_stale.py`: `say_held_sbom`; batch:
`say_signature_removed`, `say_held_sbom(removed=True)`,
`say_entry_date_floored`; `extract/wheel.py`: `warn_dist_info(...,
chosen=choice.prefix)`; `utils.py`: `wheel_sbom_missing`,
`say_validator_failure`, `say_validation_findings`; `validate_wheel.py`,
`verify_wheel.py`: `warn_no_validator`, `warn_format_unknown`,
`warn_wrong_extension`, summaries via `say_summary`; `embed_wheel.py`:
`OPTION_MISSING_PROJECT_DIR`; `_embed_generate.py`,
`id_registry/_sbom_read.py`: `JSON_MALFORMED_BOM`; `plugins/hatch.py`:
`LIBRARY_UNUSABLE_HATCHLING`, `sbom_name_conflict`; `_sdist_scan.py`:
`warn_shared_paths`; `_models_wheel_build_and_read.py`:
`warn_archive_member(MEMBER_OUTSIDE, frame=BUILD_FRAME)`.

### 11.8 Doubts and their answers (coordinator, 2026-11-23)

1. Hatchling H1/H2 `RuntimeError` -> `CodedValueError` (a `ValueError`):
   accepted; the conversion agent greps callers that catch `RuntimeError`.
2. `identity_mismatch_error` (all but the last logged at `ERROR`, the last
   returned): accepted.
3. Relay `names` maps take raw paths (never `loggable()` text);
   `embed-wheel --validate` uses `per_document=False` if that keeps
   `SBOM_NOT_VALID_LINE`: the conversion agent decides and reports.
4. `_embed_stale.say_held_sbom`: the archive is the wheel's file name.
   Shape chosen: `archive_text` names any `str` or path by its last
   component, so the caller passes `zf.filename` as is; `None` (an
   in-memory `ZipFile`) is refused with a plain `ValueError`, no code. The
   embed never opens one; if a site can, it passes the wheel path its
   caller holds instead. No `None` parameter: a line without its subject
   is not one of the entry's lines.
5. E7: `archive` is the file name as given on the command line, last
   component only, never the resolved path (`archive_text` does it).
6. `extract/wheel.py` D2 (`chosen=choice.prefix`): fine.

Other doubts:

- A 64 KiB member name: settled by the name display cap (11.2).
- `core/wheel_dist_info.py` is 527 lines (533 at HEAD), past the soft
  limit; a split belongs to a later PR.
- The relay `names` map takes raw paths; `utils.py` must not pass
  `loggable()` text (double escape).
