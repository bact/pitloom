---
Created: 2026-11-17
Last-Modified: 2026-11-17
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message catalogue PRs 10 and 11: lock files, lock entries, requirements

See also: [message-catalogue-pr8-12-plan.md](message-catalogue-pr8-12-plan.md)
(rulings 1 to 4, the family-12 contract),
[message-catalogue-migration-plan.md](message-catalogue-migration-plan.md)
(rows 10 and 11, R1 to R7), [message-catalogue-pr6-pr7-plan.md](message-catalogue-pr6-pr7-plan.md),
[message-catalogue-pr8-9-config-plan.md](message-catalogue-pr8-9-config-plan.md),
[message-catalogue-families.md](../implementation/message-catalogue-families.md).

Status: plan, 2026-11-17, `main` 654d734e. One PR for rows 10 and 11
(they share every helper). Sites listed by `PYTHONPATH=src .venv/bin/python
-m scripts.message_inventory --jsonl`, filtered by `_scope.in_scope` and
`coded` false, then read at the file:line given; "unverified" says so.

## 0. Counts

**Row 10: 21, row 11: 27, 48** (as planned). Ratchet **316 to 268**. To
0: `extract.lock._common_warnings` 7, `_lock_io` 2, `_pins` 1, `_uv_graph`
10, `cascade` 2, `common` 1, `pipfile` 3, `poetry` 1, `pylock` 8,
`requirements` 4, `uv` 3, `core.requirements` 3, `assemble.spdx3._dep_scope`
2; `extract.project._poetry_requirements` 2 to 1 (line 84, poetry-core's
API, stays 12's: `library-unusable`'s `pitloom[extra]` field cannot name a
hard dependency). Row 12's by ruling 4: `deps_installed.py:341,354,363`,
`_installed_reconcile.py:107`, `_requirements_files.py:253,356`,
`_poetry_extras.py:179`, `_poetry_fields.py:105`, `pyproject.py:469`.

## 1. Per-site table

All `WARNING` unless said. Paths under `src/pitloom/extract/lock/` unless
given. Tier S Sonnet, O Opus.

