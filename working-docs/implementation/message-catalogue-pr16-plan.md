---
Created: 2026-11-23
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Catalogue PR 16 (wheels and embedding): plan

See also: [message-catalogue-pr16-plan-steps.md](message-catalogue-pr16-plan-steps.md)
(steps, agents, tests, verification, risks),
[message-catalogue-pr16-build.md](message-catalogue-pr16-build.md)
(the build log), [message-catalogue-migration-plan.md](../design/message-catalogue-migration-plan.md)
(row 16, R1), [message-frames-forward.md](message-frames-forward.md)
("PR 16: wheels"), [message-catalogue-pr15-plan.md](message-catalogue-pr15-plan.md)
(the shape this plan follows; it handed over `utils.py:370,385`),
[message-catalogue-pr14-rulings.md](message-catalogue-pr14-rulings.md) (Q17:
`hatch.py` lines), [known-bugs/surfaces-hook-and-wheel.md](../design/known-bugs/surfaces-hook-and-wheel.md).

Status (2026-11-23): planned; built and merged as #515. Read-only plan by Opus
against `main` at 01d1a726 (#513 merged; ratchet 85); every line number is that
tree's. Branch `catalogue-wheels`. Nothing is decided: each Qn in section 5 is
the planner's recommendation.

Tags: (V) verified by reading or running on 01d1a726; (I) inferred.

## 0. Counts and ratchet

`--check` passes at **85** (V). Sites from `python -m scripts.message_inventory
--jsonl`, `_scope.in_scope` and not `coded` (V).

| Module | Uncoded (line) | PR 16 | Elsewhere |
| - | - | - | - |
| `core/wheel_dist_info.py` | 217, 258, 270, 521 | -4 | |
| `_wheel_sbom_location.py` | 70, 72, 208 | -3 | |
| `_embed_wheel.py` | 152, 200, 210, 221, 430, 463 | -5 | 430: PR 17 (`call-invalid`) |
| `core/archive_member_names.py` | 166 (four templates), 200 | -2 | |
| `core/_models_wheel_build_and_read.py` | 122 | -1 | |
| `extract/wheel.py`, `extract/project/_sdist_scan.py` | 264; 184 | -2 | |
| `embed.py` | 139, 146, 148 | -3 | |
| `_embed_stale.py`, `_embed_generate.py` | 99; 108 | -2 | |
| `_embed_overlay.py` | 117 | 0 | PR 17 (Q16) |
| `cli/commands/_embed_wheel_batch.py` | 71, 78, 84 | -3 | |
| `cli/commands/embed_wheel.py` | 168 | -1 | |
| `cli/commands/verify_wheel.py` | 47, 54, 96, 103, 105, 165 | -6 | |
| `cli/commands/validate_wheel.py` | 49, 118, 125 | -3 | |
| `cli/commands/utils.py` | 196, 259, 370, 385 | -3 | 196: final sweep (Q16) |
| `plugins/hatch.py` | 86, 97, 360 | -3 | |

**41 sites in PR 16; landing 85 to 44** (43 if Q16's inventory rule takes
`utils.py:196`). Row 16's "-28" predates `hatch.py` (PR 14 Q17),
`utils.py:370,385` (PR 15), `_sdist_scan.py:184` (PR 12 plan) and
`utils.py:259`, `extract/wheel.py:264`.

Missed by the inventory (V): the duplicate-name refusal text lives in a
lambda, `wheel_dist_info.py:224` (`on_duplicate=lambda raw: refusal(...,
"duplicate member name")`), and is counted nowhere (`archive_member_names.py:146`
is `DETAIL_EXC` `on_duplicate`). PR 16 codes it as a ninth refusal line.

Out of count already, unchanged: `wheel_dist_info.py:145,165,252,531`,
`utils.py:145,175,230,297,300`, `embed_wheel.py:144,191` (coded:
`target-wrong-format`, `input-not-found`, `over-cap`, `library-*`,
`sbom-invalid`, `option-conflict`); `_embed_build_sbom.py:109-322`
(`RuntimeError` invariants).

## 1. Sites

Surfaces: CLI `wheel`, `generate` (wheel path or PyPI wheel URL), `wheel
--embed`, `embed-wheel` (and its batch), `verify-wheel`, `validate-wheel`,
`fragment validate` (validator relay only); the model scan of a wheel
(`scanner_wheel.py:379`, refusals only); the library (`read_wheel`,
`generate_wheel_sbom`, `embed_wheel_sbom`, `embed_sbom_in_wheel`,
`find_embedded_sbom`); the hook (H rows only); the Action (CLI). `loom.run`
reads no wheel (V).

Level: E error, W warning, I info. Who: U user, C caller, - none.

| # | file:line | Lvl | Text now (abridged) | Who | Proposed code |
| - | - | - | - | - | - |
| R1 | wheel_dist_info:217 | E | `ARCHIVE='a' ENTRY='m': NUL in member name -- wheel refused` | U | `wheel-invalid` |
| R2 | wheel_dist_info:224 (lambda) | E | `... ENTRY='m': duplicate member name -- wheel refused` | U | `wheel-invalid` |
| R3 | wheel_dist_info:258 | E | `ARCHIVE='a': could not open (zipfile.BadZipFile) -- wheel refused` | U | `wheel-unreadable` |
| R4 | wheel_dist_info:270 | E | `... ENTRY='m': could not read (<type>) -- wheel refused` | U | `wheel-unreadable` |
| R5 | _embed_wheel:200 | E | R4's line, `RECORD` not UTF-8 (`UnicodeDecodeError`) | U | `wheel-unreadable` |
| R6 | _embed_wheel:210 | E | `... ENTRY='./d/WHEEL': non-conforming name -- wheel refused` (embed only) | U | `wheel-unusable` |
| R7 | _embed_wheel:221 | E | `... ENTRY='d/RECORD.jws': embedding rewrites RECORD, ...; --allow-signed-wheel removes it (re-sign the wheel after) -- wheel refused` | U | `wheel-unusable/signed` |
| R8 | _wheel_sbom_location:72 | E | `ARCHIVE='a': <problem> -- wheel refused` (4 problems) | U | `dist-info-missing`, `dist-info-ambiguous` |
| D1 | _wheel_sbom_location:70 | W | `ARCHIVE='a': the file name names no top-level .dist-info; using d/` | U | `dist-info-conflict` |
| D2 | extract/wheel:264 | W | `ARCHIVE='a': <problem>[ -- identity unknown]` | U | the three `dist-info-*` |
| D3 | wheel_dist_info:521 | W | `ARCHIVE='a': no d/METADATA -- identity unknown` | U | `dist-info-missing` |
| A1 | archive_member_names:166 | W | four: `no safe install location -- skipped`; `overwritten by later entry 'n' -- skipped`; `also a directory of other entries -- skipped`; `non-conforming name -- recorded as 'n'` | U | `archive-member-unsafe`, `-conflict` x2, `-invalid` |
| A2 | archive_member_names:200 | W | `... directory entry carries data -- skipped` | U | `archive-member-invalid` |
| A3 | build_and_read:122 | W | `Build: ARCHIVE=.. ENTRY=..: resolves outside the extraction directory -- skipped, not written to disk` | U | `archive-member-unsafe` |
| A4 | _sdist_scan:184 | W | `ARCHIVE='s': members share a project path ('p', ...); they would share one ID registry key` | U | `archive-member-conflict` (Q6) |
| S1 | utils:259 | E | `no SBOM found under .dist-info/sboms/ in 'a'[ matching 'n']` | U | `wheel-sbom-missing` |
| S2 | _wheel_sbom_location:208 | E | `Multiple SBOMs found under 'd/sboms/' in 'a' ('x', 'y') -- pass --sbom-filename to disambiguate` | C | `wheel-sbom-ambiguous` |
| S3 | verify_wheel:54 | W | `'a': d/sboms/x doesn't use the recommended '.spdx3.json' extension for its format` | U | `wheel-sbom-wrong-format` |
| S4 | verify_wheel:47 | W | `'a': unrecognized SBOM format for d/sboms/x; cannot check the recommended extension` | U | `wheel-sbom-unusable` |
| S5 | validate_wheel:49 | W | `'a': no validator registered for x's format (unrecognized); skipping content validation` | U | `wheel-sbom-unusable` |
| S6 | verify_wheel:96, embed:139 | W | `'a': <fragment>`: six "cannot cross-check" texts from `_sbom_format.py:233-319` | U | `wheel-sbom-unusable` |
| S7 | verify_wheel:103,105; embed:146,148 | E/W | `'a': SBOM/wheel name: wheel declares 'x', SBOM declares 'y'; version: ...` | U | `wheel-sbom-conflict` |
| S8 | utils:370 | E | `<wheel>/<member>: <SpdxValidateError text>` | U | `sbom-invalid` (Q9) |
| S9 | utils:385 | E | spdx3-validate findings, one tagged line per text line | U | relay + `sbom-invalid` (Q9) |
| E1 | batch:71 | I | `removed d/RECORD.jws from a: it signed the RECORD the embed rewrote; re-sign the wheel` | U | `wheel-unusable/signed` |
| E2 | batch:78 | I | `removed stale SBOM d/sboms/x from a` | - | `wheel-sbom-conflict/held` |
| E3 | _embed_stale:99 | W | `d/sboms/x: kept, not a build or analyzed SBOM of this wheel's name and version` | U | `wheel-sbom-conflict/held` |
| E4 | batch:84 | I | `a's embedded SBOM entry timestamp was before 1980 and was floored to 1980-01-01 (ZIP format limitation); ...` | - | `datetime-not-recordable` |
| E5 | embed_wheel:168 | I | `embed-wheel: no --project-dir given; the SBOM is built from the wheel alone (...)` | C | `option-missing/project-dir` |
| E6 | _embed_generate:108 | W | `SBOM <path>: byte order mark dropped (JSON text must not have one)` | U | `json-malformed/bom` |
| E7 | _embed_wheel:463 | W | `<resolved name>: file mode not restored: <exc>` | U | `file-unwritable/mode` |
| E8 | _embed_wheel:152 | E | `Invalid SBOM filename: '../x.spdx3.json'` | C | `option-invalid` (Q14) |
| V1 | verify_wheel:165 | I | `verify-wheel: N wheel(s) OK` | - | Summary |
| V2 | validate_wheel:118,125 | I | `validate-wheel: N wheel(s) valid[, M skipped ...]` | - | Summary x2 |
| H1 | hatch:86 | E | `Hatchling version unknown (no package metadata found); requires >= 1.29.0 for PEP 770 SBOM embedding.` | U | `library-unusable` (Q15) |
| H2 | hatch:97 | E | `Hatchling <v> too old for PEP 770 SBOM embedding (requires >= 1.29.0); upgrade Hatchling.` | U | `library-unusable` |
| H3 | hatch:360 | E | `SBOM file name 'n' is also, ignoring case, the name of sbom-files entry 'p'; set [tool.pitloom] sbom-basename ...` | U | `sbom-name-conflict` |

Out of PR 16, with reasons: `_embed_overlay.py:117` (project name is not
the wheel's; authors from the wheel) is the sibling of
`warn_project_authors_unread` (`extract/_author_warnings.py:165`, PR 17's
author family): PR 17. `_embed_wheel.py:430` (`SBOM content cannot be
empty`) is library-only (the CLI refuses an empty `--sbom` first as
`json-malformed`): PR 17's `call-invalid`. `utils.py:196`
(`report_error_line`, `print_error(str(exc), code=code_of(exc))`) forwards;
it leaves the count only by an inventory rule (Q16).

## 2. Probes (01d1a726; hand-zipped wheels, `ZipInfo` dated 2020-01-01)

Probe tree under the session scratchpad (`pr16/`), deleted afterwards. The
texts in section 1 are the captured stderr (V); the stdout lines
(`WHEEL=... STATUS=...`, `WHEEL=... SBOM=...`) do not change.

- **P1. The skills' "identity unknown before the ERROR" is false (V).**
  For two top-level `.dist-info` and no matching name, `embed-wheel`,
  `wheel --embed`, `verify-wheel` and `validate-wheel` print only R8's
  `ERROR:`; only `loom wheel`/`generate` warn (D2, exit 0).
  `sbom-validate/SKILL.md:171-173` and `known-limitations.md:309-310` say a
  `WARNING: ... -- identity unknown` comes first.
- **P2. `validate-wheel` findings (V).** An SBOM with one bad element gave
  two identical `[schema] $['@graph'][0]: Is not valid` lines and an empty
  `ERROR: loom validate-wheel: ` line (a blank line of the SHACL text);
  tabs print as `\t` (escaped).
- **P3. `None` in a message (V).** A non-SPDX embedded or `--sbom` file
  gives `cannot cross-check name/version for unsupported SBOM format None`;
  a CycloneDX file is "unrecognized" (`detect_sbom_format` returns `None`)
  and `--sbom` embeds it as `<name>.spdx3.json` (known bug, already listed).
- **P4. `--sbom-basename ../x` is refused late (V).** `sbom_base_name`
  returns a value unchanged when nothing is stripped (`file_names.py:90`)
  and skips the plain-name check; `embed-wheel` generates the SBOM (and runs
  any `--allow-build` build) before E8's uncoded refusal, exit 1.
- **P5. "skipped" in an embed (V).** `embed-wheel` on a wheel with
  `../evil.py`, `/abs.py` and a directory entry with data prints A1/A2
  `-- skipped`, but the rewritten wheel still holds those members: they are
  only left out of the SBOM.
- **P6. Shapes disagree (V).** Refusals and D-lines quote with
  `quote_source` (credentials masked); S3-S5, E1-E3 name members with
  `loggable` (unquoted, credentials not masked); S7's values are `%r` of
  `METADATA` and SBOM text (not masked, not cut); E6 names the path
  unquoted; E7 names the resolved file (a symlink's target), not the name
  given.
- **P7. One `loom id import` asymmetry (V by reading).**
  `id_registry/_sbom_read.py:43` reads the same `read_given_sbom` but drops a
  byte order mark silently; `embed-wheel --sbom` warns (E6).
- **P8.** Signed wheel: R7 then exit 1, wheel untouched; with
  `--allow-signed-wheel`, E1 and exit 0. `SOURCE_DATE_EPOCH=0`: E4. Damaged
  member: R4 on `wheel`/`embed-wheel`, but `verify-wheel` reads only names,
  `METADATA` and the SBOM, so it reports S1, not R4 (by design, V).

## 3. Contradictions (plans and docs versus the tree)

- C1. Row 16's families (`wheel-sbom-check 13; wheel-embed-action 4;
  archive-member-refused 10`) and "-28" are stale (section 0).
- C2. frames-forward keeps ` -- wheel refused` in the template; the
  catalogue grammar (`CONDITION[; ACTION]`, PR 15's `; not merged`) says
  `; wheel refused` (Q1).
- C3. frames-forward: "`entry` exists". It does, but its writer is
  `free_text` (unquoted unless a control character): reusing it drops
  today's quotes (Q18).
- C4. Row 17 lists `_embed_generate.py` under escaped text; its one uncoded
  site is the byte order mark line, which the PR 3 forward note gives to
  PR 16. PR 17's count drops by one.
- C5. P1: two skill texts claim a line no command prints.

## 4. Design

### 4.1 Subjects, fields, frames

- Subjects `ARCHIVE=` (the archive's file name as given, never its
  directory) and `ENTRY=` (the raw member name); both new subject keys of
  the catalogue. Fields `archive` and `member`, writer `quoted_text`
  (`quote_source`: masked, escaped, quoted; today's bytes, Q18). A wheel is
  always `ARCHIVE=`, also in S3-S7 (today `'a.whl':`).
- New fields: `exception_type` (`exception_label`, a class name only, never
  the exception's text: R3-R5 keep naming the type), `problem` (closed
  table: the four `PROBLEM_*` of `wheel_dist_info.py:373-381`),
  `wheel_value`, `sbom_value` (S7: `excerpt`, masked then cut to 120 then
  escaped), `why` (S6: closed table), `extension`. Reuse `file`, `files`,
  `failure`, `number`, `option`, `version`, `entry`.
- `BUILD_FRAME.codes` gains `archive-member-unsafe`,
  `archive-member-conflict`, `archive-member-invalid` (A1-A3 on the build
  route; `archive_member_names.py` already takes `frame`, PR 14).
  `HOOK_FRAME` (ERROR, every code) covers H1-H3. No new frame.

### 4.2 Codes (new, `since="0.25.0"`; topics in 4.4)

Templates are proposals; step 1 fixes them against `template_problem`.
`<R>` is `; wheel refused` (Q1).

| Code | Lvl | Effect / actor | Template (proposal) |
| - | - | - | - |
| `wheel-unreadable` | E | not-written / U | `ARCHIVE=%(archive)s: could not open as a ZIP archive (%(exception_type)s)<R>`; `ARCHIVE=%(archive)s ENTRY=%(member)s: could not read (%(exception_type)s)<R>` |
| `wheel-invalid` | E | not-written / U | `... ENTRY=%(member)s: NUL in member name<R>`; `... ENTRY=%(member)s: duplicate member name<R>` |
| `wheel-unusable` | E | not-written / U | `... ENTRY=%(member)s: .dist-info member under a non-conforming name<R>` |
| `wheel-unusable/signed` | E, I | not-written / U | E `... ENTRY=%(member)s: signs the RECORD the embed rewrites; --allow-signed-wheel removes it (re-sign after)<R>`; I `... ENTRY=%(member)s: signature removed; re-sign the wheel` |
| `dist-info-missing` | E, W | not-written; W: thinner / U | `ARCHIVE=%(archive)s: no top-level .dist-info<R>`; W `...; identity unknown`; W `ARCHIVE=%(archive)s ENTRY=%(member)s: METADATA missing; identity unknown` |
| `dist-info-ambiguous` | E, W | as above | `ARCHIVE=%(archive)s: %(problem)s<R>` and `...; identity unknown` |
| `dist-info-conflict` | W | weaker / U | `ARCHIVE=%(archive)s: the file name names no top-level .dist-info; using %(entry)s` |
| `archive-member-unsafe` | W | thinner / U | `[Build: ]ARCHIVE=.. ENTRY=..: no safe install location; not listed`; build: `...: resolves outside the extraction directory; not copied` |
| `archive-member-conflict` | W | thinner / U | `...: overwritten by later entry %(entry)s; not listed`; `...: also a directory of other entries; not listed`; A4: `ARCHIVE=..: members share a project path (%(files)s); they would share one ID registry key` |
| `archive-member-invalid` | W | none / U | `...: non-conforming name; listed as %(entry)s`; `...: directory entry carries data; not listed` |
| `wheel-sbom-missing` | E | none / U | `ARCHIVE=%(archive)s: no SBOM under .dist-info/sboms/` and `... named %(entry)s` |
| `wheel-sbom-ambiguous` | E | none / C | `ARCHIVE=%(archive)s: %(number)s SBOMs under .dist-info/sboms/ (%(files)s); pass --sbom-filename` |
| `wheel-sbom-wrong-format` | W | none / U | `ARCHIVE=.. ENTRY=..: SBOM does not end in %(extension)s, its format's recommended extension` |
| `wheel-sbom-unusable` | W | weaker / U | `...: SBOM format not recognised; extension not checked`; `...: no validator for the SBOM's format; not validated`; `ARCHIVE=..: SBOM name and version not cross-checked: %(why)s` |
| `wheel-sbom-conflict` | W, E | weaker; E: not-written / U | `ARCHIVE=%(archive)s: the SBOM states %(part)s %(sbom_value)s, the wheel's METADATA %(wheel_value)s` (one line per part, Q8) |
| `wheel-sbom-conflict/held` | W, I | none / U, - | W `ARCHIVE=.. ENTRY=..: another SBOM already in the wheel; kept`; I `...: an earlier Pitloom SBOM of this wheel; removed` |
| `datetime-not-recordable` | I | none / - | `ARCHIVE=%(archive)s: SBOM entry dated 1980-01-01, the earliest a ZIP holds; the SBOM's created keeps the true date` |
| `sbom-name-conflict` | E | not-written / U | `FILE=%(file)s: also the name, ignoring case, of sbom-files entry %(entry)s; set [tool.pitloom] sbom-basename or drop the entry` |

Lines added to shipped families (each unreleased or additive):
`option-missing/project-dir` (I, E5: `--project-dir not given; the SBOM is
built from the wheel alone, not from the project here`), `json-malformed/bom`
(W, E6: `FILE=%(file)s: SBOM starts with a byte order mark; dropped`),
`file-unwritable/mode` (W, E7: `FILE=%(file)s: file mode not restored;
%(failure)s`), `option-invalid` (E8, through `invalid_value(Parameter(...),
"file-name")`), `library-unusable` (H1, H2: `Hatchling %(version)s cannot
embed an SBOM (PEP 770 needs 1.29.0 or later); upgrade Hatchling`, and an
unknown-version twin), `sbom-invalid` (S8/S9: `FILE=%(file)s: not valid SPDX
3 (%(number)s finding(s) above)` and `FILE=%(file)s: could not be validated;
%(failure)s`).

Summaries (R1, text unchanged): V1, V2.

Advice sketch: unreadable/invalid: the wheel is damaged or not built by a
conforming tool, rebuild it; unusable: rebuild with a conforming tool;
signed: ask before `--allow-signed-wheel`, re-sign after (copy the skill's
rule); dist-info: rebuild or rename the file to its PEP 427 name; members:
nothing to do unless the producer is theirs; sbom-missing: embed first;
ambiguous: the caller adds `--sbom-filename`; conflict: regenerate the SBOM
for this wheel, `--fail-on-mismatch` in CI; held: remove the other SBOM if
it is stale; mismatch E (embed): `--allow-mismatch` only if the user says so.

### 4.3 Mechanism

- `WheelRefused` becomes a `CodedValueError` (as `NotAWheelError` is);
  `refusal()` is replaced by one constructor per line in
  `messages/_wheels_say.py` (`refuse_nul_name(archive, raw)`, ...), each
  naming its entry statically so the inventory sees a coded helper (the
  PR 15 unknown: check with a fixture at step 1). `unreadable_member_error`,
  `refuse_unreadable`, `RefusingReader` and the lambda call them.
- `resolve_own_dist_info` keeps returning a `DistInfoChoice`; `problem`
  becomes the line (a `Line` object), not a text tail, so D1, D2 and R8
  share one table.
- `archive_member_names.py`: `_MSG` and the four templates go; one
  say-helper `warn_archive_member(log, kind, archive, raw, *, frame,
  listed_as=None)` with a closed `kind`. The `logger is None` second read
  stays silent.
- One mismatch helper for `embed.py` and `verify_wheel.py`
  (frames-forward); `check_spdx3_name_version` returns structured causes
  (a `why` id and values), not texts, so `_sbom_format.py` holds no prose.
- `verify_wheel.py:103`'s `log.error` becomes `emit` at ERROR (the command
  frame added by the formatter, as today).
- Validator (Q9): each finding line goes through a prefixed relay
  (`spdx3-validate: `, `_relay.py`'s `prefixed` shape, as `licenseid: `),
  blank lines dropped, identical consecutive lines kept (they are the
  validator's); then one coded `sbom-invalid` line per document.
- E8: `embed_wheel_sbom` checks `sbom_basename` with `is_plain_file_name`
  before any generation (P4); `_validate_sbom_filename` keeps guarding the
  library's `sbom_filename` with `Parameter("sbom_filename")`.

### 4.4 Topics and pages

Two new topics (one page would near the 30,000-byte limit, I: 16 families,
about 26 KB): `wheels` ("Wheels": `wheel-*` refusals, `dist-info-*`,
`archive-member-*`; about 14 KB) and `wheel-sboms` ("Embedded SBOMs":
`wheel-sbom-*`, `datetime-not-recordable`, `sbom-name-conflict`; about
11 KB). Variants grow shipped pages: `files` (26,059 B) by about 1.5 KB
(`json-malformed/bom`, `file-unwritable/mode`), `targets` (26,737 B) by
about 0.6 KB (`sbom-invalid`), `options`, `models`: step 1 measures; over
29,000 B moves E6/E7 to new families on `wheel-sboms` (Q17).

### 4.5 Surfaces and exit codes

| Codes | wheel, generate | wheel --embed, embed-wheel | verify, validate | hook | library |
| - | - | - | - | - | - |
| `wheel-unreadable`, `-invalid` | E | E | E | - | raise |
| `wheel-unusable(/signed)` | - | E (I with flag) | - | - | raise |
| `dist-info-*` | W | E (D1: W) | E (D1: W) | - | W / raise |
| `archive-member-*` | W (build: `Build: `) | W | - | - | W |
| `wheel-sbom-*`, `datetime-not-recordable` | - | W/E/I (`--verify`, `--sbom`) | W/E | - | W / raise |
| `sbom-name-conflict`, `library-unusable` | - | - | - | E | - |

Exit codes unchanged (V: section 2 runs), except E8 (exit 1 as before, but
before generation). Verify stays structural (`wheel-sbom-*` and the
refusals); validate stays content (`sbom-invalid` plus the relay); the
skills keep naming the two commands apart.

### 4.6 Skills and docs that quote these lines

`sbom-validate/SKILL.md:153-176` (refusal shape, P1, `[code]`s),
`sbom-generate/SKILL.md:210-218`, `references/known-limitations.md:268-315`,
`references/embed-wheel.md` (no quoted line; re-read),
`sbom-enrich/references/model-stub-diagnosis.md:48`; `docs/wheel-sbom.md`
(56-120, 181-197, 350-377), `docs/hatchling-build-hook.md:124`,
`docs/github-action.md:224`; `scripts/manual_cli_checks/_checks_wheel.py:23`
(`_REFUSED`). No command or flag changes: no `description` edit, no
`_matrix_plan.py` entry.

## 5. Rulings (Qn: recommendation, then the alternative)

User decision needed: Q1, Q5, Q8, Q9, Q12, Q14 (stderr or behaviour a
script may parse); Q2-Q4, Q7, Q11, Q15 (code names); Q17 (pages).

**User rulings (2026-11-23):** Q1 `; wheel refused`; Q9 relay each finding
as `spdx3-validate: <line>` plus one coded `sbom-invalid` line per document
(also changes `fragment validate`); Q12 `json-malformed/bom`, `loom id
import` says it too; Q14 refuse `--sbom-basename` up front as
`option-invalid`. All four as recommended. Q5, Q8, Q2-Q4, Q6, Q7, Q10, Q11,
Q13, Q15-Q20 stand as recommended unless the user vetoes them at review.

- **Q1. Refusal suffix.** [`; wheel refused` (grammar, PR 15).] Alt: keep
  ` -- wheel refused` (frames-forward; three skill quotes and one manual
  check unchanged).
- **Q2. Refusal families.** [`wheel-unreadable`, `wheel-invalid`,
  `wheel-unusable` (+`/signed`): one condition each.] Alt: one
  `wheel-invalid` for all nine lines.
- **Q3. `.dist-info` choice.** [`dist-info-missing`, `-ambiguous`,
  `-conflict`; ERROR where a command needs the directory, WARNING where it
  only names the package.] Alt: one `wheel-identity-unknown`-like family
  (no such condition: `wheel-identity-missing`).
- **Q4. Member lines.** [Three families by condition.] Alt: row 16's one
  `archive-member-unsafe` (a "non-conforming name, listed as" line is not
  unsafe).
- **Q5. "skipped" (P5).** [`; not listed` for wheel and sdist reads, `; not
  copied` on the build route.] Alt: keep `skipped`.
- **Q6. A4.** [`archive-member-conflict`: it is said on every read, with or
  without a registry.] Alt: a line of `registry-key-ambiguous`.
- **Q7. Embedded-SBOM families.** [`wheel-sbom-missing`, `-ambiguous`
  (actor caller), `-wrong-format` (extension), `-unusable` (cannot check),
  `-conflict`.] Alt: row 16's `wheel-sbom-missing`, `-invalid` (`-invalid`
  beside `sbom-invalid` blurs verify and validate).
- **Q8. Mismatch lines.** [One line per part (name, version): a template
  has one shape.] Alt: one line with a joined `mismatches` field (today's
  line count).
- **Q9. Validator output.** [Relay each finding as `spdx3-validate: <line>`
  (out of the ratchet), drop blank lines, then one coded `sbom-invalid` line
  per document; `fragment validate` too.] Alt: code each finding line
  `sbom-invalid` (dozens of coded lines per SHACL finding).
- **Q10. Summaries.** [V1, V2 as Summaries, text unchanged.] Alt: none.
- **Q11. Embed decisions.** [E1 `wheel-unusable/signed` I; E2/E3
  `wheel-sbom-conflict/held`; E4 `datetime-not-recordable`; E5
  `option-missing/project-dir`.] Alt: E2 and E4 as Summaries.
- **Q12. Byte order mark.** [`json-malformed/bom`; `loom id import` says it
  too (P7, one new `WARNING:` there).] Alt: code E6 only, leave the import
  silent (roadmap).
- **Q13. File mode.** [`file-unwritable/mode`, naming the wheel as given.]
  Alt: a line of `wheel-unusable`.
- **Q14. `--sbom-basename ../x` (P4).** [Refuse before generation as
  `option-invalid`; CHANGELOG `Fixed`.] Alt: code E8 where it is.
- **Q15. Hook lines.** [H1/H2 `library-unusable`; H3 new
  `sbom-name-conflict`.] Alt: H3 as a variant `file-discovery-conflict/sbom`
  (ERROR).
- **Q16. Left out.** [`_embed_overlay.py:117` to PR 17 (author family);
  `_embed_wheel.py:430` to PR 17 (`call-invalid`); `utils.py:196` to the
  final sweep.] Alt: teach `_relay.py` that a helper whose body is only
  `print_error(str(p), code=code_of(p))` of its exception parameter relays
  (-1 more).
- **Q17. Pages.** [Two topics, `wheels` and `wheel-sboms`.] Alt: one
  `wheels` page, if step 1 measures it under 27,000 B.
- **Q18. Member names.** [Quoted (`quoted_text`), never cut: a name is an
  identifier, and `quote_source` masks credentials.] Alt: reuse `entry`
  (unquoted) or cut at 1,000 characters. **Ruled (after step 1):** "never
  cut" is overruled for display: every name (member, archive, list entry,
  `FILE=` of a relayed or clashing name) is masked, cut to `NAME_CHARACTERS`
  (500) with `...`, then quoted and escaped, so a line never passes
  `LONGEST_LINE` and loses its code. The cap bounds the report only; the
  member is still read and compared in full.
- **Q19. Exception text.** [R3-R5 name the type only, as today
  (`zipfile`'s text quotes member names).] Alt: `failure` (masked, cut 500).
- **Q20. P2, P3, P6 fixes.** [In this PR: they are the lines' shapes.]
  Alt: roadmap.

Steps, tests, verification and risks (sections 6 to 9) are in
[message-catalogue-pr16-plan-steps.md](message-catalogue-pr16-plan-steps.md).
