---
Created: 2026-11-17
Last-Modified: 2026-11-17
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message catalogue PRs 8 and 9: configuration

See also: [message-catalogue-pr8-12-plan.md](message-catalogue-pr8-12-plan.md)
(rulings 1 to 4, what a plan holds),
[message-catalogue-migration-plan.md](message-catalogue-migration-plan.md)
(rows 8 and 9, R3), [message-catalogue-pr6-pr7-plan.md](message-catalogue-pr6-pr7-plan.md),
[message-catalogue-review-rounds.md](../implementation/message-catalogue-review-rounds.md),
[message-catalogue-pr10-11-lock-plan.md](message-catalogue-pr10-11-lock-plan.md)
(the sibling plan; coordination in Q3).

Status: plan, 2026-11-17, `main` 654d734e. Families 8 and 9 are ONE PR
(the 8 to 12 plan, section 1), merged after 10 and 11. Sites from
`message_inventory --jsonl` (`in_scope`, not `coded`), read in the source;
"verified" means read or run (session probes `cfg-probe1.py`,
`cfg-probe2.py`); "unverified" is marked.

## 0. Counts

The plan's 46 and 14 are the classifier's. Measured: **33** config-invalid
sites (28 in `core/_config_*` and `plugins/_hatch_config.py`, 5 in shared
validators), **14** for family 9 as recommended (12 if Q5 says no; 15 if Q6
takes `file_names.py:92`), **4** orphans. The plan's other sites are coded
(`credential_policy.py`, #487) or not config (`iri.py`,
`_models_wheel_types.py`). Ratchet **316 to 265** as recommended.

Four user-reachable config errors are out of the ratchet through a text
pattern (coding them moves no count): `_config_read.py:91` (`^\{name\} must
be a table` in `INTERNAL_PAT`; `[tool] pitloom = 5`), `core/creation.py:55,61,83`
(`LIBRARY_PAT`/`INTERNAL_PAT`; a config creator named `"  "` or typed
`"robot"`; verified). The walker resolves `creation.py:61` as `Invalid
creator type person` (it took the dataclass default): log it in the review
rounds.

## 1. Sites

Rows 1 to 33 are `config-invalid`; the last column is the `expected` id
(2.3). Text abridged; T = table, K = key.