| Site | Text today (short) | Code | Fields | Row | Tier |
| - | - | - | - | - | - |
| `_lock_io.py:104` | `Cannot read`/`Failed to parse <path>: <exc>` | by exception (2.2) | file, use, failure; cap | 10 | O |
| `_lock_io.py:130` | top-level value not an object | `lock-file-malformed` | file, value_type | 10 | S |
| `_common_warnings.py:99`; `pylock.py:137,145,216`; `uv.py:130` | top-level key wrong or missing; ignoring (216: treated as empty) | `lock-file-malformed` | file, lock_key, value_type | 10 | S |
| `_common_warnings.py:60`; `uv.py:82`; `pylock.py:104,114,125` | not a genuine lock; lock-version missing, other major, newer minor (125 reads on) | `lock-file-wrong-format` | file, lock_key, lock_value, number | 10 | S |
| `uv.py:101`; `_uv_graph.py:109` | no project package; N candidates, none named X | `lock-file-unusable` | file, number, package | 10 | S |
| `cascade.py:241` | previous source matches no lock source | `InternalError` (R7, a table drift) | none | 10 | O |
| `cascade.py:264` | both X and Y present; Y takes priority | `lock-file-conflict` | kept, dropped | 10 | O |
| `requirements.py:192` | `%s:%d`: malformed requirement line | `lock-entry-malformed` | file, line, why | 10 | S |
| `requirements.py:178,200,210` | `%s:%d`: option; direct URL; not one exact pin | `lock-entry-unusable` | file, line, lock_value or package | 10 | S |
| `_pins.py:157` | X pinned to conflicting versions; ignoring file | `lock-entry-conflict` | file, package, dropped | 10 | S |
| `_common_warnings.py:43`; `_uv_graph.py:157` | conflicting versions; N resolved versions | `lock-entry-conflict` (157 said once) | file, package, dropped | 11 | S |
| `_common_warnings.py:80`; `_uv_graph.py:133`; `pipfile.py:198` | X-sourced; marker-conditional version; not one exact pin | `lock-entry-unusable` | file, package, source_kind or lock_value | 11 | S |
| `_common_warnings.py:114,128,144`; `_uv_graph.py:142,205,234,240,249,275,286`; `common.py:191`; `pipfile.py:141,190`; `poetry.py:111`; `pylock.py:350,365` | version, name, table, groups, category, marker, extras, optional-dependencies of the wrong shape; reference or extra not in the lock (142, 275; 142 said once); marker unparseable, kept (350) | `lock-entry-malformed` | file, package, lock_key, value_type, lock_value, extra, failure | 11 | S |
| `core/requirements.py:68,79` | Skipping dependency / extra entry X (source): reason | `requirement-invalid`; Poetry path: `requirement-unusable` | dependency, extra, declared_in, failure | 11 | O |
| `core/requirements.py:95` | inner extra condition ignored; optional | `extra-gate-ambiguous` | dependency, extra | 11 | O |
| `assemble/spdx3/_dep_scope.py:69,88` | not PEP 508, or marker not isolated; recorded as required | `requirement-invalid`; `extra-gate-unusable` | dependency, package | 11 | S |
| `extract/project/_poetry_requirements.py:153` (raise) | `'markers' is X, expected a string` | detail of 68 (class added to `DETAIL_EXC`) | none | 11 | O |
| new, `assemble/spdx3/deps.py` near 444 (`INFO`) | none (the #405 skip is silent) | `dependency-name-ambiguous`, born coded | package | 11 | O |

## 2. Design

### 2.1 Codes (`since` 0.25.0; actor user unless said)

Topic `lock-files`:

- `lock-file-malformed` (thinner): read and decoded, but does not parse
  or lacks the top-level shape. Advice: regenerate with its tool (`uv
  lock`, `poetry lock`); Pitloom tried the next lock in the order.
- `lock-file-wrong-format`: not this format or a version Pitloom does not
  read; a newer minor is read anyway (weaker). Advice by version, as
  `registry-wrong-format`.
- `lock-file-unusable`: well-formed, no root for this project. Advice: run
  from the member, or name the project.
- `lock-file-conflict` (none): two locks; the fixed order keeps one.
- `lock-entry-malformed` (thinner): one entry, reference or
  `requirements.txt` line of the wrong shape, or naming what the lock does
  not hold (stale, hand-edited). Advice: regenerate.
- `lock-entry-unusable` (thinner): well-formed, no exact registry pin to
  record (VCS, path or URL source; a range; a pip option; a version per
  marker). Advice: nothing to fix in a lock; a `requirements.txt` is read
  as a lock only when every line is one exact pin.
- `lock-entry-conflict`: one lock states a package at several versions.

Topic `dependencies`:

- `requirement-invalid` (thinner): a requirement or extra entry not PEP
  508, a marker that does not parse, a Poetry table not convertible, a
  self-reference to an undeclared extra, a self-reference cycle. Advice:
  fix the declaration.
- `requirement-unusable` (thinner): a Poetry `path`/`file` source.
- `extra-gate-ambiguous` (weaker, actor none): needs several extras
  together; optional for any.
- `extra-gate-unusable` (weaker): an extra marker Pitloom cannot isolate;
  recorded as required.
- `dependency-name-ambiguous` (`INFO`, actor none, thinner):
  `PACKAGE=%(package)s: a direct reference; not looked up on PyPI`. Once
  per package per document; never offline. Not `release-unpinned`
  (`messages/_pypi_info.py:88`): its advice (give the version in the URL)
  does not fit, and a code is a promise (decision L).

Reused: `file-unreadable`, `file-unreadable/not-utf8` (use `for dependency
pins`, already in `READ_USES`), `over-cap` (`KEY_LINE`).

### 2.2 Two rules for a weaker agent

**File or entry: code by where the fault is.** A fault in the file as a
whole, a top-level key or the root entry takes `lock-file-*`; a fault in
one package entry, one dependency reference or one `requirements.txt`
line takes `lock-entry-*`; the last clause says what was left out
(`skipped`, `no pins read from it`). Example: a range on line 3 of
`requirements.txt` is `lock-entry-unusable`, its clause `no pins read from
it`.

**Malformed or unreadable (rows 9 and 12 reuse it).** The system refused
or failed the read, or the bytes are not in the encoding the format
requires: `file-unreadable` (`/not-utf8`). Read and decoded but does not
parse or lacks the shape: `<subject>-malformed`. Over a size cap:
`over-cap`. Absent (a dangling link too: `os.stat` raises
`FileNotFoundError`): quiet. TOML is strict UTF-8
(`_toml_io.load_toml_bytes`), `requirements.txt` `utf-8-sig`,
`Pipfile.lock` `json.loads(bytes)` (UTF-16/32 accepted; a bad UTF-8 byte
raises `UnicodeDecodeError`: `not-utf8`, never malformed).

`warn_unreadable_lock_file` (`_lock_io.py:87`) stays the one dispatch, by
exception type, never by text. `LockFileRefusedError` gains `cap: Cap |
None` (today the text `over N bytes`, `_lock_io.py:83`): with a cap,
`over-cap` (`Cap(FETCH_MAX_BYTES, "byte", "lock-file")`, outcome `no
dependency pins read`); without, `file-unreadable`, failure `not a regular
file`.

### 2.3 Wording, frame, line numbers

- No frame, no literal prefix: `FILE=<name>` marks the family. The name is
  `lock_path.name` (`uv.lock`), as the shipped call already does
  (`_lock_io.py:98`): locks are read at the project root only, so the name
  is deterministic and no checkout path shows. Today's
  `quote_source(lock_path)` (full path) and bare labels both go.
- Shape: `FILE=%(file)s[ PACKAGE=%(package)s]: CONDITION; OUTCOME`;
  `requirements.txt`: `FILE=%(file)s LINE=%(line)s: ...` (the `%s:%d` form
  goes). Example: `WARNING: FILE=requirements.txt LINE=3: 'flask' is not
  one exact version; no pins read from it [lock-entry-unusable]`.
- Line numbers: `str.splitlines()` (`requirements.py:150`), as pip: CRLF
  and a lone CR count once; a form feed, `\x1c` to `\x1e`, `\x85`, U+2028
  or U+2029 also start a line (an editor may disagree). A continued line
  takes its first physical line. TOML and JSON errors keep the parser's
  position inside `failure` (`tomllib` counts `\n`), never a `LINE=`.
- Outcomes, one phrase per meaning: `skipped`, `no pins read from it` (the
  next lock is tried), `read as empty`, `read; newer keys not read`,
  `kept, its marker read as true`.

### 2.4 Fields (new `messages/_fields_lock.py`; `_fields.py` is 441 lines)

- `package`: free, `free_text`; every caller passes a name that passed
  `is_usable_name` (`common.py:126`); the PR lists the check per site.
- `dependency`, `extra`, `lock_value`, `kept`, `dropped`: free, written by
  `logging_config.excerpt` (masks URL credentials, cuts to 120 characters,
  escapes; `logging_config.py:249`). A 50 MB lock can hold a 10 MB
  version: never uncut. `dropped` takes a collection: sorted, joined `, `.
- `line` (`[1-9][0-9]*`), `value_type` (closed: `bool`, `date`,
  `datetime`, `dict`, `float`, `int`, `list`, `NoneType`, `str`, `time`),
  `lock_key` (closed: the keys the readers check), `source_kind` (closed:
  the union of the readers' non-registry keys), both drift-tested against
  the readers' constants; `declared_in` (free: `Poetry`,
  `optional-dependencies`, `extras_require`, a setting).
- `requirement` is taken (`pitloom[gguf]`): never reuse it.

Masking: a direct reference's URL is never printed (its kind and name
only). `InvalidRequirement`'s text repeats the line and a caret: keep its
first line, through `core.url_masking.sanitize_url_credentials`, into
`why` (as `requirements.py:191` does today); an exception goes through
`failure` (`failure_text`). The stderr formatter masks again
(`logging_config.py:115`), but a library handler sees raw args: mask at
the writer. No `%r` (34 today in these modules).

