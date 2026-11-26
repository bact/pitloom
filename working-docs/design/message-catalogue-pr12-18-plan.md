---
Created: 2026-11-18
Last-Modified: 2026-11-26
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
(rows 12 to 18, R1 to R7),
[message-frames-forward.md](message-frames-forward.md) ("PR 12", "PR 18",
the dynamic-level rule, "Cross-PR interfaces"),
[message-catalogue-review-rounds.md](../implementation/message-catalogue-review-rounds.md)
(the PRs 8 and 9 out-of-scope items),
[licence-resolution-provenance.md](licence-resolution-provenance.md) (T14
task 4, unblocked by PR 18),
[message-catalogue-pr12-18-rulings.md](message-catalogue-pr12-18-rulings.md)
(sections 4 to 7: rulings Q1 to Q11, tests, risks, order of steps; split
out for size).

Status: PR 18 BUILT and merged (#498, 2026-11-18); PR 12a merged (#499,
2026-11-19); PR 12 BUILT and reviewed on `catalogue-metadata` (#501, ratchet
211 to 154, row 57 left for PR 17; review findings in
[message-catalogue-review-rounds.md](../implementation/message-catalogue-review-rounds.md),
round 3). PR 12 plan refreshed
2026-11-18 on c4674613 (the tree of `main` 9b1454da, the #498 merge).
Sites from `message_inventory --jsonl`, `_scope.in_scope` and not `coded`,
each read in the source. "Verified" means read or run; CLI probes run with
`PYTHONPATH` on this tree: an sdist with bad TOML, an sdist with a non-UTF-8
`setup.cfg`, a project with bad TOML, a non-UTF-8 `pyproject.toml`, a
`[project]` with no `name`, a `[build-system]`-only `pyproject.toml`.

## 0. Counts

The ratchet holds **211** uncoded sites (`--check` passes; the baseline's
module counts sum to 211). PR 18 took 219 to 211. All **58** PR 12 rows of
the 2026-11-18 list still exist (none dropped, none new); five moved lines
(`pyproject.py` 164, 210, 248, 253, 469 are now 166, 212, 244, 249, 465).
`pyproject.py:228` was PR 18's L8 (coded `license-conflict`, now `:230`).
Still in the families' modules and not PR 12's: `_models_wheel_dispatch.py:198`
(`--allow-build`, PR 14), `_sdist_scan.py:184` (registry key, PR 16) and the
`_models_wheel_build_*` lines (PR 14).

Ratchet after PR 12: **211 to 153** (154 if Q11 moves
`_extract_utils.py:261` out). Row 12 leaves the count by relay shape (Q6),
not by a code.

Not a site, still in scope (verified): a project `pyproject.toml` that is
not TOML or not UTF-8 escapes raw: `ERROR: loom generate: Invalid value (at
line 3, column 11)` and `ERROR: loom generate: 'utf-8' codec can't decode
byte 0xff ...`, no `FILE=`, no code. Raising loads: `extract/project/pyproject.py:283`,
`reader.py:91`, `hatchling.py:60` (hook, Poetry fallback),
`core/_config_parse.py:417` (`read_pitloom_config`: the hook,
`plugins/hatch.py:413`, and `loom fragment`, `cli/commands/fragment.py:292`),
`sdist.py:350,396` (inside `_member_config`), `sdist.py:164,260` (WARNING
sites: row 40, the authors route). Not raising: `cli/options_resolve.py:282`
swallows every exception (`--verbose` source map), and
`setuptools.py:118` logs at DEBUG (1.3).

## 1. Sites

Routes: P project directory (CLI, library `generate_project_sbom`,
`read_project`; Action through the CLI), H Hatchling hook, S sdist
archive. `q` = silent when `quiet`. Text abridged.

### 1.1 PR 12: project metadata (58)

| # | Site | Lvl | Text today | Code | Route |
| - | - | - | - | - | - |
| 1 | `core/_models_wheel_dispatch.py:100` | W | `Build: <cause> in <dir> -- falling back to Hatchling-based heuristic` | by `failed`: `file-discovery-unusable` or `-needs-build` | P |
| 2, 3 | `:112,122` | W | `Build: <backend>'s static config failed introspection ...` / `Build: File discovery failed (above) ...` | `file-discovery-unusable` | P |
| 4 | `:129` | W | `Build: No static <backend> config ... imperative setup.py build` | `file-discovery-needs-build` | P |
| 5, 6 | `:255,265` | W | `Build: file discovery for build backend %r is not yet backend-aware ...` | `file-discovery-needs-build` | P |
| 7 | `core/_models_wheel_types.py:81` (6 calls, 5 modules) | W | `<Backend> file discovery failed for <dir>: <text>` | `file-discovery-unusable` | P, H |
| 8 | `core/_models_wheel_setuptools.py:268` | W | `<dir>: both A and B resolve to the same wheel path P -- keeping A, dropping B` | `file-discovery-conflict` | P |
| 9 | `:345` | W | `setup.py in <dir> passes K imperatively -- ...` | `file-discovery-needs-build` | P |
| 10 | `:406` | W | `<dir>: setuptools could not auto-discover packages unambiguously` | `file-discovery-unusable` | P |
| 11 | `core/_models_wheel_flit.py:70` | W | `<dir>: could not resolve a static version for [tool.flit.external-data]` | `file-discovery-needs-build` | P |
| 12 | `core/_models_wheel_setuptools_relay.py:59` | W/D | `<dir>: setuptools stderr: <line>` | relay shape, uncoded (Q6) | P |
| 13 | `extract/project/pyproject.py:166` | E | `Failed to parse project metadata: 'project.K' <reason>` | `metadata-invalid` | P |
| 14-16 | `:212,244,249` | E | `Failed to parse project metadata: <pyproject-metadata text>` | `metadata-invalid` | P |
| 17 | `:465` | W | `<dir>: [tool.poetry] metadata could not be parsed (<exc>) -- ...` | inner code, WARNING twin (Q3); catches `KeyError` too | P |
| 18 | `poetry.py:160` | E | `[tool.poetry] in pyproject.toml is not a table` | `metadata-invalid` | P, H |
| 19, 20 | `:162,174` | E | `[tool.poetry] section not found` / `Project name is required ...` | `project-name-missing` | P |
| 21 | `_poetry_fields.py:105` | W | `<file>: <where> is <T>, expected <T2> -- ignoring it` | `metadata-invalid` | P, H |
| 22 | `_poetry_extras.py:179` | W | `Ignoring <what>: <reason>` | `metadata-no-effect` | P, H |
| 23 | `_poetry_requirements.py:89` | W | `poetry-core: API not found (<exc>); ...` | `library-unusable` (Q7) | P, H |
| 24 | `pdm.py:112` | W | `PDM dynamic version source %r ... not resolvable without executing project code` | `dynamic-field-needs-build` | P |
| 25, 26 | `pdm.py:175`, `flit.py:101` | W | `PDM`/`Flit dynamic ... resolution failed for <p>: <exc>` (raw `exc`) | `dynamic-field-unusable` | P |
| 27 | `setuptools.py:236` | W | `<dir>: <setup.py error> -- reading setup.cfg alone` | row 34's code, WARNING twin (Q3) | P |
| 28 | `setuptools.py:267` | E | `No usable project metadata found in <dir>. ...<setup.py error>` | `project-name-missing` | P |
| 29, 31 | `setuptools_cfg.py:269,292` | E | `Could not parse setup.cfg: <file> <where>: <reason>; ...` | `config-malformed` | P |
| 30 | `setuptools_cfg.py:271` | E | `Could not parse setup.cfg: <exc>` (OSError, UnicodeDecodeError, `configparser.Error`) | `file-unreadable[/not-utf8]` or `config-malformed` | P |
| 32 | `setuptools_cfg.py:323` | E | `Project name is required in setup.cfg [metadata] section` | `project-name-missing` | P |
| 33 | `setuptools_py.py:106` | W | `setup.py: %r <reason> -- treating it as undeclared ...` | `metadata-invalid` | P |
| 34 | `setuptools_py.py:287` | E | `Could not parse setup.py: <exc>` (OSError, SyntaxError, ValueError, RecursionError, MemoryError) | `file-unreadable` or `metadata-malformed` | P |
| 35 | `setuptools_py.py:311` | E | `Could not extract project name from setup.py. ...` | `project-name-missing` | P |
| 36 | `_setuptools_dynamic.py:172` | W | `pyproject.toml: '<key>' <reason> -- ignoring it` | `metadata-invalid` | P |
| 37 | `_setuptools_dynamic.py:241` | W | `pyproject.toml: dynamic <fields> not read from <file>: <exc>` | inner code, WARNING twin (Q3) | P |
| 38 | `_setuptools_options.py:394` | W | `<subject>: setup.py and setup.cfg disagree on K ... -- keeping X's` | `metadata-conflict` | P |
| 39 | `_setup_cfg_directives.py:295` | W | `FILE=<f>: RecursionError parsing the <attr> line; skipped ...` (`warn_once`) | `metadata-malformed`, said once | P |
| 40 | `sdist.py:166` | W | `Failed to parse pyproject.toml from sdist member: <sdist>: <exc>` | `config-malformed` WARNING or `file-unreadable/not-utf8` | S |
| 41 | `sdist.py:277` | E | `config file '<sdist>:<member>': <exc>` (reached by bad TOML and by a non-UTF-8 `setup.cfg`, verified) | forward (2.4) | S |
| 42 | `_sdist_pyproject.py:36` | W | `<sdist>:pyproject.toml: %r is <T>, expected <T2> -- ignoring it` | `metadata-invalid` | S |
| 43 | `_sdist_pyproject.py:138` | W | `<sdist>:pyproject.toml: dynamic field(s) not resolved without PKG-INFO` | `dynamic-field-needs-build` | S |
| 44 | `reader.py:76` | W | `<file> has no usable [project] table ... -- falling back to setup.cfg/setup.py` | split by branch (Q9) | P |
| 45, 47 | `installed.py:115,138` | W | `<label> exists but has no <marker>` / `declares name N, which does not match ...` | `installed-metadata-unusable` | P |
| 46, 49 | `installed.py:125,319` | W | `<marker> could not be read` / `could not be re-read` | `file-unreadable` (2.5) | P |
| 48 | `installed.py:197` | W | `multiple installed-metadata candidates found (...) -- using X` | `installed-metadata-ambiguous` | P |
| 50 | `_installed_reconcile.py:107` | W | `<subject> disagrees on K (declared %r, installed %r) -- keeping declared` | `metadata-conflict` | P |
| 51 | `_requirements_files.py:253` | W | `<config>: skipping pip option line(s) ...` | `metadata-no-effect` | P |
| 52 | `_requirements_files.py:356` | W | `FILE=<f>: could not read for <field>; not found` (an absent listed file, or a NUL in its name) | `metadata-invalid` | P |
| 53, 55 | `assemble/spdx3/deps_installed.py:341,363` | W | `Locked version %r for dependency %r conflicts with declared exact pin` / `does not satisfy` | `dependency-pin-conflict` | P |
| 54 | `deps_installed.py:354` | W | `Dependency %r declared as %r couldn't be parsed -- ... using it anyway` | `requirement-invalid` | P |
| 56 | `core/project.py:394` | W | `merge_project_metadata: both sides have a field_conflicts entry ...` | `InternalError` (Q10) | - |
| 57 | `extract/_extract_utils.py:261` | E | `Cannot read <subject> <where>: <why>` (URL or absent file) | out (Q11) | - |
| 58 | `core/config_cascade.py:237` | E | `config file '<p>': <exc>` (uncoded residue) | forward (2.4, Q10) | P, library |

12 discovery rows, 46 reader rows; rows 41 and 58 vanish by forwarding,
row 12 by relay shape, row 56 by `InternalError`.

### 1.2 PR 18: licences -- DONE (#498)

All 8 sites coded (L1 to L8 of the earlier list): `license-expression-malformed`,
`license-expression-invalid` (+ `/resolved`, INFO, actor none),
`license-ambiguous`, `license-conflict`, `license-db-missing` (INFO or
WARNING), `license-db-unusable`, and a `LICENSE=` line on `text-malformed`.
The `licenseid: ` relay is out of the count by the `prefixed` relay shape.

**What PR 18 settled, which PR 12 reuses:**

- *Entries*: one module per family (`_license_expression.py` 210 lines,
  `_license_db.py` 93), exported by the topic module (`licences.py`);
  helpers in a `_say` module (`_license_say.py` 91) that bind `line=` and
  `extra=` by name so no value can take their place; `_SINCE: Final =
  "0.25.0"` per module (last tag still `v0.24.0`: PR 12 uses 0.25.0 unless a
  tag is cut first; check `git tag`).
- *Fields*: a family table (`_fields_licence.py`, `LICENCE_FIELDS`) merged in
  `_fields.py` by one import and one tuple entry (`_fields.py` now 453
  lines). Foreign text that may name a URL is written by `masked_free_text`
  (`free_text(masked_text(plain_text(v)))`); a value read from a file by
  `excerpt_text`. Each new field gets a `SAMPLES` entry in
  `tests/_message_drift.py`.
- *Said once*: `emit(log, M, level, once=<key>, ...)` goes through
  `log_once`'s memo; the caller keeps the key, so one value said through two
  helpers is said once. A dynamic INFO/DEBUG line: INFO coded through `emit`,
  DEBUG the same rendered text through `log_once(..., logging.DEBUG, once,
  "%s", line.render(values))`, no code (`say_license_resolved`).
- *Relay shape*: `prefixed` in `scripts/message_inventory/_relay.py`: a
  module constant bound once to a string, `+ "%s"`, one argument
  `one_line(<param>)` where `<param>` is a parameter of the saying function
  (not a loop variable), no keyword. `tests/test_message_ratchet.py` pins
  exactly three relays (`test_the_three_relays_say_no_text_of_their_own`);
  `tests/scripts/message_inventory/test_relay_prefixed.py` (206 lines)
  holds the shape's counter-examples.
- *Split by the reader's own category*: `Refusal(reason, malformed)`
  (`extract/_license_resolve.py:195`) carries LicenseID's category so the
  code is chosen by cause, not by which helper fires.
- *Tests and drift*: `tests/messages/test_licences.py` (entries, said once,
  mutants), `test_licence_surfaces.py` (`platform`), quotes in
  `test_drift_quotes.py`; regenerated pages, never by hand.
- *`text-malformed`*: `LICENSE_LINE` (`LICENSE=%(license)s: lone surrogates
  replaced with U+FFFD`) and an amended `did`; a new subject is a new line
  on the shipped entry, not a new code.

### 1.3 Found while re-reading (not in scope; for the roadmap or the owning PR)

- `plugins/hatch.py:86,97,388,394,404,465,512`: PR 14 or 16 (`:465` still
  says `Pitloom: ` despite frames-forward ruling 1). The hook reaches row 7
  via `get_wheel_files(assume_backend="hatchling")` (`:176`,
  `_models_wheel_hatchling.py:154`); the six dispatch rows are skipped
  (`_models_wheel_dispatch.py:390`).
- `extract/_author_warnings.py:168` (`<sdist>:pyproject.toml: project
  metadata not read (<exc>)`): PR 17's file; PR 12 adds the WARNING twin of
  `TOML_LINE`, PR 17 switches to it.
- `extract/env.py:92,96` (pipdeptree): no owning row; final sweep.
- `extract/project/setuptools.py:118` (`read_pyproject_toml`) catches
  `(OSError, TOMLDecodeError)` but not `UnicodeDecodeError`; reached only
  after the metadata read (which fails first), so latent.
- `extract/project/installed.py:112` uses `marker_path.exists()`
  (`PermissionError` propagates on 3.10 to 3.13; CLAUDE.md pattern).
- `extract/project/_poetry_requirements.py:74`: a block `# pylint:
  disable=import-outside-toplevel` (CLAUDE.md wants `disable-next`).
- Row 23's owner: pr8-12 ruling 4 gave `_poetry_requirements.py` to PR 11,
  which left the line uncoded; PR 12 takes it (C9).

## 2. Design

### 2.1 Codes (all `since` 0.25.0)

New, `pitloom.messages.metadata` (entries in `_metadata*.py` modules, one
per family, as `_license_expression.py`). Two topic pages, not one (ruling
15): `metadata` ("Project metadata", 9 codes) and `file-discovery` ("File
discovery", 3 codes); `dependency-pin-conflict` joins `dependencies`.

| Code | Topic | Cond. | Levels | Actor / effect | Advice (short) |
| - | - | - | - | - | - |
| `metadata-malformed` | metadata | malformed | E, W | user / not-written (E), thinner (W) | Fix the file's syntax where the line says (`setup.py` is Python). |
| `metadata-invalid` | metadata | invalid | E, W | user / not-written, thinner | The value named is refused (E) or ignored (W); fix it in the file. |
| `metadata-no-effect` | metadata | no-effect | W | user / none | The table or line is not read by this backend; move or drop it. |
| `metadata-conflict` | metadata | conflict | W | user / weaker | The grid: `kept X, dropped Y`; the SBOM states X. |
| `project-name-missing` | metadata | missing | E, W | user / not-written | Declare `name` (literal in `setup.py`). W: the twin row 17 relays. |
| `dynamic-field-needs-build` | metadata | needs-build | W | user / thinner | Only the build knows the field; `PKG-INFO` or a built wheel has it. |
| `dynamic-field-unusable` | metadata | unusable | W | user / thinner | The backend's resolver failed (detail); report it. |
| `installed-metadata-unusable` | metadata | unusable | W | user / thinner | A `.dist-info`/`.egg-info` that is broken or another project's. |
| `installed-metadata-ambiguous` | metadata | ambiguous | W | user / weaker | Several candidates; the line names the one used. |
| `file-discovery-unusable` | file-discovery | unusable | W | user / thinner | Discovery failed; `--allow-build` gives the exact list (runs build code). |
| `file-discovery-needs-build` | file-discovery | needs-build | W | user / weaker or thinner | Static reading cannot see the list; `--allow-build` (trust first). |
| `file-discovery-conflict` | file-discovery | conflict | W | user / thinner | Two files, one wheel path: the grid. |
| `dependency-pin-conflict` | dependencies | conflict | W | user / weaker | Lock and declared pin disagree: the grid. |

Every advice ends with `ASK_FIRST`. No new condition word, no variant.

Reused:

- `config-malformed` for the TOML and INI syntax of a project's
  `pyproject.toml` and `setup.cfg` on every route (Q2), plus WARNING twins
  of `TOML_LINE` and `INI_FILE_LINE` (row 40, rows 27 and 37 relaying a
  `setup.cfg` failure, the authors route). Rewrite its `summary` (today:
  "A configuration file is not valid TOML (a --config file) or INI (a
  setup.cfg) ... A project's or an sdist's pyproject.toml that is not valid
  TOML is not yet coded", `messages/_config.py:200-204`) and `did` (today
  names only config routes and "Read no setting"): "Read no setting and no
  project metadata".
- `file-unreadable` with a new `READ_USES` entry `for the project metadata`
  (rows 30, 34, 46, 49, the loader).
- `library-unusable` (row 23, a line naming the API moved, Q7),
  `requirement-invalid` (row 54).
- The twin helper: `_warning_twins` is private to `messages/_registry_file.py:62`;
  promote it to one shared helper (`messages/_types.py` or a small module)
  before a second family copies it.

### 2.2 Fields

New fields go in `messages/_fields_metadata.py` (`METADATA_FIELDS`, merged
in `_fields.py` as `LICENCE_FIELDS` is; `_fields.py` 453 to about 455):
`backend` (declared `build-backend`, untrusted: `quoted_text`), `kwargs`
(joined), and the discovery hint if it becomes a field (2.5). Reused:
`file`, `dir`, `field`, `failure`, `kept`, `dropped`, `package`, `version`,
`value`, `reason`, `outcome`, `requirement`, `key`. A backend error text
(rows 25, 26) is foreign: `masked_free_text`, as PR 18 writes LicenseID's
reason.

### 2.3 Subjects and the `Build: ` prefix

- Subject first (frames-forward rule 1): `DIR=` for directory lines,
  `FILE=` for file lines, `PACKAGE=` (53 to 55).
- `Build: ` leaves rows 1 to 6 (decided; in the stderr sweep);
  `BUILD_LOG_PREFIX` stays for `:198` and the `_models_wheel_build_*` lines
  until PR 14. The lead-ins `setup.py: `, `pyproject.toml: `, `PDM`,
  `Flit`, `poetry-core: `, `merge_project_metadata: ` go.
- No `%r`, no raw `exc` (rows 17, 25, 26, 37 print an exception raw today;
  row 17 also catches a `KeyError`, printed as `'name'`).

### 2.4 Files that do not parse; wrappers

- One loader, `load_project_toml(path, *, use)` in a new
  `pitloom/core/_project_toml.py` (beside `config_cascade`, which already
  imports `pitloom.messages`; live import test both orders):
  `TOMLDecodeError` and the `(ValueError, RecursionError)` residue to
  `config-malformed` `TOML_LINE`, `UnicodeDecodeError`/`OSError` to
  `file-unreadable` with *use*, absent to `input-not-found`.
  `config_cascade.load_config_file` (`:214-231`, the same except chain)
  calls it with `CONFIG_USE`, so the chain exists once. `pitloom/_toml_io.py`
  stays raw (its docstring leaves exception policy to callers). The raising
  loads of section 0 call it; the sdist twin takes bytes and names
  `FILE=<sdist>:pyproject.toml`.
- The sdist `setup.cfg` is decoded raw too (`sdist.py:304`,
  `raw.decode("utf-8")` inside `_member_config`): a non-UTF-8 member says
  `config file '<sdist>:setup.cfg': 'utf-8' codec can't decode ...`
  (verified). The twin decoder covers it (`file-unreadable/not-utf8`).
- Wrappers keep the inner code (frames-forward "Cross-PR interfaces").
  `sdist.py:_member_config` (`:269-279`) and `config_cascade.py:233-237`
  drop the prefix-adding branch once their residue is unreachable (Q10). If
  a residue stays, it is coded at its raise, never re-wrapped.
- Rows 17, 27, 37 (a WARNING relaying a caught coded error): R6, the
  shipped `relay_extra` mechanism (`_registry_save_say.py` is the
  precedent): the text is the inner line's, said at WARNING, so the inner
  entry needs a WARNING twin of the identical template, and the outcome
  ("reading setup.cfg alone") moves to the entry's `did` ("As a WARNING,
  ..."). A missing twin raises `InternalError`, never prints uncoded. The
  inner `KeyError` of row 17 is coded at its raise or proven unreachable.

### 2.5 Discovery and installed metadata

- `_skip_hatchling_fallback` and `_discover_with_no_static_module` pick a
  line per branch; the uv hint and `(build-and-read failed)` become fields
  or lines, not `%s` tails; `discovery_failure_text` stays the detail.
- `installed._read_marker_text` returns the `OSError` (today `None`,
  `installed.py:77-78`), so rows 46 and 49 can say `failure`.
- Row 39 keeps its `warn_once` memo through `emit(once=)`.

### 2.6 Row 12, setuptools' stderr

Today `log.log(WARNING if error else DEBUG, "%s: setuptools stderr: %s",
source, one_line(line))` inside a loop: two arguments and a loop variable,
so it does not fit the `prefixed` shape (verified: inventory `relays` is
`null`). To fit (Q6): a module constant `_PREFIX = "setuptools stderr: "`
and a one-call helper `_say(line: str, level: int)` whose parameter is the
line: `log.log(level, _PREFIX + "%s", one_line(line))`. The directory goes
(one project per discovery; the discovery lines name `DIR=`). The DEBUG
half and the two other DEBUG lines (`:66`, `:119`) are out of scope. The
ratchet test then pins four relays.

### 2.7 Example

`ERROR: loom project: FILE=p/pyproject.toml: project.version: invalid
(<library text>) [metadata-invalid]`, exit 1; the library raises it with
`pitloom_code`. The hook never reads `[project]` itself, but a bad TOML
there says
`ERROR: Pitloom build hook: FILE=pyproject.toml: not valid TOML; <failure> [config-malformed]`
(today: `ERROR: Pitloom build hook: Invalid
value ...`, by reading `plugins/hatch.py:367-377`, not run).

## 3. Surfaces

| Rows | CLI | Hook | Library | Action | sdist | `loom fragment` |
| - | - | - | - | - | - | - |
| 1 to 6, 8 to 12 | yes | no | yes | yes | no | no |
| 7 | yes | yes (Hatchling) | yes | yes | no | no |
| 13 to 16, 19, 20, 27 to 39, 44 to 52 | yes | no | yes | yes | no | no |
| 17, 18, 21 to 23 (Poetry) | yes | yes (`fill_from_poetry`) | yes | yes | no | no |
| 40 to 43 | yes | no | yes (`read_sdist`) | yes | yes | no |
| 53 to 55 | yes | no (build stage reads no lock; reasoned) | yes | yes | unverified | no |
| the loader | yes | yes (`read_pitloom_config`) | yes | yes | yes (twin) | yes (`fragment.py:292`) |

Entry points read: `__main__.main`, `cli_error_handler`, `plugins/hatch.py`
`initialize` (`log.error` with `code_extra_of`, `:367-377`),
`read_project`, `generate_project_sbom`, `read_sdist`,
`cli/commands/fragment.py`. Tests settle the "unverified" and "reasoned"
cells.

Quotes (grep of `skills/`, `docs/`, README; generated pages excluded): no
skill or doc quotes a PR 12 line. Every `Build: ` quote
(`build-timeout.md`, `git-url.md`, `docs/allow-build.md`,
`docs/git-urls.md`) is a PR 14 build line; `sbom-generate/SKILL.md:278`
("`Build: ...` lines from an `--allow-build` run") stays true once
discovery drops the prefix. `--quotes` matches row 52 to the generated
`messages-files.md` (it mimics `file-unreadable`'s text). Regenerate
(`python scripts/generate_message_reference.py`): new
`message-codes-metadata.md`, `message-codes-file-discovery.md` and the
skills' twins, larger `config`, `files`, `dependencies` pages; `mkdocs.yml`
nav is hand-written (two lines).

## 4. to 7. Rulings, tests, risks, steps

Moved to
[message-catalogue-pr12-18-rulings.md](message-catalogue-pr12-18-rulings.md).