| # | Site | Lvl | Text today | Expected / code |
| - | - | - | - | - |
| 1, 4 | `_config_parse.py:71,106` | E | creator / creation-tool `entry is missing a valid 'name' (got X)` | `non-empty` |
| 2, 3 | `:77,83` | E | creator `'type'`, `'email'` `must be a string, got T: V` | `string` |
| 5, 7 | `:120,170` | E | provenance K, `'id-registry'` must be a string | `string` |
| 6 | `:134` | E | `[tool.pitloom.provenance] must be a table` | `table` |
| 8 | `:208` | E | fragment `'files' must be an array` | `array` |
| 9, 11 | `:216,241` | E | `'files'` entry empty string / table entry without a valid `'path'` | `non-empty` |
| 10 | `:223` | E | `'files' entries must each be a string or table` | `string-or-table` |
| 12-15 | `:247,253,262,268` | E | `'files' entry` role, description, sha256, link-to-main: string | `string` |
| 16, 19 | `:290,392` | E | `no-creation-tool`, `describe-relationship` must be a boolean | `boolean` |
| 17 | `:311` | E | `'sbom-basename' must be a file name, not a path` | `file-name` |
| 18 | `:330` (`_pick_str`) | E | `[tool.pitloom] K must be a string` | `string` |
| 20-22 | `_config_read.py:30,50,63` | E | `T K must be a boolean` / `an integer` / `one of A, B` | `boolean` / `integer` / `one-of-*` |
| 23-24 | `_config_read.py:71,77` | E | `T must be an array of tables` / `entry must be a table` | `array-of-tables` / `table` |
| +0 | `_config_read.py:91` | E | `[tool]`, `[tool.pitloom]`, ... `must be a table` | `table`; drop the pattern |
| 25-27 | `_config_parse_scan.py:53,61,133` | E | `'pattern'` non-empty / MIME `type/subtype` / content-type table | `non-empty` / `media-type` / `table` |
| 28 | `plugins/_hatch_config.py:54` | E | hook `'enabled' must be a boolean (true/false)` | `boolean` |
| 29-30 | `core/model_extract_limit.py:65,69` | E | `L must be an integer` / `a positive integer` | `integer` / `positive`; by route (2.3) |
| 31-32 | `core/provenance.py:88,92` | E | integer / `0 (unlimited) or at least 8 bytes` | `integer` / `budget`; by route |
| 33 | `core/file_names.py:88` | E | `L must be a file name without .spdx3.json` | `bare-file-name`; by route |
| +0 | `core/creation.py:55,61,83` | E | blank creator or tool name; creator type | `non-empty` / `creator-type` (reader checks first) |
| 34-38 | `_config_legacy.py:86,93,105,111,124` | E | `T 'K' has moved to D. Update your config.` | `config-moved` |
| 39 | `_hatch_config.py:61` | E | hook `K is no longer supported here; set it under D instead.` | `config-moved` |
| 40 | `_config_keys.py:159` | W | `SRC T unknown key 'K'; did you mean 'X'?` (or `; it belongs in T2`) | `config-unknown-key` |
| 41 | `_hatch_config.py:68` | E | hook `unknown key(s): ['k']. Only 'enabled' and ...` | `config-unknown-key` |
| 42 | `config_cascade.py:211` | E | `config file 'P': <exc>` | forward; `config-malformed`; `file-unreadable/not-utf8` (2.5) |
| 43 | `config_cascade.py:214` | W | `Options: 'P': --config file has no [tool.pitloom] table; using the defaults` | `option-no-effect` (Q4) |
| 44 | `_loom_active_run.py:79` | E | `ValueError(str(exc))` of a coded `input-not-found` | forward (2.5) |
| 45 | `_loom_active_run.py:81` | E | `config file 'P': <OSError>` | `file-unreadable` |
| (46) | `core/file_names.py:92` | W | `L 'V' is not a bare file name ...; using 'B'` | PR 16 (Q6) |
| 47-48 | `setuptools_cfg.py:352,355` | E | setup.cfg interpolation / INI parse error | `config-malformed` (Q5) |
| 49-50 | `core/creation.py:166,173` | E | `SOURCE_DATE_EPOCH='x' is not an integer ...` / `out of range` | `source-date-epoch-invalid` |
| 51 | `creation_info.py:64` | E | `Invalid ISO 8601 datetime: V` | `datetime`; by route (2.6) |
| 52 | `plugins/hatch.py:124` | I | `Pitloom build hook: created and builtTime come from the clock; ...` | `datetime-unpinned` |

Not config: `core/iri.py:145` (`--namespace`, already argparse detail, or
`IdRegistry.new`: an `option-invalid` library line, final sweep);
`plugins/hatch.py:514` (an `sbom-basename` and `sbom-files` name clash,
ERROR, nothing kept, so not ruling 1's grid; PR 16); `sdist.py:275` (PR 12;
T4); `enrich.py:74`, `fragments.py:510` (PR 15).

## 2. Design

### 2.1 Codes (all `since` 0.25.0, topic `config`)

| Code | Condition | Levels | Actor | Effect | Advice (short) |
| - | - | - | - | - | - |
| `config-invalid` | invalid | ERROR | user | not-written | Tell the user the key, its value and what it must be; never edit their config. |
| `config-moved` | moved | ERROR | user | not-written | Tell the user the key's new place (in the line). |
| `config-unknown-key` | unknown-key | WARNING; ERROR (hook) | user | none | The key is ignored; the hint names the likely key or table. |
| `config-malformed` | malformed | ERROR | user | not-written | Not valid TOML (or INI); fix the syntax where the parser says. |
| `source-date-epoch-invalid` | invalid | ERROR | user | not-written | Unset it, or set whole seconds since 1970 (the build environment sets it). |
| `datetime-unpinned` | unpinned | INFO | none | none | (R1) Builds differ in time; `SOURCE_DATE_EPOCH` or `creation-datetime` pins it. |

Every advice ends with `ASK_FIRST`.