### 2.5 Helpers (Opus)

- `say_lock_file`, `say_lock_entry` in `messages/_lock_say.py`, public
  from `pitloom.messages.lock_files`: `emit` plus the memo of 4.3; no
  prefix.
- `warn_skipped_dependency` and `warn_skipped_extra_entry` take a cause
  from a closed set (`not-pep-508`, `marker`, `not-convertible`,
  `local-source`, `undeclared-extra`, `cycle`), not free reason text; the
  cause picks code and line; `quiet` stays.
- Ruling 2: no site here relays a coded exception today (verified:
  `_lock_io.py:124`, `requirements.py:118`, `core/requirements.py:191`
  catch uncoded parser errors; `pep508` says its own `over-cap`, then
  raises a plain `InvalidRequirement`). Those three handlers forward
  `code_of(exc)` when present; one test patches a parser to raise a
  `CodedValueError` and asserts its `[code]`.

## 3. Conflict grid (ruling 1; only 11's row built here)

`conflict` only where two sources or two entries state one fact
differently and a fixed order, merge order or by-design rule settles it.
Every line ends `; kept %(kept)s, dropped %(dropped)s`, or `; skipped,
dropped %(dropped)s` (none kept), or `; both kept, <outcome>` (identity).
Advice default: "the SBOM states <kept>; <dropped> is not recorded". A
by-design override is `INFO`, actor none, effect none.

