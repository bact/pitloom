---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-26
Last-Modified: 2026-11-27
---

# Message catalogue sweep C1: behaviour and correctness fixes (plan)

See also: [message-catalogue-sweep-c1-as-built.md](message-catalogue-sweep-c1-as-built.md)
(C1a and C1b as built, and the follow-ups left open),
[message-catalogue-sweep-b-plan.md](message-catalogue-sweep-b-plan.md)
(sections "Carried to sweep C or the rescan" and "For sweep C: the PR 17
onward range review", the sources of this plan),
[message-catalogue-sweep-plan.md](message-catalogue-sweep-plan.md)
(sweep A leftovers), [message-catalogue-agent-rules.md](message-catalogue-agent-rules.md).

Status 2026-11-26: built and merged as C1a #545 and C1b #550 (as built:
[message-catalogue-sweep-c1-as-built.md](message-catalogue-sweep-c1-as-built.md));
planned read-only by Opus against commit 4c194136 (main 4ef7961d plus
open #543). Sibling plans: sweep C2 (wording and quotes) and the
masking PR. Every item marked "reproduced" was run at 4c194136 (probe output
in the appendix of
[message-catalogue-sweep-c1-as-built.md](message-catalogue-sweep-c1-as-built.md#appendix-plan-probes-at-4c194136-abridged));
"read-only" items were read, not run.

**Recommendation in one line:** split C1 in two. **C1a** (behaviour fixes,
about 25 files, about 750 lines with tests) first; **C1b** (one rule: an
`except` never swallows `InternalError`; a helper, a lint test and a
scripted conversion of 187 handlers in about 106 files, about 300 lines)
after C1a and the masking PR. C1 leaves `logging_config.py` alone: the
masking PR splits it (ruling Q8).

## 1. Scope

Evidence: **R** reproduced at 4c194136, **RO** read-only.

### C1a: behaviour fixes

| Id | What | Where (4c194136) | Ev. | User-visible effect today | SBOM / stderr change |
| --- | --- | --- | --- | --- | --- |
| A1 | An empty path argument is read as `.` or fails uncoded | `core/wheel_dist_info.py:157` (`require_wheel_path` puts `''` in a `FILE=` field), `cli/commands/utils.py:83` (`existing_model_path`), `cli/commands/project.py:106`, `merge.py:76`, `generate.py:137` | R | `loom wheel ""` (also `verify-wheel`, `validate-wheel`, `embed-wheel`, library `generate_wheel_sbom("")`): uncoded `ERROR: ... file='' is not a file`. `loom enrich ""` names `'.'`. `loom merge ""` merges every `*.json` of the cwd; `loom project ""`, `loom generate -o x ""` scan the cwd; `-o ""` says `FILE=.` | stderr yes; SBOM: no longer written for `""` |
| A2 | Catalogue writers raise a plain `ValueError` on a caller's bug | `messages/_templates.py:69,76` (`written`), `messages/_types.py:285` (`line_for`), the field writers (`_field_writers.py:102,122,149,252,267,305`, `_fields_*.py`), `namespace_invalid` | R (via A1) | A1's uncoded line is this: a value outside its field's shape reads as a user's error | stderr: such a line becomes an `InternalError` (still uncoded, now named a bug) |
| A3 | A helper with one uncoded return branch | `extract/ai_model/reader.py:371` (`refusal_error`), inventory `scripts/message_inventory/` (judges a helper by its first coded return), `_coded.py` `STATIC_CALLS` omits `CodedOSError` | RO (reviewer reached it with a patched `read_lfs_pointer`; a race in practice) | An LFS pointer that vanishes between reads prints an uncoded `ERROR:` | stderr yes |
| A4 | Wrong-typed loom SDK arguments raise uncoded | `_loom_active_run.py:199-340`, `loom.py:188-338`, `_loom_dataset_meta.py:68` | R | `set_model(None)`, `path=5`, `add_dataset(5)`, `croissant=5`: uncoded `TypeError`; `set_model_hyperparameters(["a"])`: `AttributeError`; `data_preprocessing="tok"`: bindings `TypeError`; `declared_license=5`: uncoded `TypeError` (on purpose since 17b) | stderr yes |
| A5 | `input_datasets` given as a string, or with unhashable entries | `_loom_active_run.py:311,376` | R | `input_datasets="a.txt"` links `a` and warns for `.`, `t`, `x`, `t` (five `reference-not-found/dataset` lines); `[["a.txt"]]` raises an uncoded `TypeError` at the run's exit, no fragment | SBOM (wrong links) and stderr |
| A6 | An unknown `dataset_type` is recorded as `text` | `_loom_dataset.py:106-112` (`getattr(..., text)`) | R | `dataset_type="bogus"` gives `["text"]` silently; `"__module__"` raises the bindings' uncoded `ValueError` | SBOM yes (no longer `text`), stderr yes |
| A7 | The current directory gone | `_loom_active_run.py:130` (`Path.cwd()` for `resolve_registry`), `:153` (`os.path.abspath`), `cli/commands/project.py:164` and `merge.py:84` (`default=Path.cwd()` evaluated when the parser is built) | R | `loom.run()`: uncoded `FileNotFoundError` at `__enter__`. **New:** every `loom` command prints a Python traceback, even with absolute paths, because building the parser calls `Path.cwd()` | stderr yes |
| A8 | A loom fragment write that fails is a bare `OSError` | `_loom_active_run.py:457-460` (`mkdir`, `write_text_lf`) | R | `loom.run("ro/frag.json")`: uncoded `PermissionError` | stderr yes |
| A9 | A NUL byte in `croissant=` | `extract/_extract_utils.py:265` (`fetch_json` catches `OSError`/`HTTPException` only) | R | uncoded `ValueError: embedded null byte` | stderr yes |
| A10 | A too-long name on the model routes | `cli/commands/utils.py:83-91` (`existing_model_path`, `Path.exists`), the `model` route | R (3.10, 3.11, 3.13 macOS) | `loom enrich`/`loom model` `<300 chars>.gguf`: uncoded `[Errno 63] File name too long`; `project`, `merge`, `verify-wheel`, `fragment validate` say `file-unreadable ... for the input check`; 3.14 and Windows read it as missing | stderr yes |
| A11 | One namespace credential, two codes | CLI `id generate --namespace` (argparse `type=`) vs `IdRegistry(namespace=)` | R | CLI `option-invalid`, library `credentials-unsafe/registry` | stderr (code) yes |
| A12 | `PitloomConfig(sbom_basename=)` checked late and misnamed | `core/_config_types.py:173,212`; `_embed_generate.py:353,402` | RO | warns as a `[tool.pitloom]` key; `embed_wheel_sbom` refuses it as `sbom_filename` after generating | stderr yes |
| A13 | One script named two ways in a fragment | `_loom_caller.py:156` (`path.resolve()`), `_loom_active_run.py:153` | R | run through a symlink `link.py -> real/s.py`: `software_File` `real/s.py`, every provenance `Source: link.py` | SBOM yes |
| A14 | Tooling gaps (no runtime change) | `tests/test_licenseid_floor_docs.py:52` (first `licenseid>=` only, no `src/` docstrings); `scripts/manual_cli_checks/_checks_loom.py:179` (`startswith(TAGS)`, not `line_kind`); `messages/_line_kind.py:101` (`UNSHOWN_MESSAGE` plus a catalogued code read as `uncoded`) | R (read and grep) | none | no |
| A15 | Strict check misses module/class/session fixture records | `tests/_strict_uncoded.py:49` | RO (documented gap) | none; may surface hidden uncoded lines | no (tests only) |

### C1b: `InternalError` is never swallowed

| Id | What | Where | Ev. | Effect | Change |
| --- | --- | --- | --- | --- | --- |
| B1 | Broad handlers that can catch `InternalError` (a `ValueError`) | AST count at 4c194136: 214 handlers catch `ValueError`, `Exception`, `BaseException` or bare; 16 already guard, 11 re-raise; **145 swallow** and **42 convert** it (`raise Coded...(...) from exc`, e.g. a reader's `model-malformed`) in 106 files. `extract/ai_model`: 37 of them (19 swallow, 18 convert); the "about 200" of the source note was every handler in `src/`, not the readers alone. The 8 listed sites are all in the 187 | R (AST count; probe `c1probe/excepts.py`) | A bug in Pitloom is said as a user's bad file, an "authors unread" warning, a silently empty field (`deps_pypi.py:192` `future.result()` to `None`) or a debug line | stderr only when a bug fires; no SBOM change on a correct tree |

## 2. Out of scope, and where each goes

| Item | Goes to |
| --- | --- |
| `dataset-conflict` said twice; conflict lines name no model; metadata-budget `over-cap` reads as the model file; dependency's over-cap author names no package; `author-invalid` "not an email address"; `generate_env_sbom` `Raises:`; `iri.namespace_problem` docstring order; repeated `input_datasets` name warned per repeat; non-string value quoted like a name | **C2** (wording; the conflict lines change one message's subject and count together) |
| `Bearer%20` quadratic masker, request-id glue, `one_line` collapse before masking, header credential after a line break | **masking PR** |
| `_counted_entries` duplicates `_fields_authors._entries_text` | C2 (same files as the author wording) |
| Inventory: `_module_bindings` misses `global` rebinding; tuple unpacking and returned values not followed; ratchet blind spots (`warnings.warn`, `sys.stderr.write`, `raise <local>`, `getattr(log, ...)`, aliased `print`, positional upper-case constants, `pitloom_code: None`) | **consistency rescan** (A3 takes only "judge each return expression" and `STATIC_CALLS`) |
| Argparse wording `usage_code() is None` on 3.11-3.14; summary regex 0.4 s at the cap | rescan |
| Hub `log.debug` of `exc.request_id` | masking PR (optional) |
| Splitting `logging_config.py` | masking PR (ruling Q8) |
| `stated_count` placeholders, path cutting, docs over 30 KB | as already routed (rescan, own PRs) |

## 3. Rulings needed

**Ruled 2026-11-26 by the maintainer: every recommendation accepted.**
Q1 (a) split by role; Q2 (a) missing everywhere; Q3 (a) `CodedTypeError`;
Q4 (a) refuse at the call; Q5 `credentials-unsafe/registry` on both
surfaces; Q6 (a) as invoked; Q7 (a) `reraise_internal` plus an AST lint, in
one PR by a re-runnable script; Q8 (a) the masking PR splits
`logging_config.py`; Q9 probe report-only first.
C2 ruling 10 (same day) routes R1 here, with A5: `reference-not-found/dataset`
says each missing name once per output dataset, in first order, and its
`a value of type` branch goes once A5 refuses non-str entries at the call.

**Q1. An empty path argument.** (a) An empty *input* path is
`input-not-found` on every surface (as `ls ""` and `os.stat("")` say), and
an empty `-o`/`--project-dir`/`--id-registry` is `option-invalid`
(`must be a non-empty string, got ''`, the existing `non-empty` id); the
Action maps an empty `project-path` to `.` itself. (b) `""` means `.`
everywhere (today's accident, made explicit). (c) Refuse every empty path
argument as `option-invalid`. **Recommend (a)**: `loom merge ""` merging the
cwd and `loom project "$DIR"` with `DIR` unset scanning the cwd contradict
the user's intent (AGENTS "honour user intent"); a library caller and a CLI
user get the same code. The Action keeps its default because
`action.yml:358` passes `"${PL_PROJECT_PATH}"` to `loom project` and an
explicit `project-path: ""` would otherwise now fail.

**Q2. A name too long to exist (`ENAMETOOLONG`).** (a) Missing everywhere:
`is_missing_errno` counts it, so every route says `input-not-found`, as
Windows and Python 3.14's `Path.exists` already do. (b) Keep
`file-unreadable` on the routes that say it and route `model`/`enrich`
through `input_exists` so they say it too. **Recommend (a)**: a name the
file system cannot hold names nothing; one rule on every OS and Python.
Check `is_missing_errno`'s callers first (a scan's `except` would then skip
quietly, which is right for "absent").

**Q3. Wrong-typed loom SDK arguments.** (a) A new `CodedTypeError`
(`_CodedError, TypeError`) carrying `option-invalid`
(`LOOM_SDK_VALUE_LINE`), checked at the facade; `declared_license`'s
`TypeError` becomes it (still a `TypeError`, now coded); the pr17b ruling
"`TypeError` is internal" stays for Pitloom's own code. (b)
`loom_sdk_invalid_value` (a `ValueError`) for all. (c) Keep uncoded.
**Recommend (a)**: a caller's wrong type is a user's input reaching a
message (agent rules: "a raise a user can reach needs a code"), and a
`TypeError` is what a Python caller expects; (b) would change the
documented `declared_license` contract.

**Q4. An unknown `dataset_type`.** (a) Refuse at the call
(`option-invalid`, a new `EXPECTED` id `one-of-dataset-type` listing the
SPDX terms; exact spelling, terms only, never `getattr` on the class). (b)
Warn and record `noAssertion`. **Recommend (a)**: the call is made before
training starts, a typo fails fast, and recording any type the caller did
not say is a silent deviation.

**Q5. A credential in a namespace.** **Recommend** the CLI says
`credentials-unsafe/registry` (the cause, and the code a skill explains);
alternative: both `option-invalid`. The CLI line keeps its
`argument --namespace:` frame only if the frame allows that exact code.

**Q6. One name for a script run through a symlink.** (a) Both the
`software_File` and the provenance label name it as invoked (`link.py`,
lexical, through `cwd_relative_label`). (b) Both name the resolved file.
**Recommend (a)**: every other path keeps the user's spelling
(`given_spelling`); the label must not depend on where a link points.
Changes SBOM output for symlinked scripts only.

**Q7. C1b scope.** (a) One rule for every broad handler in `src/`, through
a helper `reraise_internal(exc)` as the handler's first statement, enforced
by an AST lint test with a reasoned allowlist. (b) A preceding
`except InternalError: raise` clause. (c) Make `InternalError` a
`BaseException`. **Recommend (a)**: the helper call runs whenever the
handler does, so it adds no uncovered branch (b adds 187 lines no test
reaches, against the branch-coverage rule); (c) would let a library
caller's `except Exception` miss a Pitloom bug and reverses the documented
"a `ValueError`, so a caller that catches one still does". Allowlist
categories, each with a reason in the test: top-level reporters
(`cli_error_handler`, the hook catch-all), never-raise contracts
(`log_masking.py`'s 7, logging formatters), cleanup that re-raises later in
the handler (`_models_wheel_build_kill.py`). Also: is C1b's ~106 files
acceptable as one mechanical PR (as B2's 26 one-line markers were), or
split by package (`extract/` 60-ish files, the rest)? **Recommend one PR**,
the conversion done by a re-runnable script so a rebase is cheap.

**Q8. `logging_config.py` (503 lines).** (a) The masking PR splits it, as
a pure-move first commit (the one-line and failure-text helpers,
`one_line`, `failure_reason`, `excerpt`, `EXCERPT_CHARS`,
`field_loss_suffix`, `_QUOTED_VALUE`, to their own module with re-exports),
then edits `one_line` there. (b) C1a splits it and the masking PR rebases.
(c) A tiny split PR after both. **Recommend (a)**: the masking PR is the
only one of the three that edits those helpers, so a move and an edit in
one PR has no conflict; C1 does not touch the file.

**Q9. Strict-check fixture scopes (A15).** **Recommend** build the
`pytest_fixture_setup`/teardown hookwrapper in report-only mode first; if it
finds no uncoded record, turn it on in C1a; if it finds some, carry the
findings and the hook to the rescan rather than grow C1a.

## 4. Design per item

**A1 empty path.** One helper `refuse_empty_input(given, kind)` in
`messages/_input_not_found_say.py`: raises `input_not_found(kind, given)`
when `os.fspath(given_spelling(given)) == ""`. Called once at each public
entry that takes an input path, before any format check: the library
`generate_wheel_sbom`, `generate_model_sbom`, `enrich_model`,
`generate_project_sbom`, `generate_merged_sbom`, `embed.embed_wheel_sbom`, the
verify/validate wheel entries, `require_wheel_path` (so every wheel
surface shares it), `existing_model_path`, `_project_target` (before
`TypedPath`), `loom merge`'s directory, `loom id generate`/`import`. For
`-o`, `--project-dir`, `--id-registry`: one argparse `type=` callable
`non_empty_path` in `cli/` (wrapping `TypedPath`) raising
`ArgumentTypeError(must_be("non-empty", got=text))`, the shape
`usage_code()` already codes `option-invalid`. `action.yml:358`: pass
`"${PL_PROJECT_PATH:-.}"`. Docs: `docs/` and skills quote no `''` line
(grep `is not a file`, `'.'` in `skills/`); add none.

**A2 writers.** `written()`, `Message.line_for()`, `render()` and every
field writer raise `InternalError` (still a `ValueError`) for a value
outside its shape; update their `Raises:`; `namespace_invalid`'s plain
`ValueError` likewise. Tests that `raises(ValueError)` keep passing.

**A3 helper branches.** `refusal_error`'s last branch returns
`file_unreadable_error(OSError-less form)`: add a line to `file-unreadable`
only if no existing line fits; prefer `LFS_POINTER_MALFORMED` with the
reason as its failure (a pointer that changed between reads is a malformed
read). Inventory: a helper counts as coded only when every return
expression is coded (`scripts/message_inventory/`); add `CodedOSError` to
`_coded.py` `STATIC_CALLS`. Baseline may rise by the sites this exposes:
fix them in the same step, never raise the ratchet.

**A4 SDK types.** One table and one check in `_loom_active_run.py` (or a
new `_loom_args.py` if the file passes 500 lines; it is 526 now, so **new
module**): `check_sdk_arguments(call, **values)` mapping each parameter to
an `EXPECTED` id (`string`, `non-empty`, new `path-or-none` = "a path (str
or os.PathLike) or None", new `list-of-strings`, new `mapping-of-strings`,
`boolean`), raising `CodedTypeError(OPTION_INVALID,
line=LOOM_SDK_VALUE_LINE, ...)`. Every SDK method calls it first. New
`EXPECTED` ids regenerate the values page (#499).

**A5 `input_datasets`.** In the same table: `None` or a `list`/`tuple` of
`str` (`list-of-strings`); refused at the call, so nothing is hashed at
exit.

**A6 `dataset_type`.** `_dataset_kind` looks the name up in the enum's
term names only (a frozenset built from the binding's named individuals,
not `getattr`); unknown raises `option-invalid` `one-of-dataset-type` at
the call (Q4).

**A7 cwd gone.** One helper `current_dir()` in `core/` returning
`Path.cwd()` or raising `file_unreadable_error(exc, dir=".", use=CWD_USE)`
through the existing `DIR_READ_LINE` shape at `ERROR` (add an `ERROR`
sibling line if none, `since` 0.25.0). Used by `_ActiveRun.__init__` (both
`Path.cwd()` and the `abspath`, which becomes `current_dir() / script`),
and by the parser: `default=None` for `project_dir` and merge `-o`,
resolved inside the command, so the parser builds with no cwd. A grep for
`Path.cwd()`/`os.getcwd()` in `add_argument` defaults is the guard test.

**A8 fragment write.** `finalize()` wraps `mkdir` and `write_text_lf`
through the shared coded write (`_sbom_io`'s `file-unwritable` path, as
sweep A moved `_coded_write` into `write_sbom_output`) with a new `use`
value `FRAGMENT_USE = "for the SBOM fragment"` in
`messages/_field_tables.py`.

**A9 croissant NUL.** Probe the path through `_input_stat` (a NUL is
"nothing there") before `fetch_json`'s open, so `croissant="a\x00b"` gets
the existing croissant not-a-file refusal; and `fetch_json` catches the
`ValueError` of `os.stat`/`open` for a local path as that refusal.

**A10 long names.** Q2(a): `is_missing_errno` adds `ENAMETOOLONG`;
`existing_model_path` probes through `input_exists(given, shown=target)`
instead of `Path.exists()`; the `model` route's first stat likewise.

**A11.** The CLI `--namespace` `type=` calls the library's namespace check
and re-raises its coded error's text with the library's code (Q5).

**A12.** `PitloomConfig.__post_init__` checks `sbom_basename` with
`sbom_base_name(value, Parameter("PitloomConfig.sbom_basename"))`, as
`max_dataset_hash_bytes` is checked; the `[tool.pitloom]` parse keeps its
own place.

**A13.** `_get_caller_script_path` returns the lexical label
(`cwd_relative_label(filename)`, no `resolve()`); the absolute path kept
for hashing is `current_dir() / filename` (A7), opened as given.

**A14.** Floor test: every `licenseid>=` in `pyproject.toml` must agree
(assert one distinct pair) and `src/**/*.py` joins the scanned texts.
`_checks_loom.py:179`: `line_kind(line) != "untagged"` via the shared
classifier (as `universal()` does). `line_kind`: `UNSHOWN_MESSAGE` text plus
a catalogued `[code]` is `coded`; drop the one test allowance it needed.

**A15.** See Q9.

**B1.** `core/internal_error.py`: `reraise_internal(exc: BaseException) ->
None` (`if isinstance(exc, InternalError): raise exc`). Lint
`tests/core/test_internal_error_reraised.py`: AST walk of `src/pitloom`,
every handler catching `ValueError`, `Exception`, `BaseException` or bare
must (i) follow an `except InternalError` in the same `try`, (ii) start
with `reraise_internal(<its name>)`, (iii) end in a bare `raise`/`raise
<its name>`, or (iv) be on the allowlist `(file, function, line text)` with
a reason; a stale allowlist entry fails. Conversion: a script (kept in the
PR description, not the repo) adds `as exc` where missing and the call as
first statement; `report_wheel_failure`'s own check stays (it is (ii)'s
equivalent). The 5 "already guarded" sites keep their clause.

Catalogue: new `EXPECTED` ids (A4-A6), a `use` value (A8, A7), possibly one
`ERROR` line (A7) with `since` = 0.25.0; regenerate
`docs/message-codes*.md` and the values page; drift quotes in skills: grep
`loom SDK:` and `could not write` in `skills/` and `docs/loom*.md`.
CHANGELOG: one C1a bullet ("empty and too-long paths, the loom SDK's
argument checks, a missing current directory and fragment writes are
coded"), one C1b bullet only if user-visible (it is not: internal).

## 5. Tests per item (each fails on 4c194136)

| Id | Test (file) | Input | Assertion | Marker |
| --- | --- | --- | --- | --- |
| A1 | `test_empty_input_is_not_found` (`tests/cli/test_empty_path.py`), parametrised over every subcommand's positional path argument **discovered from the parser** (walk `add_parser` subparsers; a new command is covered automatically) | `""` | exit 1, one line ending `[input-not-found]`, no SBOM written, cwd unchanged | `platform` |
| A1 | `test_empty_output_option_invalid` same file | `-o ""`, `--project-dir ""` | `[option-invalid]`, `non-empty` | `platform` |
| A1 | library: `test_library_empty_path` (`tests/test_library_empty_path.py`) | `generate_wheel_sbom("")`, `generate_model_sbom("")`, `enrich_model("")`, `generate_project_sbom("")` | `CodedFileNotFoundError`, code `input-not-found` | `platform` |
| A1 | Action: `tests/scripts/action/` case | `project-path: ""` | `loom project .` invoked | - |
| A2 | `tests/messages/test_templates.py` | `written(t, {"file": ""})`, an `int` for a path field | `raises(InternalError)` | - |
| A3 | `tests/extract/ai_model/test_reader_refusal.py` | each `refusal_reason` value incl. a pointer re-read failure (patched) | every return carries `pitloom_code`; inventory fixture with a two-branch helper counts one uncoded | - |
| A4 | `tests/test_loom_sdk_argument_types.py` parametrised over the 8 reproduced calls (ids short) | `set_model(None)`, `path=5`, ... | `TypeError` with `pitloom_code == "option-invalid"`, line `loom SDK: <param>: must be ...`; adversarial: `bool` for a string, `Path` accepted for `path`, `bytes` path refused | - |
| A5 | same file | `input_datasets="a.txt"`, `[["a"]]`, `("a",)` | first two refused at the call (no fragment link to `a`), tuple accepted | - |
| A6 | `tests/test_loom_dataset_type.py` | `"bogus"`, `"__module__"`, `"Text"`, `"text"`, `"noAssertion"` | first three `option-invalid`; last two recorded | - |
| A7 | `tests/test_loom_cwd_gone.py` | chdir into a removed temp dir; `loom.run(abs)`; CLI `loom wheel <abs>` in a child (`run_loom`) | coded `file-unreadable`, no traceback; CLI parses | `platform` (POSIX only: Windows cannot remove the cwd; one short-circuited module constant) |
| A8 | `tests/test_loom_fragment_write.py` | read-only parent dir (spy `os.chmod` on Windows per AGENTS) | `pitloom_code == "file-unwritable"`, `for the SBOM fragment` | `platform` |
| A9 | `tests/test_loom_croissant_path.py` | `croissant="a\x00b.json"` | the croissant refusal's code | `platform` |
| A10 | `tests/cli/test_long_names.py` | 300-character name on `model`, `enrich`, `wheel`, `project`, `merge`, `fragment validate`; `is_missing_errno(ENAMETOOLONG)` | `input-not-found` on every route; a version-independent probe (os.stat, not `Path.exists`) | `platform` |
| A11 | `tests/cli/test_id_namespace_credentials.py` | CLI and library with `user:ghp_...@` | same code on both, token masked on both | - |
| A12 | `tests/core/test_config_types.py` | `PitloomConfig(sbom_basename="a/b")` | `option-invalid` naming `PitloomConfig.sbom_basename` at construction | - |
| A13 | `tests/test_loom_caller_symlink.py` | script run through a symlink | `software_File.name` equals the provenance label `link.py` | `platform` (symlink privilege on Windows: skip if `os.symlink` fails) |
| A14 | floor test: a second `licenseid>=` with another floor in a fixture text fails; a docstring floor in a temp `src` copy fails; `line_kind` UNSHOWN case | - | - | - |
| B1 | `tests/core/test_internal_error_reraised.py` (lint, fails on base listing 187 sites); `reraise_internal` unit test; behavioural: `deps_pypi` future raising `InternalError` propagates; a reader whose helper raises `InternalError` is not `model-malformed`; `_embed_overlay` per-wheel authors read | as listed | as listed | - |

Every new test: classify with `pytest <file> -m platform --collect-only -q`.

## 6. Build steps and agents

C1a (one branch, `catalogue-sweep-c1a`):

1. **Opus P (paths and cwd)**: A1, A2, A7, A10, A14 floor test. Fence:
   `messages/_input_not_found_say.py`, `messages/_templates.py`,
   `messages/_types.py`, `messages/_field_writers.py`, `messages/_fields_*.py`,
   `core/wheel_dist_info.py`, `core/path_probe.py`, a new
   `core/current_dir.py`, `cli/commands/{utils,project,merge,generate,model,enrich}.py`,
   `cli/parser.py`, a new `cli/_path_args.py`, `action.yml`, their tests.
   Opus: cross-surface ordering (existence before format), the Action, and
   errno rules across OS and Python.
2. **Opus S (loom SDK)**, after P lands `current_dir()`: A4, A5, A6, A8,
   A9, A12, A13. Fence: `loom.py`, `_loom_*.py`, a new `_loom_args.py`,
   `messages/_emit.py` (`CodedTypeError`), `messages/_config_place.py`,
   `messages/_field_tables.py`, `extract/_extract_utils.py`,
   `core/_config_types.py`, their tests. Opus: a public API contract change
   and SBOM output (A6, A13).
3. **Sonnet T (tooling)**, parallel with S: A3 inventory part and
   `STATIC_CALLS`, A14 `_checks_loom.py` and `line_kind`, A11. Fence:
   `scripts/message_inventory/`, `scripts/manual_cli_checks/_checks_loom.py`,
   `messages/_line_kind.py`, `cli/id.py`, `extract/ai_model/reader.py`.
   Sonnet: each to a clear spec.
4. **Opus F (A15 probe)**, report-only, parallel: `tests/_strict_uncoded.py`,
   `tests/conftest.py`. Opus: pytest hook ordering and xdist.
5. **Sonnet R**: regenerate the reference and values pages, CHANGELOG,
   grep `skills/` and `docs/` for changed lines; **Haiku** the stale-wording
   grep (`is not a file`, `loom SDK:`, `could not write`).

C1b (branch `internal-error-reraised`, after C1a and the masking PR merge):

6. **Opus I**: helper, lint test, allowlist with reasons (judgement per
   site in the three categories). **Sonnet C**: the conversion script and
   its run on the tree; **Haiku**: count check (lint passes, 0 left).

## 7. Gates

- **Tier 1** per round: touched tests (`-k`), `ruff`, `mypy`, `pylint`
  on touched dirs, `message_inventory --check`, reference `--check`, an
  stderr/SBOM diff of the A1/A5/A6/A13 probes vs main.
- **Gate A**: full suite `-n 4`; every CI linter (ruff format/check,
  pylint `examples/ src/ tests/ tests/*/`, mypy, pyright with
  `--pythonpath`, pyrefly, bandit, flake8); `--cov-branch` 100% on changed
  files; inventory, ratchet, reference and drift tests; each regression
  test run with `-o pythonpath=` against an untouched 4c194136 copy and
  seen failing; `shellcheck -x`/`actionlint` for `action.yml`.
- **Gate B**: mutation on `refuse_empty_input`, `current_dir`,
  `check_sdk_arguments`, `_dataset_kind`, `is_missing_errno`,
  `reraise_internal`, the lint's four exemptions, `line_kind`'s UNSHOWN
  rule; manual checks `--only` the loom, wheel, model/enrich, project,
  merge, id and action ids, then the full run `-j 8`; Windows dry run:
  `""` and long names (`WinError 206` is `FileNotFoundError`: A10 must
  still say `input-not-found`), the cwd test skipped by a module constant,
  chmod spied, symlink privilege, `PureWindowsPath` for the A13 label; a
  fresh-context Opus review of the whole diff; a fresh read of changed
  `SKILL.md`s. Label `test-all-os` on both PRs.

## 8. Risks (highest first) and size

1. **A1 changes what `""` does** (merge and project no longer read the
   cwd): a script relying on it breaks. Mitigation: Q1, the Action fix,
   a CHANGELOG line.
2. **B1 changes failure routes broadly**: a handler that swallowed a real
   `InternalError` on some input now aborts the run. That is the point,
   but a currently-hidden bug could surface at release time; run the
   manual checks and the real-world fixtures under B1 before merge.
3. **A2 can expose `InternalError` where a test expected a user error**;
   the suite shows which.
4. **A6/A13 change SBOM output** (a dataset type no longer `text`; a
   symlinked script renamed): determinism holds, the CHANGELOG says so.
5. **A10 `is_missing_errno` widening** makes a scan skip a too-long name
   quietly: correct under "absent is not an error", checked by its callers'
   tests.

Size: C1a about 25 source files plus about 14 test files, about 450 src and
450 test lines (over 800 in total with tests): **if it lands over 900
changed lines, split off A14 and A15 (tooling) as C1a-2**. C1b about 106
files, about 300 lines (190 one-line calls, a lint test of about 150).

## 9. Overlap with the other two PRs

Order: masking (#544), C1a (#545), C2 (#546, #548), C1b, all but C1b merged
on 2026-11-26. The original overlap analysis is in
[message-catalogue-sweep-c1-as-built.md](message-catalogue-sweep-c1-as-built.md#plan-section-9-overlap-as-planned).
