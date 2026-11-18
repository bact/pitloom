---
Created: 2026-11-18
Last-Modified: 2026-11-18
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message catalogue PRs 12 and 18: project metadata and licences

See also: [message-catalogue-pr8-9-config-plan.md](message-catalogue-pr8-9-config-plan.md)
(the shape of this plan; `config-malformed`),
[message-catalogue-pr8-12-plan.md](message-catalogue-pr8-12-plan.md) (rulings
1 to 4, the family 12 contract),
[message-catalogue-migration-plan.md](message-catalogue-migration-plan.md)
(rows 12 and 18, R1 to R7),
[message-frames-forward.md](message-frames-forward.md) ("PR 12", "PR 18",
the dynamic-level rule),
[message-catalogue-review-rounds.md](../implementation/message-catalogue-review-rounds.md)
(open items 121 and 122),
[licence-resolution-provenance.md](licence-resolution-provenance.md) (T14
task 4 waits on PR 18).

Status: plan, 2026-11-18, on 137b2b88 (PRs 8 and 9 merged as #497).
Sites from `message_inventory --jsonl`, `in_scope` and not `coded`, each
read in the source. "Verified" means read or run (CLI probes: bad TOML,
non-UTF-8 `pyproject.toml`, `setup.py` syntax error, bad `setup.cfg`, an
overlong version, an sdist with bad TOML, licence plus classifiers).

## 0. Counts

The ratchet baseline holds **219** uncoded sites (`--check` passes). The 33
modules of the two families hold 68 of them; 2 are not theirs
(`core/_models_wheel_dispatch.py:198`, the `--allow-build` line, PR 14;
`extract/project/_sdist_scan.py:184`, members sharing a registry key, PR
16). So **58** sites for PR 12 and **8** for PR 18 (the migration plan's 8,
confirmed). The plan said 50 for PR 12; the 8 sites the 2026-11-17
contract and ruling 4 added (`deps_installed.py` 3, `_requirements_files.py`
2, `core/project.py`, `_extract_utils.py`, `config_cascade.py`) account
for the difference (not matched site by site to the classifier's 50).

Ratchet: **219 to 211** after PR 18, **211 to 153** after PR 12 (153 in
one go). 154 if Q11 moves `_extract_utils.py:261` out.

Not a site, still in scope: a project `pyproject.toml` that is not TOML
or not UTF-8 escapes raw from `_toml_io.load_toml_file` (verified:
`ERROR: loom project: Invalid value (at line 4, column 7)`, no `FILE=`, no
code). Loads: `extract/project/pyproject.py:287`, `reader.py:91`,
`hatchling.py:60` (hook), `core/_config_parse.py:417` (hook
`plugins/hatch.py:413`), `cli/options_resolve.py:282` (`--verbose`).

## 1. Sites

Routes: P project directory (CLI, library `generate_project_sbom`,
`read_project`; Action through the CLI), H Hatchling hook, S sdist
archive, W Core Metadata (wheel, sdist `PKG-INFO`, installed), A any
licence reader. `q` = silent when `quiet` (a second read). Text abridged.

### 1.1 PR 12: project metadata (58)

| # | Site | Lvl | Text today | Code | Route |
| - | - | - | - | - | - |
| 1 | `core/_models_wheel_dispatch.py:100` | W | `Build: <cause> in <dir> -- falling back to Hatchling-based heuristic` | by `failed`: `file-discovery-unusable` or `-needs-build` | P |
| 2, 3 | `:112,122` | W | `Build: <backend>'s static config failed introspection ...` / `Build: File discovery failed (above) ...` | `file-discovery-unusable` | P |
| 4 | `:129` | W | `Build: No static <backend> config ... imperative setup.py build` | `file-discovery-needs-build` | P |
| 5, 6 | `:255,265` | W | `Build: file discovery for build backend %r is not yet backend-aware ...` | `file-discovery-needs-build` | P |
| 7 | `core/_models_wheel_types.py:81` (5 callers) | W | `<Backend> file discovery failed for <dir>: <text>` | `file-discovery-unusable` | P, H |
| 8 | `core/_models_wheel_setuptools.py:268` | W | `<dir>: both A and B resolve to the same wheel path P -- keeping A, dropping B` | `file-discovery-conflict` | P |
| 9 | `:345` | W | `setup.py in <dir> passes K imperatively -- ...` | `file-discovery-needs-build` | P |
| 10 | `:406` | W | `<dir>: setuptools could not auto-discover packages unambiguously` | `file-discovery-unusable` | P |
| 11 | `core/_models_wheel_flit.py:70` | W | `<dir>: could not resolve a static version for [tool.flit.external-data]` | `file-discovery-needs-build` | P |
| 12 | `core/_models_wheel_setuptools_relay.py:59` | W/D | `<dir>: setuptools stderr: <line>` | relay, uncoded (Q6) | P |
| 13 | `extract/project/pyproject.py:164` | E | `Failed to parse project metadata: 'project.K' <reason>` | `metadata-invalid` | P |
| 14-16 | `:210,248,253` | E | `Failed to parse project metadata: <pyproject-metadata text>` | `metadata-invalid` | P |
| 17 | `:469` | W | `<dir>: [tool.poetry] metadata could not be parsed (<exc>) -- ...` | inner code, WARNING (Q3) | P |
| 18 | `poetry.py:160` | E | `[tool.poetry] in pyproject.toml is not a table` | `metadata-invalid` | P, H |
| 19, 20 | `:162,174` | E | `[tool.poetry] section not found` / `Project name is required ...` | `project-name-missing` | P |
| 21 | `_poetry_fields.py:105` | W | `<file>: <where> is <T>, expected <T2> -- ignoring it` | `metadata-invalid` | P, H |
| 22 | `_poetry_extras.py:179` | W | `Ignoring <what>: <reason>` | `metadata-no-effect` | P, H |
| 23 | `_poetry_requirements.py:89` | W | `poetry-core: API not found (<exc>); ...` | `library-unusable` (Q7) | P, H |
| 24 | `pdm.py:112` | W | `PDM dynamic version source %r ... not resolvable without executing project code` | `dynamic-field-needs-build` | P |
| 25, 26 | `pdm.py:175`, `flit.py:101` | W | `PDM`/`Flit dynamic ... resolution failed for <p>: <exc>` (raw `exc`) | `dynamic-field-unusable` | P |
| 27 | `setuptools.py:236` | W | `<dir>: <setup.py error> -- reading setup.cfg alone` | row 34's code, WARNING (Q3) | P |
| 28 | `setuptools.py:267` | E | `No usable project metadata found in <dir>. ...<setup.py error>` | `project-name-missing` | P |
| 29, 31 | `setuptools_cfg.py:269,292` | E | `Could not parse setup.cfg: <file> <where>: <reason>; ...` | `config-malformed` | P |
| 30 | `setuptools_cfg.py:271` | E | `Could not parse setup.cfg: <exc>` | `file-unreadable[/not-utf8]` or `config-malformed` | P |
| 32 | `setuptools_cfg.py:323` | E | `Project name is required in setup.cfg [metadata] section` | `project-name-missing` | P |
| 33 | `setuptools_py.py:106` | W | `setup.py: %r <reason> -- treating it as undeclared ...` | `metadata-invalid` | P |
| 34 | `setuptools_py.py:287` | E | `Could not parse setup.py: <exc>` | `file-unreadable` or `metadata-malformed` | P |
| 35 | `setuptools_py.py:311` | E | `Could not extract project name from setup.py. ...` | `project-name-missing` | P |
| 36 | `_setuptools_dynamic.py:172` | W | `pyproject.toml: '<key>' <reason> -- ignoring it` | `metadata-invalid` | P |
| 37 | `_setuptools_dynamic.py:241` | W | `pyproject.toml: dynamic <fields> not read from <file>: <exc>` | inner code, WARNING (Q3) | P |
| 38 | `_setuptools_options.py:394` | W | `<subject>: setup.py and setup.cfg disagree on K ... -- keeping X's` | `metadata-conflict` | P |
| 39 | `_setup_cfg_directives.py:295` | W | `FILE=<f>: RecursionError parsing the <attr> line; skipped ...` | `metadata-malformed` | P |
| 40 | `sdist.py:166` | W | `Failed to parse pyproject.toml from sdist member: <sdist>: <exc>` | `config-malformed` WARNING or `file-unreadable/not-utf8` | S |
| 41 | `sdist.py:277` | E | `config file '<sdist>:pyproject.toml': <exc>` | forward (2.4) | S |
| 42 | `_sdist_pyproject.py:36` | W | `<sdist>:pyproject.toml: %r is <T>, expected <T2> -- ignoring it` | `metadata-invalid` | S |
| 43 | `_sdist_pyproject.py:138` | W | `<sdist>:pyproject.toml: dynamic field(s) not resolved without PKG-INFO` | `dynamic-field-needs-build` | S |
| 44 | `reader.py:76` | W | `<file> has no usable [project] table ... -- falling back to setup.cfg/setup.py` | `metadata-no-effect` (Q9) | P |
| 45, 47 | `installed.py:115,138` | W | `<label> exists but has no <marker>` / `declares name N, which does not match ...` | `installed-metadata-unusable` | P |
| 46, 49 | `installed.py:125,319` | W | `<marker> could not be read` / `could not be re-read` | `file-unreadable` (2.5) | P |
| 48 | `installed.py:197` | W | `multiple installed-metadata candidates found (...) -- using X` | `installed-metadata-ambiguous` | P |
| 50 | `_installed_reconcile.py:107` | W | `<subject> disagrees on K (declared %r, installed %r) -- keeping declared` | `metadata-conflict` | P |
| 51 | `_requirements_files.py:253` | W | `<config>: skipping pip option line(s) ...` | `metadata-no-effect` | P |
| 52 | `_requirements_files.py:356` | W | `FILE=<f>: could not read for <field>; not found` (`file-unreadable`'s text, no code) | `metadata-invalid` | P |
| 53, 55 | `assemble/spdx3/deps_installed.py:341,363` | W | `Locked version %r for dependency %r conflicts with declared exact pin` / `does not satisfy` | `dependency-pin-conflict` | P |
| 54 | `deps_installed.py:354` | W | `Dependency %r declared as %r couldn't be parsed -- ... using it anyway` | `requirement-invalid` | P |
| 56 | `core/project.py:394` | W | `merge_project_metadata: both sides have a field_conflicts entry ...` | `metadata-conflict` or `InternalError` (Q10) | P |
| 57 | `extract/_extract_utils.py:261` | E | `Cannot read <subject> <where>: <why>` (URL or absent file) | Q11 | - |
| 58 | `core/config_cascade.py:237` | E | `config file '<p>': <exc>` (uncoded residue) | forward (2.4) | P, library |

12 discovery rows, 46 reader rows; 2 vanish by forwarding (41, 58), 1 by
relay shape (12).

### 1.2 PR 18: licences (8)

| # | Site | Lvl | Text today | Code | Route |
| - | - | - | - | - | - |
| L1 | `extract/_license_classify.py:94` | W | `LICENSE=%a: has characters that cannot be encoded; each replaced with U+FFFD` | `text-malformed` (Q14) | A |
| L2 | `:185` | W | `LICENSE=%r: not a valid SPDX license expression (<reason>); recorded as license text` | `license-expression-malformed`/`-invalid` (Q12) | A |
| L3 | `:205` | W | `FIELD=<f> LICENSE=<v>: not read as an SPDX license expression (<reason>); ...` | same split | A |
| L4 | `extract/_core_metadata.py:198` | W | `CLASSIFIERS=%r: several license classifiers; recorded as %r, assuming AND ...` | `license-ambiguous` | W, P |
| L5 | `extract/_license_resolve.py:221` | I/D | `[FIELD=<f> ]LICENSE=<v>: read as <expr> (<steps>)` | INFO coded, DEBUG plain (2.6) | A |
| L6 | `extract/_license_text_match.py:97` | I | `licenseid database not found: <path> -- license text detection skipped; run ...` | `license-db-missing` | A |
| L7 | `:107` | W | `licenseid database cannot be used: <LicenseID text> -- license text detection skipped` | `license-db-unusable` (Q13) | A |
| L8 | `extract/project/pyproject.py:228` | W | `<file> declares both an SPDX license expression and legacy License :: classifiers -- dropping ...` | `license-conflict` | P |

Uncoded on purpose: `extract/_licenseid_relay.py:88` (`say`: `log_once(log,
level, line, "%s", line)`, `PREFIX = "licenseid: "` at `:64`), LicenseID's
own grammar. Excluded today by `PASSTHROUGH_PAT` (`^%s$`,
`scripts/message_inventory/_scope.py:111`); frames-forward ruling 6 moves
the exclusion to a relay shape in `scripts/message_inventory/_relay.py`
(count unchanged). Row 12 takes the same shape (Q6).

### 1.3 Not in scope, found while listing

- `plugins/hatch.py` has no file-discovery line (frames-forward's `:177`
  is stale): the hook's `get_wheel_files(assume_backend="hatchling")`
  (`:176`) reaches row 7 via `_models_wheel_hatchling.py:154`; the six
  dispatch rows are skipped (`_models_wheel_dispatch.py:390`).
- `plugins/hatch.py:86,97,388,394,404,465,512`: PR 14 or 16 (`:465` still
  says `Pitloom: ` despite ruling 1).
- `extract/_author_warnings.py:168` (`<sdist>:pyproject.toml: project
  metadata not read (<exc>); authors from the PKG-INFO`): a TOML failure
  in PR 17's file. PR 12 adds the WARNING twin; PR 17 switches to it.
- `extract/env.py:92,96` (pipdeptree): no owning row; final sweep.

## 2. Design

### 2.1 Codes (all `since` 0.25.0)

Last tag `v0.24.0`; `CHANGELOG.md` `[Unreleased]` holds the catalogue
bullet. A line added to an older code carries that entry's `since` (no
per-line `since`).

New, topic `metadata` ("Project metadata", frames-forward "Topic pages"),
module `pitloom.messages.metadata`:

| Code | Cond. | Levels | Actor / effect | Advice (short) |
| - | - | - | - | - |
| `metadata-malformed` | malformed | E, W | user / not-written (E), thinner (W) | Fix the file's syntax where the line says (`setup.py` is Python). |
| `metadata-invalid` | invalid | E, W | user / not-written, thinner | The value named is refused (E) or ignored (W); fix it in the file. |
| `metadata-no-effect` | no-effect | W | user / none | The table or line is not read by this backend; move or drop it. |
| `metadata-conflict` | conflict | W | user / weaker | The grid: `kept X, dropped Y`; the SBOM states X. |
| `project-name-missing` | missing | E | user / not-written | Declare `name` (literal in `setup.py`). |
| `dynamic-field-needs-build` | needs-build | W | user / thinner | Only running the build knows the field; `PKG-INFO` or a built wheel has it. |
| `dynamic-field-unusable` | unusable | W | user / thinner | The backend's resolver failed (detail); report it. |
| `installed-metadata-unusable` | unusable | W | user / thinner | A `.dist-info`/`.egg-info` that is broken or another project's. |
| `installed-metadata-ambiguous` | ambiguous | W | user / weaker | Several candidates; the line names the one used. |
| `file-discovery-unusable` | unusable | W | user / thinner | The backend's discovery failed; `--allow-build` gives the exact list (runs build code). |
| `file-discovery-needs-build` | needs-build | W | user / weaker or thinner | Static reading cannot see the list; `--allow-build` (trust first). |
| `file-discovery-conflict` | conflict | W | user / thinner | Two files, one wheel path: the grid. |
| `dependency-pin-conflict` | conflict | W | user / weaker | Topic `dependencies`. Lock and declared pin disagree: the grid. |

Reused: `config-malformed` (TOML and INI syntax of a project's
`pyproject.toml` and `setup.cfg` on every route, plus a WARNING twin of
`TOML_LINE` for the sdist metadata-only and authors routes; its summary
today says "A project's or an sdist's pyproject.toml ... is not yet coded",
`messages/_config.py:203-204`: rewrite it), `file-unreadable` with a new
`READ_USES` entry `for the project metadata`, `library-unusable`,
`requirement-invalid`.

New, topic `licences` (exists, 3.0 KB, `messages/licences.py` 28 lines):

| Code | Cond. | Levels | Actor / effect | Advice |
| - | - | - | - | - |
| `license-expression-malformed` | malformed | W | user / weaker | Fix the operator syntax (`MIT OR`); the SBOM holds text. |
| `license-expression-invalid` | invalid | W, I (`/resolved`, Q12) | user / weaker | Use a listed id or a `LicenseRef-`; INFO: the reading is LicenseID's. |
| `license-ambiguous` | ambiguous | W | user / weaker | Several classifiers read as AND; state `license` (PEP 639). |
| `license-conflict` | conflict | W | user / none | `kept project.license, dropped the License :: classifiers`. |
| `license-db-missing` | missing | I, W | user / thinner | Run `licenseid update --source packaged` (offline). |
| `license-db-unusable` | unusable | W | user / thinner | Per LicenseID's reason; no home directory: set `HOME`. `loom` has no `--db`. |

Every advice ends with `ASK_FIRST`. No new condition word.

### 2.2 Fields

`_fields.py` is 445 lines: new fields go in `messages/_fields_metadata.py`
(as `_fields_config.py`). New: `license` (`entity_text`: URL credentials
masked, escaped; `excerpt` kept), `classifiers` (joined), `expression` and
`steps` (LicenseID's words, `free_text`), `backend` (declared
`build-backend`, untrusted, `quoted_text`), `kwargs` (joined). Reused:
`file`, `dir`, `field`, `failure`, `kept`, `dropped`, `package`,
`version`, `value`, `reason`, `outcome`.

### 2.3 Subjects and the `Build: ` prefix

- Subject first (frames-forward rule 1): `DIR=` for directory lines,
  `FILE=` for file lines, `PACKAGE=` (53 to 55); licences keep `LICENSE=`,
  `FIELD= LICENSE=`, `CLASSIFIERS=`; `licenseid database` stays a literal
  subject phrase (`_DB_PREFIX`, `_license_text_match.py:62`).
- `Build: ` leaves rows 1 to 6 (decided; in the stderr sweep);
  `BUILD_LOG_PREFIX` stays for `:198` until PR 14. The lead-ins
  `setup.py: `, `pyproject.toml: `, `PDM`, `Flit`, `poetry-core: ` go.
- No `%r`, no raw `exc` (rows 25, 26 print a multi-line backend error raw
  today).

### 2.4 Files that do not parse; wrappers

- One loader, `load_project_toml(path, *, source)` in a module both
  `core` and `extract.project` may import (`pitloom.core._project_toml`,
  unverified for cycles: live import test both orders): `TOMLDecodeError`
  and the `(ValueError, RecursionError)` residue to `config-malformed`
  `TOML_LINE`, `UnicodeDecodeError`/`OSError` to `file-unreadable`
  `for the project metadata`, absent to `input-not-found` (as
  `config_cascade.load_config_file` does, `config_cascade.py:214-231`,
  the precedent). The five load sites of section 0 call it; the sdist
  twin takes bytes and names `FILE=<sdist>:pyproject.toml`.
- Wrappers keep the inner code (frames-forward "Cross-PR interfaces"):
  `sdist.py:_member_config` and `config_cascade.py:233-237` drop the
  prefix-adding branch once the residue is shown unreachable (Q10 probe:
  every `raise` reachable from `parse_pitloom_config` coded; the one
  plain `ValueError` found, `core/_config_types.py:75`, is a library
  parameter check, not a file read). If a residue stays, it is coded at its
  raise, never re-wrapped.
- Rows 27, 37, 17: a WARNING that reports a caught coded error forwards its
  code (ruling 2, R6) through its own WARNING twin, never a second prefix.

### 2.5 Discovery and installed metadata

- `_skip_hatchling_fallback` and `_discover_with_no_static_module` pick a
  line per branch; the uv hint and `(build-and-read failed)` become fields
  or lines, not `%s` tails; `discovery_failure_text` stays the detail.
- `installed._read_marker_text` returns the `OSError` (today `None`,
  `installed.py:77-78`), so rows 46 and 49 can say `failure`.

### 2.6 Dynamic INFO/DEBUG (row L5)

`say_resolved` picks the level from `resolved.decided`
(`_license_resolve.py:219`). INFO goes through `emit(...,
once=f"resolved:{value}")` (same `_WARNED_ONCE` memo as `log_once`,
`_emit.py:57-60`); DEBUG stays `log_once(..., logging.DEBUG, ...)` with the
same key. The memo is per `(logger, key)` and a value's level never
changes, so the pair cannot double-say. Same for row 12 if Q6 codes it
(WARNING through `emit`, DEBUG plain).

### 2.7 Lone surrogates in a licence (row L1)

Not a drop-in for `warn_lone_surrogates` (frames-forward's note): the
licence path writes U+FFFD (`_license_classify.py:89-95`), the
`text-malformed` entry's `did` says `\udXXX`, and the helper needs a
`file`. Add `LICENSE_LINE` (`LICENSE=%(license)s: lone surrogates replaced
with U+FFFD`) and amend `did`; SBOM output unchanged.

### 2.8 Example

`ERROR: loom project: FILE=p/pyproject.toml: project.version: invalid
(<library text>) [metadata-invalid]`, exit 1; the library raises it with
`pitloom_code`; the hook never reads `[project]` itself, but a bad TOML
there says `ERROR: Pitloom build hook: FILE=pyproject.toml: not valid
TOML; ... [config-malformed]`.

## 3. Surfaces

| Rows | CLI | Hook | Library | Action | sdist | wheel/PyPI |
| - | - | - | - | - | - | - |
| 1 to 6, 8 to 12 | yes | no | yes | yes | no | no |
| 7 | yes | yes (Hatchling) | yes | yes | no | no |
| 13 to 16, 19, 20, 27 to 39, 44 to 52, 56 | yes | no | yes | yes | no | no |
| 17, 18, 21 to 23 (Poetry) | yes | yes (`fill_from_poetry`) | yes | yes | no | no |
| 40 to 43 | yes | no | yes (`read_sdist`) | yes | yes | no |
| 53 to 55 | yes | unverified | yes | yes | unverified | no |
| TOML/UTF-8 loader | yes | yes | yes | yes | yes | no |
| L1 to L3, L5 to L7 | yes | yes | yes | yes | yes | yes |
| L4 | yes | unverified | yes | yes | yes | yes |
| L8 | yes | no | yes | yes | no | no |

Entry points read: `__main__.main`, `cli_error_handler`, `plugins/hatch.py`
`initialize` (`log.error` with `code_extra_of`, `:372-377`),
`read_project`, `generate_project_sbom`, `read_sdist`. Tests settle the
"unverified" cells.

Quotes (grep of `skills/`, `docs/`, README; generated pages excluded):

- `skills/sbom-generate/references/known-limitations.md:334-363,386,408-410,435`;
  `examples.md:97-98`; `SKILL.md:81-92` (preflight: add a clause naming
  `license-db-missing`).
- `docs/hatchling-build-hook.md:53`, `docs/github-action.md:40-42`,
  `docs/metadata-provenance-licences.md:160-166,177`; `docs/messages.md`
  gains the relay paragraph (frames-forward ruling 6).
- No skill or doc quotes a PR 12 line (grepped). `--quotes` also matches
  row 52 to the generated `messages-files.md` (it mimics
  `file-unreadable`'s text).
- Regenerate (`python scripts/generate_message_reference.py`): new
  `message-codes-metadata.md`, the skills' `messages-metadata.md`,
  `mkdocs.yml` nav, larger licences pages. Never by hand.

## 4. Rulings for the user (Qn = item n; recommendation in brackets)

1. One PR or two? RULED 2026-11-18 (user): two, PR 18 first. [Two. PR 18 first: 8 sites in 5 source files plus the
   inventory relay rule, about 30 test lines pinning wording; it unblocks
   T14 task 4 and shares only `pyproject.py:228` with PR 12. PR 12 after
   it from fresh `main`: 58 sites in 28 modules, plus about 5 for the
   loader and the hook table, about 190 test lines pinning wording ("file
   discovery" 70, "disagree" 52, installed 41, `Build: ` 29). One PR would
   be the widest catalogue PR yet, against "one family at a time".]
2. Split `metadata-malformed` (syntax) from `file-unreadable` (I/O,
   UTF-8)? [Yes: different advice (decision D); the TOML/INI syntax of
   `pyproject.toml`/`setup.cfg` reuses `config-malformed` so one file's
   syntax error has one code on every route (the hook reads config first,
   the CLI metadata first).]
3. Rows 17, 27, 37 (a WARNING relaying a caught coded error): a WARNING
   twin carrying the inner code? [Yes, R6 and ruling 2.]
4. Drop `Build: ` from rows 1 to 6? [Yes, as frames-forward decided;
   listed in the stderr sweep.]
5. Discovery codes: three (`-unusable`, `-needs-build`, `-conflict`) or
   fold to one? [Three: the advice differs (report a failure; pass
   `--allow-build`; fix the layout).]
6. Row 12, setuptools' stderr relay: uncoded under the same relay shape as
   LicenseID's, or coded? [Relay shape: foreign text; one `_relay.py` rule
   for both, keyed on "module-constant prefix + `one_line(foreign)` in a
   relay function".]
7. `poetry-core` API moved: a `library-unusable` line? [Yes; its advice
   "reinstall" needs a clause "a poetry-core version Pitloom supports".]
8. Dynamic INFO/DEBUG: INFO through `emit`, DEBUG plain (2.6)? [Yes, the
   frames-forward rule.]
9. Row 44 (`pyproject.toml` with only `[build-system]`, a legacy layout)
   is a WARNING for absent data, against "absent source data is quiet".
   [Code it at its level now (no level change in a coding PR); log the
   conflict in the review rounds for a later wording PR.]
10. Row 56 and the two wrappers: prove unreachable and replace with a
    forward or `InternalError`? [Yes, with a probe test.]
11. Row 57 (`_extract_utils.py:261`, a Croissant/PyPI JSON fetch) is not
    project metadata despite the contract. [Move to PR 13 (network: the
    URL case is `download-network-failed`) and PR 17 (an absent dataset
    file); ratchet 154.]
12. Licence expression codes: two (`license-expression-malformed` for a
    syntax failure, `license-expression-invalid` for an operand LicenseID
    reads as no licence), chosen by LicenseID's refusal reason, not by
    which helper fires; the resolver INFO as `license-expression-invalid/
    resolved` (actor none, R1)? [Yes: T14 case 7 wants two `Reason`s
    (`Apache2 OR Foo`, `MIT OR`) and Reason equals the code. Unverified:
    that LicenseID's `reason` separates the two reliably; read its
    categories first.]
13. `licenseid database` missing: own code `license-db-missing` (INFO when
    a licence is declared, WARNING otherwise, today said as `cannot be
    used`), not an `INPUT_KINDS` kind? [Own code: the advice is the
    preflight command; the user named no file.]
14. Licence lone surrogates: a `text-malformed` line saying U+FFFD (2.7)?
    [Yes; no SBOM change.]
15. Index size first (section 6, risk 1). [A small generator PR before
    PR 18 that slims or splits the code table.]

## 5. Tests

Per family `tests/messages/test_metadata.py`,
`test_metadata_discovery.py`, `test_licences.py`, and
`test_metadata_surfaces.py`/`test_licence_surfaces.py` (`platform`:
paths, encodings, archives). Parametrised, short `ids=`.

- One case per boundary through the real reader: each `expected`
  condition per row; the OSError/UnicodeDecodeError/syntax split of rows
  30 and 34 (a directory named `setup.py`, `\xff` bytes, `setup(`); a
  NUL in `setup.py` on 3.10/3.11 (`ValueError`) and 3.12+
  (`SyntaxError`), each its own case (coverage per Python); `failed`
  true/false on row 1; hint present/absent on rows 5 and 6; `quiet`
  silent per `q` row.
- Licence: `MIT OR` (malformed), `Acme-Terms` in `project.license`
  (invalid), `Apache2` (INFO, coded) and `mit` (DEBUG, uncoded, not on
  stderr), the same value twice said once, one value through both
  helpers said once (shared key); several classifiers; database missing
  with and without a declared licence, no home directory; licence plus
  classifiers (L8).
- Canaries: no line with `config file` before `FILE=` or `FILE=` twice
  (sdist, `--config`; fails on base); a newline, `\x1b`, a lone surrogate
  in a licence value, a `build-backend` string and a PDM error (one
  escaped line); `user:pass@` in a licence URL (masked); a TOML error on
  line 3 of a CRLF file says line 3; `PureWindowsPath`
  `C:\p\x.tar.gz:pyproject.toml` into `file_text` (two colons before
  `: `); fail-on-base with `PYTHONPATH` pinned to a 137b2b88 archive.
- Surfaces: CLI line, `[code]`, exit code; hook (`staged_sbom`) for row 7,
  the loader, a Poetry row, L2, L6; library `pitloom_code` from
  `generate_project_sbom` and `read_sdist`; Action through the CLI.
- Drift: the relay rule on both relays and on a planted
  `log.warning("%s", text)` (must count); `READ_USES` liveness; quotes via
  `test_drift_quotes.py`.
- Classify each file (`-m platform --collect-only -q`); `test-all-os`.
- Wording pinned in `tests/` today: "file discovery" 70 lines in 39
  files, "disagree" 52 in 31, installed 41 in 7, `Build: ` 29 in 12,
  "licenseid database" 16 in 6, "config file " 20 in 14. Manual CLI
  checks pin none.
- Mutants: the loader's except order, `failed` in
  `_skip_hatchling_fallback`, the level choice in `say_resolved`, the
  malformed/invalid split, the relay rule, the forward guards,
  `_read_marker_text`'s exception.

Gates (CLAUDE.md): Tier 1 between rounds; Gate A (full suite `-n 4`,
every CI linter, fail-on-base, branch coverage, `--only` manual checks
for `extract/`, `core/`, `plugins/hatch.py`); Gate B (mutation, full
manual run `-j 8`, determinism harness, Windows dry-run, fresh-context
sweep, fresh read of changed skill files). SBOM diff vs `main` empty with
`--creation-datetime` pinned.

## 6. Risks and contradictions

1. **Index near its guard.** `docs/message-codes.md` is 27,566 bytes and
   the skills' `messages.md` 27,259 and 27,215 (generator `MAX_BYTES =
   30_000`, `scripts/generate_message_reference.py:144`); a code row costs
   about 97 bytes. About 20 new codes and variants add about 2 KB:
   29.5 KB after both PRs, and PRs 13 to 17 overflow it. Ruling 15.
2. `setuptools_cfg.py` is 500 lines, `poetry.py` 491, `pyproject.py` 484,
   `_setuptools_options.py` 459: a site rewrite must not grow them; move a
   helper out first where it would.
3. Stacked prefixes today (verified): `No usable project metadata ...
   Could not parse setup.py: ...` (two conditions in one line, row 28) and
   `config file '<sdist>:pyproject.toml': ...` (row 41).
4. The hook reads `[tool.pitloom]` first, the CLI `[project]`: one
   loader, so one code on both.
5. Rows 25, 26 echo backend text raw; in a downloaded clone it can quote a
   file: apply `discovery_failure_text`'s rule.

Contradictions with the older plan docs:

- C1. frames-forward PR 12, `plugins/hatch.py:177`: stale (1.3).
- C2. Migration row 12, "`setuptools_cfg.py` passthrough 1": none there;
  the passthrough is `_models_wheel_setuptools_relay.py:59`.
- C3. Migration row 12, 50 sites: 58 (section 0).
- C4. Migration forward requirements, `_license_text_match.py:97` as an
  `INPUT_KINDS` kind: an own code instead (ruling 13).
- C5. frames-forward PR 18, "`_classify:94` ... call the helper": not a
  drop-in (2.7).
- C6. Migration row 18 and T14 section 8, one `expression-malformed`:
  T14 needs two Reasons (ruling 12).
- C7. Review rounds 122 item 1, `hatch.toml` "replaces `tool.hatch`
  wholesale": Hatchling 1.32.3 `metadata/core.py:243-252` updates per
  top-level key (`build` replaces `tool.hatch.build` only). The fix
  (`FILE=hatch.toml`, `[build.hooks.pitloom]`, at
  `plugins/_hatch_config.py:22`) rides with PR 12; no ratchet site.
- C8. 8-12 plan section 4: `sdist.py:275` is now `:277`;
  `_extract_utils.py:261` is not project metadata (ruling 11).

## 7. Order of steps and agents

0. Opus: rulings; the index PR (ruling 15) if taken.
1. Opus: PR 18 entries, `_fields_metadata.py`, `licences.py` exports, the
   dynamic-level call, the relay-shape rule (`_relay.py`, `_scope.py`).
2. Sonnet: PR 18 sites and tests. Haiku: stale quotes, `%r` in touched
   templates, file sizes.
3. Opus: docs and skill text, generator, `--quotes` before and after,
   `--write-baseline` (219 to 211), CHANGELOG folded into the catalogue
   bullet; Gates A and B.
4. Opus: PR 12 from fresh `main`: entries, topic `metadata`, the loader,
   the forwards, the discovery line choice.
5. Sonnet A `extract/project/`; Sonnet B `core/_models_wheel_*`,
   `config_cascade.py`, `core/project.py`, `deps_installed.py`; Sonnet C
   tests. Each touches only its files; judgement calls go to Opus.
6. Opus: review of every diff, stderr sweep, generator,
   `--write-baseline` (211 to 153), Gates A and B, review-rounds entries.

Never: an exemption by text, a new condition word, a level change, `%r`, a
helper adding a prefix, dropping a said-once memo, a hand-edited generated
file or baseline, a block `pylint: disable`.