| Concept | Code | Sites (family) | Level, actor |
| - | - | - | - |
| One lock states a package at several versions | `lock-entry-conflict` | `_common_warnings.py:43`, `_uv_graph.py:157`, `_pins.py:157` (11) | W, user |
| Two lock files, fixed order | `lock-file-conflict` | `cascade.py:264` (10) | W, user |
| Two declared sources, fixed order | `project-field-conflict` | `_setuptools_options.py:394`, `_installed_reconcile.py:107` (12) | W, user |
| Declared pin against a lock pin | `dependency-version-conflict` | `deps_installed.py:341,363` (12) | W, user |
| Fragment against fragment, merge order | `fragment-conflict` | `_fragments_props.py:121,195` (15) | W, user |
| Fragment over a generated value, by design | `generated-value-conflict` | `_fragments_generated.py:188`, `_fragments_model_names.py:245`, `_fragments_evidence.py:120` (15) | INFO, none |
| Identity: both kept, or names unified | `fragment-id-conflict`, `dataset-name-conflict`, `dataset-field-conflict` | `_fragments_ids.py:56`, `_fragments_hashes.py:62` (15); `dataset_names.py:76`, `dataset_merge.py:101` (17) | as today |

Never `-conflict`: one of several candidates chosen (`installed.py:197`:
`-ambiguous`, like `file-ambiguous`); none of several matches
(`_uv_graph.py:109`); two values Pitloom cannot combine
(`core/requirements.py:95`: `extra-gate-ambiguous`); a caller merging two
objects that each hold a conflict record (`core/project.py:394`: caller
misuse or `InternalError`, 12 decides); a table drift (`cascade.py:241`);
one value with no rival (`_uv_graph.py:133`).

Amendment (Q1): `kept`/`dropped` are lower-case fields in the outcome
clause, not `KEPT=`/`DROPPED=` keys: keys belong to the subject block
(`LEVEL: [SUBJECT=value: ]CONDITION[; ACTION]`).

## 4. Surfaces, traps, said once

### 4.1 Who reads lock files (verified)

- CLI `loom project <dir>`, `loom generate <dir>`, `loom enrich
  --project-dir`, through `resolve_project_with_lockfile`
  (`extract/project/reader.py:258`; the peek reads none, the second read
  does, `reader.py:313-319`). Library `generate_project_sbom`
  (`assemble/_generators.py:278`), `enrich_model`
  (`_model_generator.py:434`), the Git URL route on its checkout
  (`_generators_git.py:187`: attacker text). `loom fragment list`, for a
  document id only (`_model_generator.py:202`; Q9). The Action runs the
  CLI.
- Never: the hook (`hatchling.py:51-62`, `plugins/hatch.py:310-313`),
  `loom wheel`, `embed-wheel`, `env`, an sdist or PyPI sdist
  (`reader.py:180`).
- The direct-reference `INFO`: every route assembling dependencies online
  (CLI, library, the hook, `loom wheel`); never `loom env` (pipdeptree has
  no `direct_url.json`; known bug).

Tests per surface: CLI (line, `[code]`, exit 0), library (`pitloom_code`
via `caplog`), hook (a malformed `uv.lock`: **no** lock line; a direct
reference online: the `INFO`), Git URL (a checkout fixture).

### 4.2 Traps, with the input where nothing must fire