`config-unusable` (the migration plan's name) is not used: no site reads a
well-formed file it cannot use; a syntax error is `malformed` (decision D:
the advice is "fix the syntax"). Value-ignored folds into `option-no-effect`
(one line, site 43). No new condition word.

### 2.2 Fields

- `config_key` (new, closed pattern, not free): written from
  `ConfigPlace(table, key=None, entry=None, sub=None, setup_cfg=False)` as
  `[tool.pitloom] pretty`, `[tool:pitloom:provenance] max-source-metadata-bytes`,
  `[[tool.pitloom.creator]] entry 0 type`, `[tool.pitloom.fragment] files
  entry 2 role`, `[tool.pitloom.provenance]`. The ONE place that spells `.`
  or `:` (T2); entries count from 0 (as `FINGERPRINT_ENTRY_LINE`). Table
  names: a closed tuple in `_field_tables.py`, drift-tested against
  `KNOWN_KEYS`/`KNOWN_ENTRY_KEYS` (`messages` cannot import `_config_keys`,
  which will import `messages`).
- `expected` (new, closed table, 2.3), plain.
- `got` (new): what was found, never `%r`: `a string 'maybe'` (the string
  through `entity_text`: URL credentials masked, controls escaped, cut to 40
  characters with `...`), `an integer 0`, `a float 1.5`, `a boolean true`,
  `a date-time`, `an array`, `a table` (no contents: bounded, no nested
  secret), `nothing` for a missing key. TOML type names, not Python's
  (`str`, `dict`): the user reads TOML.
- Reused: `file` (`FILE=`, `file_text`), `entry` (an unknown key as written,
  escaped), `setting` (a known key, the "did you mean" hint), `option`.

### 2.3 The closed `expected` table and `config_invalid()`

`messages/_config.py` holds `EXPECTED: Mapping[str, str]` (id to text); a
key outside it raises `InternalError`. Text is what follows `must be `:

| Id | Text | Sites |
| - | - | - |
| `boolean` | `true or false` | 16, 19, 20, 28 |
| `integer` | `an integer` | 21, 29, 31 |
| `positive` | `an integer of at least 1` | 30 |
| `budget` | `0 (no cap) or an integer of at least 8` (8 = `MIN_SOURCE_METADATA_BYTES`, drift test) | 32 |
| `string` | `a string` | 2, 3, 5, 7, 12-15, 18 |
| `non-empty` | `a non-empty string` | 1, 4, 9, 11, 25, creation.py:55,83 |
| `string-or-table` | `a string or an inline table` | 10 |
| `table` | `a table` | 6, 24, 27, :91 |
| `array` | `an array` | 8 |
| `array-of-tables` | `an array of tables` | 23 |
| `one-of-format`, `one-of-detail`, `one-of-preserve`, `one-of-method` | `one of annotation, both, comment` etc. (drift test against each `frozenset`) | 22 |
| `creator-type` | `one of agent, organization, person, software-agent` | creation.py:61 |
| `media-type` | `a media type type/subtype (image/png)` | 26 |
| `file-name` | `a file name, not a path` | 17 |
| `bare-file-name` | `a file name without .spdx3.json` | 33 |
| `datetime` | `an ISO 8601 date and time` | 51 (config route) |

Helper (Opus): `config_invalid(place, expected, got=MISSING) ->
ConfigInvalidError` (a `CodedValueError` keeping its values; `raise
config_invalid(...)`, the `input_not_found` shape). `parse_pitloom_config`
catches it once and raises `exc.located(source, is_setup_cfg)`: `FILE=` and
the INI spelling added in one place, no reader takes `source`. A pickle
keeps text and code only (`_restored`), enough once located. Lines:

- `FILE=%(file)s: %(config_key)s: must be %(expected)s, got %(got)s`
- `%(config_key)s: must be %(expected)s, got %(got)s` (no source: a
  library dict, `setup_cfg_pitloom_config(text)` without a name)

The shared validators (29 to 33) take a stage flag (CLAUDE.md, stage-scoped
helpers), not a label string: `ConfigPlace` raises `config-invalid`, a
library parameter name raises a new `option-invalid` line
`%(option)s: must be %(expected)s, got %(got)s` (actor caller). The CLI
flag route stops calling them: `cli/options.py:242,255` call the pure
`*_problem(value) -> expected-id | None` (the `iri.namespace_problem`
shape) and raise `ArgumentTypeError` with the `EXPECTED` text, so the flag
line stays `argument --x: ... [option-invalid]`, exit 2.

### 2.4 Moved and unknown keys

- `config-moved`: `FILE=%(file)s: %(config_key)s: moved to %(destination)s`
  and the no-`FILE` twin; `destination` a closed table built from
  `_MOVED_CREATION_KEYS`, `_MOVED_TOP_LEVEL_TABLES`, `_MOVED_FLAT_KEYS` and
  the hook's `_MOVED_KEYS` (drift test). "Update your config." goes: the
  advice says it. Hook line: `%(config_key)s: moved to %(destination)s`
  (no `FILE=`: T5).
- `config-unknown-key` WARNING: `FILE=%(file)s: %(config_key)s: unknown key
  %(entry)s; did you mean %(setting)s?`, `...; it belongs in %(tables)s`,
  `...` without a hint, each with a no-`FILE` twin (6 lines; `config_key`
  here is the table). ERROR (hook): `%(config_key)s: unknown keys
  %(entries)s; only enabled and Hatchling's own hook keys go here, other
  settings go in [tool.pitloom]`. The said-once memo stays: `emit(...,
  once=<the warn_once key today>)`, scoped by source and table.

### 2.5 Files that do not parse; ruling 2

- `config_cascade.py:211`: `if code_of(exc): raise` (forward unchanged:
  the inner line already names `FILE=`); a `TOMLDecodeError` raises
  `config-malformed` `FILE=%(file)s: not valid TOML; %(failure)s`; a
  `UnicodeDecodeError` raises `file-unreadable/not-utf8` with a new
  `READ_USES` entry `for the configuration`. An `OSError` (today escapes as
  the handler's uncoded `[Errno 13] ...`) raises `file-unreadable`, same use.
- `_loom_active_run.py:79`: the `input-not-found` text and code, as a
  `ValueError` (the library contract): promote `_emit._restored` to a public
  `recoded(cls, exc)`; `:81` is the `file-unreadable` raise of
  `load_config_file`, so the `except OSError` goes.
- `sdist.py:275` (PR 12's text): PR 8 adds only `if code_of(exc): raise`.
- `setuptools_cfg.py:352,355` (Q5): `config-malformed` INI lines
  `FILE=%(file)s: not valid INI; %(failure)s` and the interpolation one.

### 2.6 Time sources (orphans)

- `SOURCE_DATE_EPOCH`: `SOURCE_DATE_EPOCH=%(value)s: not an integer number
  of seconds since the Unix epoch` and `...: out of range for a date`
  (`value` through `free_text`; today `%r`). `subject_key="SOURCE_DATE_EPOCH"`
  (fits `_KEY_RE`; unverified that the reference renders it well).
- `creation-datetime`: validated where it enters. Config: at parse
  (`expected` `datetime`). Flag: argparse `type=`, `option-invalid` exit 2
  (exit 1 today: a behaviour change, Q7). Library (`CreationMetadata`):
  `option-invalid` `creation_datetime: must be ...` raised at
  `creation_info.py:228` and `_document_main_package.py:90`. Move the pure
  parse to `pitloom.core.creation` as `iso_datetime_or_none()` (stdlib only;
  `assemble` re-exports `parse_iso_datetime` for callers); `_release_time`
  keeps its `WARNING`. A live import test in both orders.
- `datetime-unpinned` (hook only): today's text, no trailing period, the
  `Pitloom build hook: ` literal of R1's ruling. No test pins it: add one.

### 2.7 How a line prints (example: `pretty = "maybe"`)

- CLI: `ERROR: loom project: FILE=p/pyproject.toml: [tool.pitloom] pretty:
  must be true or false, got a string 'maybe' [config-invalid]`, exit 1
  (today no file is named; verified).
- `--config c.toml`: the same line, `FILE=c.toml` once (no `config file`).
- Hook: `ERROR: Pitloom build hook: FILE=<root>/pyproject.toml: ...
  [config-invalid]` (`HOOK_FRAME` plus `code_extra_of`, `plugins/hatch.py`
  `initialize`, verified). The hook's own table: `ERROR: Pitloom build hook:
  [tool.hatch.build.hooks.pitloom] enabled: must be true or false, got a
  string 'yes' [config-invalid]`.
- Library: a `CodedValueError`, `str()` the line, `pitloom_code`
  `config-invalid`; nothing printed.
- Action: the CLI line (the `config` input becomes `--config`,
  `action.yml:432`); the step fails.

## 3. Surface parity (entry points read)

- CLI: `__main__.main` and `cli_error_handler` (`cli/commands/utils.py:67`:
  `print_error(str(e), code=code_of(e))`); project config through
  `extract/project/pyproject.py:293` and `setuptools_cfg.py:479`; `--config`
  through `cli/options_resolve.py:205`.
- Hook: `plugins/hatch.py` `initialize` (one `log.error` with
  `code_extra_of`); `validate_config`, then `read_pitloom_config(project_dir
  / "pyproject.toml")` (no `setup.cfg`, no `--config`).
- Library: `read_project` (under `generate_project_sbom`), `loom.run`
  (`_loom_active_run.loom_config`), `load_config_file`, `sdist._config`.
- Action: the CLI only.
Every route reaches `parse_pitloom_config`, the one place `located()` runs.

## 4. Traps (counter-examples)

- T1 (R3). `--max-model-extract-bytes 0` is `option-invalid` (argparse,
  exit 2); `max-model-extract-bytes = 0` in a file is `config-invalid`
  (exit 1, actor user), also through `--config`; `generate_project_sbom(
  max_model_extract_bytes=0)` is `option-invalid` (actor caller). And today
  `accept-url-credentials`/`url-credentials` in `[tool.pitloom]` raise
  `option-invalid` (`credential_policy.py:240,265`): R3 says
  `config-invalid` (Q1).
- T2. setup.cfg errors name the TOML table: `[tool:pitloom] pretty = maybe`
  says `[tool.pitloom] 'pretty' ...` (verified). Only `_config_legacy` and
  `max-source-metadata-bytes` spell `:`. Fixed by the writer; one test per
  site family under `is_setup_cfg`.
- T3. `_pick_str` (`_config_parse.py:330`) names `[tool.pitloom]` for a key
  read from `[tool.pitloom.creation]` (`datetime = 5`): the place must carry
  the table the key came from.
- T4. Prefix stacked: `config_cascade.py:211` and `sdist.py:275` prepend
  `config file 'P': ` to every `ValueError`; after `located()`, a coded line
  would read `config file 'P': FILE=P: ...`. Both forward a coded exception.
- T5. The hook table may live in `hatch.toml` (`[build.hooks.pitloom]`);
  the hook gets a dict, so its lines name no `FILE=` (unverified whether
  Hatchling tells the source).
- T6. Typo vs unknown: `prety` hints `pretty`, `no-creation-tool` never
  `creation-tool` (`_opposite`), a misplaced key hints its table. The hook's
  unknown key is an ERROR, `[tool.pitloom]`'s a WARNING: one code, both.
- T7. Moved keys: `creation-tool` is stale as a string, valid as an array;
  `enrich` only as a table. The hook's `_MOVED_KEYS` comment claims "one
  source of truth shared with the CLI": it is a second dict (drift test).
- T8. Values that leak: `creation-datetime = "https://u:secret@h/x"` would be
  echoed by the `datetime` line; `got` masks through `entity_text`.
  Fingerprint lines never show the value (keep `got` off them).
- T9. A scope pattern hides user errors (section 0): validate in the
  reader through one shared creator-type normaliser, not a copy.
- T10. Windows: `FILE=` is `str(Path)` with `\`: build the expected path
  with `str(path)`; emulate `C:\p\pyproject.toml` through `PureWindowsPath`
  into `file_text` (a drive colon before the `: ` separator).
- T11. The hook's `FILE=` is absolute (`Path(self.root)`), a temporary tree
  under pip (Q8). T12: an unquoted TOML date for `creation-datetime` is
  refused as "not a string" (out of scope: a roadmap note).

Tests that pin today's wording (matching lines): `tests/core/`
`test_config.py` 27, `test_config_unknown_keys.py` 22,
`test_config_moved_keys.py` 18, `test_model_extract_limit.py` 12,
`test_loom_pitloom_config.py` 10, `test_fetch_policy.py` 8,
`test_metadata_edge_cases.py` 7, `test_provenance.py` 7,
`test_credential_policy.py` 7 (Q1); `tests/test_config_key_surfaces.py` 9,
`test_byte_cap_surfaces.py` 5; 1 to 5 each in 16 more (hook, sdist,
setup.cfg, creation, CLI options; rerun the grep in the PR). Manual CLI
checks pin none (grep of `scripts/manual_cli_checks`).

## 5. Sensitive areas

- The cascade (CLI > pyproject > defaults) is untouched: messages only, plus
  the earlier `creation-datetime` refusal (Q7). SBOM diff vs `main` empty
  with `--creation-datetime` pinned.
- The hook reads config in an isolated build: no new import of a
  dependency it lacks. `_config_parse.py` is 508 lines: if the helper does
  not shrink it, move the fragment readers out first.
- `docs/configuration.md` is 31.6 KB, over the hard limit (review rounds,
  "Open: docs"). This PR adds no prose there: it replaces the quoted
  moved-key sentence (line 156) and the "raises `ValueError`" phrases (144,
  174, 305, 325) with code links of equal or smaller size. The split is a
  separate docs PR (roadmap line).

## 6. Docs and skills

- New topic `config` ("Configuration") after `options` in `TOPIC_TITLES`
  (index position 5), module `pitloom.messages.config`; generated
  `docs/message-codes-config.md` and the skills' `messages-config.md`;
  `mkdocs.yml` nav. Budget about 10 to 14 KB. `config-unsafe` stays in
  `targets` (released 0.23.4, linked from `docs/git-urls.md:282`); `files`
  gains only the `READ_USES` entry (under 100 bytes of its 25.1 KB).
- Docs: `hatchling-build-hook.md:121` (clock), `configuration.md` (above),
  `python-api.md:141,150`, `python-api-remote.md:58,101` (name the code).
- Skills: `references/cli-flags.md` (`--config` bullet, one clause);
  `lockfile-discovery.md` quotes no message (confirm with `--quotes`). No
  flag changes: no `SKILL.md` description, no `_matrix_plan.py` entry. Run
  the generator and `--quotes` before and after; read changed skill files
  in full.

## 7. Tests

`tests/messages/test_config.py` (entries, writers, drift of tables,
choices, moved destinations, budget minimum) and `test_config_surfaces.py`
(`platform`), parametrised, short `ids=`.

- Per site: one case per `expected` id and per table, through the real
  reader (not the helper alone); setup.cfg spelling for each (T2); `_pick_str`
  from `creation` (T3); `got` `nothing` for a missing name.
- Canaries: no stderr line holds `FILE=` twice or `config file` before
  `FILE=` (CLI `--config`, sdist; fails on base); a newline, `\x1b` and a
  lone surrogate in a value and in an unknown key (escaped, one line); a URL
  with `user:pass@` as `creation-datetime` (masked, T8); a Windows path via
  `PureWindowsPath` into `file_text`; an unknown key in a file parsed twice
  said once (CLI reads `pyproject.toml` twice); a TOML error on line 3 of a
  CRLF file names line 3; fail-on-base with `PYTHONPATH` pinned to a
  654d734e archive.
- Surfaces: CLI (stderr line, `[code]`, exit 1; `--config`), hook
  (`staged_sbom` or `make_hook`: config-invalid, hook `enabled`, unknown and
  moved hook keys, `datetime-unpinned`), library (`pitloom_code` on the
  exception from `generate_project_sbom`, `loom.run`, `load_config_file`),
  Action through the CLI (one `tests/scripts/action/` case if it runs
  `loom`; else stated). `SOURCE_DATE_EPOCH` on CLI, hook and embed.
- Mutants: `located()`, the separator, `got`'s `bool` before `int`, the
  forward guards (T4), the validators' stage flag. Drift: a marker per docs
  or skills quote; choices against `_VALID_*`.
- Classify each new file (`-m platform --collect-only -q`); the PR carries
  `test-all-os`.

## 8. Ratchet and CHANGELOG

316 to 265: `core._config_parse` 19, `_config_read` 5, `_config_parse_scan`
3, `_config_legacy` 5, `_config_keys` 1, `config_cascade` 2,
`plugins._hatch_config` 3, `core.model_extract_limit` 2, `core.provenance`
2, `core.file_names` 1 (`:92` stays, Q6), `core.creation` 2, `assemble.spdx3.creation_info`
1, `plugins.hatch` 1, `_loom_active_run` 2, `setuptools_cfg` 2 (51 in
all; no `core._config_*` module stays in the baseline). Regenerate
with `--write-baseline` after merging `main` (never by hand). Remove
`^\{name\} must be a table` from `INTERNAL_PAT` with the coding.

CHANGELOG (Added, folded into the catalogue bullet): "Configuration errors
carry a message code and name the file ([#NNN])". Fixed: "A `setup.cfg`
`[tool:pitloom]` error names that table ([#NNN])".

## 9. Agents

- Opus: `messages/_config.py`, `config.py`, fields and tables (new
  `_fields_config.py`; `_fields.py` is 441 lines), `config_invalid`,
  `located`, `recoded`, `_topics.py`, `_scope.py`, the validators' stage
  flag; review of every diff; the stderr sweep.
- Sonnet A (sites in `core/_config_*.py`, `plugins/_hatch_config.py`).
  May touch only those files. Use `config_invalid(ConfigPlace(...), "<id>",
  got=value)`; never write a table name as a string; never catch and
  rewrap a coded exception; keep `warn_once` keys verbatim in `emit(once=)`.
- Sonnet B (validators and orphans): `core/model_extract_limit.py`,
  `core/provenance.py`, `core/file_names.py`, `cli/options.py`,
  `core/config_cascade.py`, `_loom_active_run.py`, `core/creation.py`,
  `assemble/spdx3/creation_info.py`, `_document_main_package.py`,
  `plugins/hatch.py` (line 124 only), `sdist.py` (the forward guard only),
  `setuptools_cfg.py` (352, 355 only, if Q5).
- Sonnet C (tests, section 7): `tests/` only; updates the listed files.
- Haiku: grep checks (stale quotes, `%r` in touched templates, file sizes).
- Never: an exemption by text; a new condition word; a level change; `%r`;
  a helper adding a prefix; dropping the said-once memo; editing a
  generated page or the baseline; a block `pylint: disable`; touching
  `messages/` (Sonnet) or the sibling plan's files. Every judgement call
  (a new `expected` id, a line shape, a test that cannot reach a site) goes
  back to Opus.

## 10. Open questions (recommendation in brackets)

- Q1. Move the three `[tool.pitloom]` lines of `option-invalid`
  (`FINGERPRINT_ENTRY_LINE`, `FINGERPRINT_ARRAY_LINE`,
  `URL_CREDENTIALS_MODE_LINE`) into `config-invalid` (R3)? [Yes: unreleased
  (0.25.0), and the actor is the user; the library lines stay.]
- Q2. One `config-invalid` with the `expected` table, or variants? [One
  code: the advice is the same; variants only if a reviewer finds advice
  that differs.]
- Q3. `config-malformed` or a format code `toml-malformed` (R4's
  `json-malformed` shape) shared with PR 10's lock files? [`config-malformed`:
  the advice is by subject (fix your config; regenerate a lock file); agree
  with the PR 10 planner before either merges.]
- Q4. The empty `--config` WARNING as a new `option-no-effect` line
  `Options: FILE=%(file)s: %(option)s has no [tool.pitloom] table; the
  defaults apply`? [Yes; the `--config` flag is what had no effect.]
- Q5. `setuptools_cfg.py:352,355` in this PR? [Yes: `setup_cfg_pitloom_config`
  reads only Pitloom's settings; PR 12 keeps the metadata reads.]
- Q6. `file_names.py:92` (a trimmed base name, `WARNING`)? [Leave it to PR
  16 (the embed's `--sbom-basename`); it is neither invalid nor no-effect.]
- Q7. Refuse a bad `--creation-datetime` at parse (exit 2, was 1 at
  assembly)? [Yes, with a CHANGELOG line.]
- Q8. The hook names `FILE=pyproject.toml` relative to the project root?
  [Yes: the build tree is temporary.]
- Q9. Codes `source-date-epoch-invalid` and `datetime-unpinned`?
  [Yes; `datetime-unpinned` actor none (R1).]
