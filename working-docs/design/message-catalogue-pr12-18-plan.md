---
Created: 2026-11-18
Last-Modified: 2026-11-19
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
task 4, unblocked by PR 18).

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

## 4. Rulings for PR 12 (Qn = item n)

Ruled or done: **1** (two PRs, PR 18 first: done, #498). **12** (two
expression codes by LicenseID's category: built, `Refusal.malformed`).
**13** (`license-db-missing` own code: built). **14** (licence surrogates on
`text-malformed`: built, `LICENSE_LINE`).

**Ruled 2026-11-19: every bracketed answer of 2 to 11 below is accepted**
(including 9: a `[build-system]`-only `pyproject.toml` is DEBUG). PR 12a is
merged (#499); PR 12 is on branch `catalogue-metadata`. A build-ready re-check
of this plan against the tree (two line drifts from the flit cast of #500;
ratchet target 154) added five rulings, also accepted 2026-11-19; no
backward compatibility is kept:

- **D1**: a `[project]` that is not a table, or a `name` that is not a
  string, is coded `metadata-invalid` ERROR in `read_pyproject`, beside row 44.
- **D2**: row 28 relays the `setup.py` error as its WARNING twin whenever
  not `quiet`, then raises `project-name-missing` plainly.
- **D3**: row 52 is `metadata-invalid` `FILE=<f>: listed by <field>, not
  found; skipped` (and a `not a file name` line), not `file-unreadable`.
- **D4**: row 17's catch narrows to `ValueError`, pinned by a fuzz test.
- **D5**: rows 18 and 21 both stay (the type, then the consequence).

The "Open" labels below are the questions as asked.

Open (asked 2026-11-18, ruled above):

2. **Reuse `config-malformed` for project `pyproject.toml`/`setup.cfg`
   syntax, split from `file-unreadable` (I/O, UTF-8)?** [Yes.] Evidence:
   the entry already holds `INI_FILE_LINE` for a `setup.cfg` read for
   `[tool:pitloom]` (`setup_cfg_pitloom_config`), so rows 29 to 31 would
   give the same file's syntax error a second code on the metadata read;
   the hook reads `[tool.pitloom]` first (`hatch.py:413`, then
   `_config_parse.py:417`) and the CLI `[project]` first, so one loader
   gives one code on both. `effect` (not-written), `actor` and advice fit;
   the `summary` and `did` (config routes only, "not yet coded") must be
   rewritten (2.1). Advice differs from `file-unreadable` (decision D).
3. **Rows 17, 27, 37: a WARNING twin carrying the inner code?** [Yes, R6
   and pr8-12 ruling 2, by `relay_extra` with an identical template; the
   outcome moves to `did` (2.4).] Evidence: the registry save relays this
   way (`_registry_save_say.py:46-55`); an appended outcome would make the
   text no line of the code, and `relay_extra` returns `None`.
4. **Drop `Build: ` from rows 1 to 6?** [Yes, as frames-forward decided;
   in the stderr sweep. No skill or doc quotes a discovery line.]
5. **Three discovery codes, or one?** [Three: the advice differs (report a
   failure; pass `--allow-build`; fix the layout).]
6. **Row 12: relay shape or coded?** [Relay shape, by reshaping the code
   (2.6), not by widening `_relay.py`: the text is setuptools' own; one
   rule for both relays; the rule stays as mutation-tested.] Evidence: the
   inventory record has `relays: null`, two arguments and `one_line(line)`
   of a loop variable, which `_one_line_param` and `_says_only` refuse.
   Cost: the line loses `<dir>`. Alternative if `<dir>` must stay: widen
   `prefixed` to one leading `quote_source(<param>)` subject argument (a
   rule change with its own counter-examples).
7. **`poetry-core` API moved: `library-unusable`?** [Yes, with a new line
   (`required library API not found: <module>: <error>; ...`) and a clause
   in the summary, which today says "fails to import" only; advice: a
   `poetry-core` release Pitloom supports (`>=2.4.1`).]
8. **Dynamic INFO/DEBUG.** [Settled by PR 18's pattern (1.2); applies in
   PR 12 only if Q6 codes row 12 instead.]
9. **Row 44.** [Split by branch, verified by probe.] `[project]` present
   without `name` (`[project]\nversion = "1"`): a real error PEP 621 refuses,
   today the same WARNING: code it `metadata-invalid` (WARNING, `FILE=`,
   `project.name` missing; read setup.cfg/setup.py). `[project]` absent
   (a `[build-system]`-only legacy setuptools layout, the normal case): absent
   source data, quiet by the design principle, but a level change in a coding
   PR needs a ruling: [lower it to DEBUG, listed in the stderr sweep];
   else code it WARNING `metadata-no-effect` and log the conflict.
10. **Rows 56, 58, 41: prove unreachable, then `InternalError` or a
    forward?** Row 56 [`InternalError`]: unreachable by reading. The only
    writers of `field_conflicts` are `record_setuptools_conflicts` (inside
    `read_setuptools`, `setuptools.py:272`) and
    `reconcile_installed_metadata` (`reader.py:253`, after every merge). The
    two merges' secondaries never hold one: `pyproject.py:409` merges Poetry
    metadata (no writer), `reader.py:96` the `read_pyproject` result
    (`_setuptools_dynamic` merges options without recording). Probe test: a
    structural test that `add_conflict`'s callers are those two, plus a run
    of a legacy layout with `setup.py`/`setup.cfg` and an `.egg-info`
    disagreeing. Row 41 [forward]: REACHABLE today (two probes); after the
    loader twin and the `setup.cfg` decoder, its residue is
    `parse_pitloom_config` and `setup_cfg_pitloom_config` only, the same as
    row 58's. Row 58 [forward, then `InternalError` for an uncoded
    `ValueError`]: the inventory finds no uncoded raise in `core/_config*`
    reachable from a table (`_config_types.py:75` is a parameter check; a
    table read reports through `_require_choice`), but a stdlib
    `ValueError` is invisible to it. Probe test: every `[tool.pitloom]` key
    of the drift table times four bad values (wrong type, NUL, huge int,
    empty) through `load_config_file` and the sdist route, each error coded;
    only then the residue becomes `InternalError`.
11. **Row 57 (`_extract_utils.py:261`) is not project metadata.** [Move
    out; ratchet 154.] Evidence: callers are `extract/dataset/croissant.py:252`
    (raises to the CLI: dataset, PR 17) and `assemble/spdx3/deps_pypi.py:106`
    (swallows the `ValueError`, returns `None`); `extract/remote/_pypi_release.py`
    calls another `fetch_json`. The URL case is `download-network-failed`
    (PR 13 reuses it), the absent file PR 17's.
15. **Index size: BLOCKING.** [Move the values table out of the index into
    one generated page per site, in a small PR before PR 12.] Measured on
    this tree (bytes, `MAX_BYTES = 30_000`,
    `scripts/generate_message_reference.py:144`, guarded by
    `test_every_generated_file_fits_the_size_limit`):

    | File | Bytes | Headroom | Code rows | Values rows |
    | - | - | - | - | - |
    | `docs/message-codes.md` | 29,252 | 748 | 123 rows, 11,995 (97.5 each) | 88 rows, 14,981 (170 each) |
    | `sbom-enrich/references/messages.md` | 28,910 | 1,090 | 11,380 (92.5 each) | 14,981 |
    | `sbom-generate/references/messages.md` | 28,866 | 1,134 | 11,380 | 14,981 |

    PR 12 adds 13 code rows (about 1,270 bytes), 2 page-list lines (about
    115) and 2 to 3 fields (340 to 510): the docs index reaches about 30,900
    to 31,100, over by itself (rows alone: 30,640). PRs 13 to 17 add about
    25 to 30 code rows and variants (migration plan rows 13 to 17) and about
    10 fields: about 35 to 36 KB without a change. The values table is 51%
    of the index and grows faster per entry than the code table. Moved out:
    the index is about 14.3 KB, 15.7 after PR 12, about 19 after PR 17; the
    values page about 15.6 KB, about 18 after PR 17. Rejected: shorter rows
    (dropping `Since` and `Level` saves about 25 bytes a row, 3 KB: one PR's
    worth); an index of pages only (a skill finds a code's page in
    `messages.md`: `known-limitations.md:90`, `pypi-url.md:137`,
    `deterministic-pass.md:24`); raising the limit (CLAUDE.md's file cap).
    Files: `scripts/generate_message_reference.py` (`render` drops
    `_values()`; a `render_values_page`; `expected_pages` lists it so
    `orphans` keeps it; `_PAGE_RULE` and the module docstring say "the
    values page"; it is 533 lines, so move the index and values renderers
    into a sibling module first), `tests/messages/test_generated_reference.py`
    (481 lines: `_RENDERS`, a test that the page lists every used field and
    that no topic is named `values`; a new test file if it nears 500),
    regenerated index, values pages (`message-codes-values.md`,
    `messages-values.md`) and every topic page (the rule text), `mkdocs.yml`
    nav. The frames table (328 bytes) stays in the index. PR 12 then splits
    its codes over two topic pages (2.1): licences runs 2.2 KB a code, so 12
    codes on one page would be 22 to 27 KB, near the guard.

## 5. Tests

New files: `tests/messages/test_metadata.py`,
`test_metadata_discovery.py`, `test_metadata_surfaces.py` (`platform`:
paths, encodings, archives), and a loader test beside `core`'s tests.
Parametrised, short `ids=`. Edited: `tests/test_message_ratchet.py` (four
relays if Q6), `tests/_message_drift.py` (`SAMPLES` for each new field),
`tests/messages/test_config.py` (441 lines: the `config-malformed` twins;
a new file if it nears 500).

- One case per boundary through the real reader: each condition per row;
  the OSError/UnicodeDecodeError/syntax split of rows 30 and 34 (a
  directory named `setup.py`, `\xff` bytes, `setup(`); a NUL in `setup.py`
  on 3.10/3.11 (`ValueError`) and 3.12+ (`SyntaxError`), each its own case;
  `failed` true/false on row 1; hint present/absent on rows 5 and 6; both
  branches of row 44; `quiet` silent per `q` row; row 39 said once.
- Canaries: no line with `config file` before `FILE=` or `FILE=` twice
  (sdist TOML, sdist non-UTF-8 `setup.cfg`, `--config`; each fails on
  base); a newline, `\x1b`, a lone surrogate in a `build-backend` string
  and a PDM error (one escaped line); `user:pass@` in a backend error
  (masked); a TOML error on line 3 of a CRLF file says line 3;
  `PureWindowsPath` `C:\p\x.tar.gz:pyproject.toml` into the file field (two
  colons before `: `); fail-on-base with `PYTHONPATH` pinned to a c4674613
  archive.
- Surfaces: CLI line, `[code]`, exit code; hook (`staged_sbom`) for row 7,
  the loader, a Poetry row; `loom fragment` for the loader; library
  `pitloom_code` from `generate_project_sbom` and `read_sdist`; Action
  through the CLI.
- Drift: the relay rule on both relays (and row 12's reshaped one) and on a
  planted `log.warning("%s", text)` (must count); `READ_USES` liveness;
  quotes via `test_drift_quotes.py`; a `relay_extra` twin for every inner
  code rows 17, 27, 37 can relay.
- Q10 probes: `add_conflict` callers; the config key times bad value sweep.
- Classify each file (`-m platform --collect-only -q`); `test-all-os`.
- Wording pinned in `tests/` today (re-counted): "file discovery" 70 lines
  in 39 files, "disagree" 52 in 31, installed 42 in 7, `Build: ` 29 in 12,
  "config file " 20 in 14, "Failed to parse project metadata" 6 in 2,
  "Could not parse setup" 7 in 3, "setuptools stderr" 7 in 4. Manual CLI
  checks pin none.
- Mutants: the loader's except order, `failed` in
  `_skip_hatchling_fallback`, the row 44 branch, the forward guards,
  `_read_marker_text`'s exception, the reshaped relay.

Gates (CLAUDE.md): Tier 1 between rounds; Gate A (full suite `-n 4`,
every CI linter, fail-on-base, branch coverage, `--only` manual checks for
`extract/`, `core/`, `plugins/hatch.py`); Gate B (mutation, full manual run
`-j 8`, determinism harness, Windows dry-run, fresh-context sweep, fresh
read of changed skill files). SBOM diff vs `main` empty with
`--creation-datetime` pinned.

## 6. Risks and contradictions

1. **Index over the guard** (ruling 15): measured, blocking.
2. File sizes a rewrite touches (lines; soft ceiling 500): within 60 of it
   or over: `setuptools_cfg.py` 500, `poetry.py` 491, `deps_installed.py`
   489, `pyproject.py` 480, `core/_config_parse.py` 469,
   `_setuptools_options.py` 459, `messages/_fields.py` 453,
   `plugins/hatch.py` 538 (over; touched only if the hook needs a line),
   `scripts/generate_message_reference.py` 533 (ruling 15 PR). None over
   800. A site rewrite must not grow them; move a helper out first.
3. Stacked prefixes today (verified): `No usable project metadata ...
   Could not parse setup.py: ...` (row 28) and `config file
   '<sdist>:<member>': ...` (row 41, both members).
4. Rows 25, 26 echo backend text raw; in a downloaded clone it can quote a
   file or a URL: `masked_free_text`.
5. Row 17 catches `KeyError`; its source is unread.

Contradictions with the older plan docs (each re-checked):

- C1. frames-forward PR 12, `plugins/hatch.py:177`: stale; the call is
  `:176`, and it is no discovery line (1.3).
- C2. Migration row 12, "`setuptools_cfg.py` passthrough 1": none there;
  the passthrough is `_models_wheel_setuptools_relay.py:59`.
- C3. Migration row 12, 50 sites: 58 (section 0).
- C4 to C6 (PR 18: `licenseid database` as an `INPUT_KINDS` kind, the
  surrogate helper as a drop-in, one `expression-malformed`): resolved by
  rulings 12 to 14 as built in #498.
- C7. Review rounds (PRs 8 and 9 second review, item 1): `hatch.toml`
  "lets a `hatch.toml` replace `tool.hatch` wholesale" is false. Read in
  Hatchling 1.32.3 (`.venv`, `hatchling/metadata/core.py:231-254`,
  `ProjectMetadata.hatch`): `hatch_config = tool.hatch.copy();
  hatch_config.update(load_toml(hatch.toml))`, a shallow update per
  top-level key. A `hatch.toml` with `[build]` replaces all of
  `tool.hatch.build` (hooks included); `version`, `metadata` and the other
  keys of `tool.hatch` survive. So the hook table's source is knowable: from
  `hatch.toml` when it has a top-level `build` key, else `pyproject.toml`.
  The fix (`FILE=hatch.toml`, `[build.hooks.pitloom]`;
  `plugins/_hatch_config.py:22`) is no ratchet site; it may ride with PR 12
  as its own commit. Not read: Hatchling 1.29.0 (the floor).
- C8. 8-12 plan section 4: `sdist.py:275` is now `:277`;
  `_extract_utils.py:261` is not project metadata (Q11).
- C9. pr8-12 ruling 4 gave `_poetry_requirements.py` to PR 11; its row 23
  is still uncoded and is PR 12's.
- C10. The earlier version of this plan: "5 callers" of row 7 (6 calls);
  `cli/options_resolve.py:282` as a load site (it swallows); Q10's "the
  wrappers' residue is unreachable" (row 41 is reached today); the loader
  in `pitloom.core` "unverified for cycles" stands, now beside
  `config_cascade`.

## 7. Order of steps and agents

PR 18 (steps 1 to 3 of the earlier order): done, #498.

**PR 12a, the index split (ruling 15), from fresh `main`, before PR 12:**

0. Opus: rulings 2 to 11 and 15 with the user.
1. BUILT 2026-11-19 (branch `catalogue-index`): the values page
   (`message-codes-values.md`, `messages-values.md`), `expected_pages`, the
   rule text, `mkdocs.yml` nav, `tests/messages/test_generated_values_page.py`.
   Not split into a sibling module (about 575 lines): the two tests that
   load it by path would first need `scripts/` on `sys.path`; noted in the
   complexity roadmap. Index 29,252 to 14,338 bytes, values page 15,589.
2. Opus: review; Gate A (generator tests, `--check`, linters on
   `scripts/` and `tests/`); no src change, ratchet unchanged.

**PR 12, from `main` after 12a merges:**

3. Opus: entries (`_metadata*.py`, two topics, `dependency-pin-conflict`),
   `_fields_metadata.py`, the shared twin helper, `config-malformed`
   rewrite and twins, `file-unreadable` use, `library-unusable` line, the
   loader `core/_project_toml.py` with `load_config_file` on it, the forward
   decisions, the discovery line choice, row 12's reshape.
4. Sonnet A `extract/project/` (rows 13 to 52); Sonnet B
   `core/_models_wheel_*`, `config_cascade.py`, `core/project.py`,
   `deps_installed.py`, `sdist.py` wrapper (rows 1 to 12, 53 to 58);
   Sonnet C tests (section 5). Each touches only its files, fenced in
   writing; judgement calls go to Opus.
5. Haiku: stale quotes, `%r` in touched templates, file sizes, `SAMPLES`.
6. Opus: review of every diff, stderr sweep (`Build: ` dropped, row 44,
   row 12's `<dir>`), generator, `--write-baseline` (211 to 153 or 154),
   CHANGELOG folded into the catalogue bullet, Gates A and B, review-rounds
   entries (C7 corrected there too).

Never: an exemption by text, a new condition word, an unruled level change,
`%r`, a helper adding a prefix, dropping a said-once memo, a hand-edited
generated file or baseline, a block `pylint: disable`.