- Lock-only (transitive) package: normal, no line.
- A stale lock against a declared pin is 12's `dependency-version-conflict`
  (two sources), not `lock-entry-conflict` (one file).
- Several versions is often legitimate (Q3): PEP 751 lets `pylock.toml`
  hold one name per marker, `uv.lock` per Python version; Pitloom
  evaluates no marker. Advice says "regenerate" only when the versions are
  not per environment. No line: `1.0` and `1.0.0` collapse (PEP 440).
- `uv.lock` root: a workspace with the project named: no line; the extras
  pass re-reads with `warn_entries=False` (`uv.py:155`): keep it.
- `requirements.txt` listed by `[tool.setuptools.dynamic]` is not tried
  (`cascade.py:253`): no line. A BOM and `\` continuations: no line. A
  `-r` file or `pip-compile --generate-hashes` output (a `--hash` on a
  continued line is not PEP 508) is not used, one line (Q10).
- Two locks (`uv.lock` and `requirements.txt`): first wins, **no** line;
  `lock-file-conflict` only when `poetry.lock` was applied during
  `pyproject.toml` reading and a higher one wins (`cascade.py:262`).
- `--no-use-lockfile`: no lock line.

### 4.3 Said once

- Bug: a package missing from `uv.lock`'s table and referenced twice is
  warned twice: each reference resolves before the `visited` check
  (`_uv_graph.py:186-195`; by reading, not run). Fix: a per-walk memo by
  (canonical name, code); Fixed entry, fail-on-base test.
- `lock-unreadable:<path>` (`_lock_io.py:100`) stays process-wide.
- New memos are per run (a set passed down), never `log_once`: a second
  library call on another project still warns. The `INFO`: once per
  package per document (both lists, `document.py:311-346`).
- Unverified: whether one `loom generate <dir>` run reads the cascade
  twice (`project_document_id` and the main read): count lines in the PR.

### 4.4 Wording pinned (grep of `tests/`; none in `scripts/manual_cli_checks`)

`tests/extract/lock/`: `test_common`, `test_cascade`, `test_requirements`,
`test_requirements_io`, `test_lock_io`, `test_pipfile`, `test_pdm`,
`test_poetry`, `test_pylock`, `test_pylock_real_world`, `test_uv`,
`test_uv_warnings`, `test_uv_transitive`; `tests/assemble/`:
`test_deps_locked_versions` (132, 147, 191), `test_dep_scope`,
`test_deps_extras_edges`; `tests/test_build_flag_warning_ordering`,
`tests/test_joined_extra_surfaces`, `tests/core/test_requirements`;
`tests/extract/project/`: `test_setup_cfg_requirements_files`,
`test_poetry_extras`, `test_poetry_requirements`,
`test_setuptools_dynamic`, `test_project_resolve_lockfile`,
`test_optional_dependencies`, `test_pyproject_deep`. Assertions move to
the code plus a short stable substring.

## 5. Sensitive areas and pages

- The `INFO` is new output on four surfaces: never offline, never for a
  registry requirement, never twice.
- New topics in `_topics.py` after `files`, before `pypi`: `lock-files`
  ("Lock files", 7 families, about 14 KB) and `dependencies`
  ("Dependencies", 5, about 9 KB; 12 adds `dependency-version-conflict`).
  Unverified estimates (`id-registry-ids`: 9 families, 20.5 KB). `files`
  (25,081 bytes) gains about 100 (`not-utf8` names a lock file); no family
  is added there. `over-cap`'s advice needs no change.

## 6. Skills and docs

- Generated only (`scripts/generate_message_reference.py`):
  `docs/message-codes-lock-files.md`, `-dependencies.md`, the index,
  `mkdocs.yml`, `references/messages-lock-files.md` and
  `messages-dependencies.md` in both skills, both `messages.md`.
- `skills/sbom-generate/references/lockfile-discovery.md` (no quotes): a
  paragraph pointing at the two pages. No `SKILL.md` or `description`
  edit, no `_matrix_plan.py` entry (no flag changes).
- `docs/dependency-sources.md`: 58-132, 160, 190-197, 213-240 (leave the
  version-conflict paragraph to 12), 381-385 (the direct reference now an
  `INFO`). `--quotes` before and after; a `_MARKERS` entry per new family
  in `tests/messages/test_drift_quotes.py`.

## 7. Tests

Files: `tests/messages/test_lock_file.py`, `test_lock_entry.py`,
`test_dependency_skips.py`, `test_dependency_name_ambiguous.py`.

- Canaries: no line holds `FILE=` or `uv.lock` twice (`_uv_graph.py:109`
  names it twice today: fails on base); `\n`, `\x1b`, a lone surrogate in a
  `Pipfile.lock` name, version and extra (JSON can hold `\ud800`, TOML
  cannot: `uv.lock` gets `\u001b`); a `PureWindowsPath` lock path into the
  `file` writer; the uv diamond said once (fails on base); CRLF
  `requirements.txt`, bad line 3, `LINE=3`, and a form-feed comment
  shifting it as pip does; a CRLF TOML error naming the parser's line; a
  10 KB version cut to 120 characters; `user:pass@` masked in `why` and in
  the record's args.
- `A and B`: `lock-file-conflict` (a previous result; a higher source
  wins) and the `INFO` (online; direct reference): one test per leg.
- Fail-on-base with `PYTHONPATH` pinned to a 654d734e archive.
- `pytestmark = pytest.mark.platform` on `test_lock_io.py`, the CRLF and
  Windows tests; classify every new file; label `test-all-os`.
- Mutation: the unreadable dispatch, `resolve_pinned_dependencies` skip
  and abort, the memo, the cause table, the `INFO` gate.
- Stderr sweep against `main` over `tests/fixtures/real-world-locks/`:
  identical but for decided wording and `[code]`; SBOM diff empty.
- Add a manual check (malformed `uv.lock`; a clean lock prints nothing).

## 8. Ratchet and CHANGELOG

316 to 268, by `--write-baseline` after the generator. `[Unreleased]`:
fold "lock file and dependency" into the Added message-code bullet
([#NNN]); Added "A direct reference is said, as an `INFO:` line, not to
be looked up on PyPI ([#NNN])"; Fixed "A `uv.lock` dependency missing from
its package table is warned of once ([#NNN])".

## 9. Agents

A first; B and C after A's entries; D last; Opus review, then a
fresh-context sweep. Each brief: British English, the Windows dry-run
checklist, section 2.2 verbatim.

- **A (Opus)**: `src/pitloom/messages/` only (`_lock_file.py`,
  `_lock_entry.py`, `_dependency.py`, `_fields_lock.py`, `_lock_say.py`,
  `lock_files.py`, `dependencies.py`, `_catalogue.py`, `_topics.py`,
  `_field_tables.py`); `scripts/message_inventory/_scope.py` (one
  `DETAIL_EXC` name).
- **B (Sonnet)**: `extract/lock/**`, `tests/extract/lock/**`.
- **C (Sonnet)**: `core/requirements.py`, `_dep_scope.py`, `deps.py`,
  `_poetry_requirements.py`, only the helper call lines of
  `_requirements_files.py`, `_setuptools_options.py`, `_poetry_extras.py`;
  their tests.
- **D (Sonnet)**: generator, baseline, docs, skills, CHANGELOG.
- **Haiku**: `%r` and `quote_source(lock_path)` left in `extract/lock/`
  (0); baseline delta per module.

Forbidden: a ratchet exemption by text; a condition not in `CONDITIONS`;
any level change (pylock:125 stays `WARNING`); `%r`; a helper adding a
prefix; dropping `warn_entries`, `quiet` or the `lock-unreadable` memo;
editing a generated page or the baseline; a block `pylint: disable`;
printing a direct reference's URL. Escalate to Opus: any new code, field
or table entry, an outcome unlike section 1, a test asserting a full line.

## 10. Questions (recommendation in brackets)

- Q1. `kept`/`dropped` as clause fields, not `KEPT=` keys? [Yes.]
- Q2. Code by fault location (`requirements.txt` lines are
  `lock-entry-*`)? [Yes.]
- Q3. `lock-entry-conflict` covers per-marker versions, advice by case?
  [Yes; a `/markers` variant needs markers carried through
  `resolve_pinned_dependencies`: follow-up.]
- Q4. `over-cap` (purpose `lock-file`), not "over N bytes" detail? [Yes.]
- Q5. `cascade.py:241` raises `InternalError`, with a drift test on
  `_LOCK_SOURCES` names? [Yes.]
- Q6. `dependency-name-ambiguous` for the #405 `INFO`? [Yes.]
- Q7. Fix the uv said-once bug here? [Yes.]
- Q8. Two topics, `lock-files` and `dependencies`? [Yes.]
- Q9, Q10. `loom fragment list` reading locks, and hashed
  `requirements.txt` ignored: roadmap notes, out of scope. [Yes.] Also
  noted: `pyproject.py:479` builds a provenance string by hand.

## 11. Family-12 contract (overview section 4)

Confirmed: 12 reuses `requirement-invalid` (`REQUIREMENT_INVALID`,
`pitloom.messages.dependencies`; `deps_installed.py:354`), the split rule
of 2.2, and the grid with `project-field-conflict` and
`dependency-version-conflict`. Amended: the helper call lines in
`_requirements_files.py:186`, `_setuptools_options.py:159`,
`_poetry_extras.py:235,243` are coded and reworded by 11; 12 does not
reword them. `package`, `dependency`, `extra`, `kept`, `dropped`,
`declared_in` and the two topics are not renamed during review of 8 to 12.

## 12. Amendments by agent A (maintainer ruling, 2026-11-17)

- Renamed fields: `extra` -> `extra_name`, `line` -> `line_number`. Both
  names are reserved: `emit` and the coded exceptions take `extra=` and
  `line=` (`tests/messages/test_model_stub.py`). The printed key stays
  `LINE=`.
- Two causes added to the cause table, both `requirement-invalid`:
  `undeclared-dependency` (`_poetry_extras.py:235`) and `unlisted-optional`
  (`_poetry_extras.py:243`).
- `lock-file-wrong-format` is one entry, effect thinner; a newer minor
  version is weaker, said in its summary, with no `/newer` variant.
- A `requirements.txt` version conflict ends `; no pins read from it,
  dropped <dropped>`.
- `value_type` takes the value itself, never its type's name.
- `why` is masked in `say_lock_entry` (the shared `why` writer does not
  mask).
- The `undeclared-extra` and `cycle` lines do not name the missing extra or
  the cycle's members (no new field).
- `_poetry_requirements.py:153` raises `_MarkersTypeError(TypeError)`, a
  `DETAIL_EXC` name.
- `_document_locked_deps.py:111` (the document's own guard, no lock file)
  says `LOCKED_VERSIONS_LINE` of `lock-entry-conflict`: `PACKAGE=<name>:
  pinned to several versions in the locked dependencies; skipped, dropped
  <dropped>`, with no `FILE=` (it printed `FILE=locked dependencies`).
- `uv.lock` workspace lines read `workspace entries: <n>, ...`, right for
  one entry and many.
- Review round: a `failure` on these lines is masked and cut to 120
  characters in the helpers; `lock-entry-malformed` lines that keep the
  pin end `..., pin kept` (`DEPENDENCIES_LIST_LINE` for an entry's own
  `dependencies`); the cause `marker` applies to an extra's entry only;
  `lock-entry-conflict`'s subject key is `PACKAGE`.
- `warn_lock_file_over_cap` is removed: the inventory scans one call deep,
  so `_lock_io.py` calls `warn_over_cap` with `lock_file_cap()` and
  `LOCK_FILE_OVER_CAP_OUTCOME`.

Helper signatures (B and C):

```text
say_lock_file(log, SHAPE_LINE, /, *, file=None, said=None, **values)
say_lock_entry(log, SHAPE_LINE, /, *, file=None, said=None, **values)
lock_file_cap(limit) -> Cap
warn_skipped_dependency(log, cause, *, dependency, declared_in,
    failure=None, source_kind=None, quiet=False)
warn_skipped_extra_entry(log, cause, *, extra, dependency, declared_in,
    failure=None, quiet=False)
warn_required_not_pep508(log, dependency)
warn_extra_gate_unusable(log, *, package, dependency, self_reference)
warn_extra_gate_ambiguous(log, *, dependency, extras)
say_direct_reference(log, package, *, said)
```

`file` is a path (its `.name` is printed) or a name; `None` only for
`LOCK_CONFLICT_LINE` and `LOCKED_VERSIONS_LINE`. `said` is a per-run `set` the caller makes.
