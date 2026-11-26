---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-26
Last-Modified: 2026-11-26
---

# Message catalogue sweep C1: as built

See also: [message-catalogue-sweep-c1-plan.md](message-catalogue-sweep-c1-plan.md)
(the plan, its rulings Q1-Q9 and the per-item design this records the
differences from).

## C1a as built (PR #545, 2026-11-26)

Built as planned, with these differences (plan claims found wrong are
marked):

- **A1**: the empty-input rule lives in the input probe
  (`messages/_input_not_found_say._input_stat`: an empty spelling is
  nothing there), so every surface reaching `input_exists`/`is_input_file`
  shares it; `refuse_empty_input` covers the entries that never probe
  (`require_wheel_path`, `generate`, the model and project entries, `loom
  id`, the loom `pitloom_config=`). An empty `-o`, `--project-dir`,
  `--id-registry` (CLI) and `loom.run("")`/`id_registry=""` (SDK) are
  `option-invalid` `non-empty`. `loom id generate ""` is checked where any
  missing PATH is, so both say `option-missing` without a registry.
- **A2**: `namespace_invalid` is in `messages/_options_say.py`, not
  `core/iri.py` (plan wrong).
- **A10**: ENAMETOOLONG is "missing" only when a component is longer than
  255 bytes (`path_probe.names_too_long_component`): a whole path past
  PATH_MAX whose parts exist is still a read failure (a scan warns
  `dir-unlistable`), as the ruling's "a name the file system cannot hold"
  means. An empty library `output_path` or `id_registry` (and
  `[tool.pitloom] id-registry = ""`, `config-invalid`) is refused first,
  as on the CLI.
- **A3**: the inventory took the best kind of any call in a helper's body,
  not "the first coded return" (plan wrong); now every return branch
  (`IfExp`, `BoolOp`, each assignment of a returned name) is judged, and a
  recursive call is neutral. `_render.py` no longer recurses forever on a
  parameter passed through a recursive call (pre-existing crash).
- **A7**: `file_unreadable_error(dir=".")` cannot carry a gone cwd (ENOENT
  is refused as absent, plan wrong): `current_dir_error` and an `ERROR` `DIR=`
  line say it. `resolve_registry` takes `None` for "the current directory,
  read only when a relative registry needs it", so an absolute-path run never
  reads the cwd. `id_registry/_registry.root_dir()` keeps `os.getcwd()`: its
  callers degrade on `OSError` by contract.
- **A8**: `READ_USES` is the one `use` vocabulary for reads and writes;
  `FRAGMENT_USE` joins it.
- **A9**: a NUL in a local `croissant=` is `input-not-found`, read by
  `_extract_utils._read_local`; other refusals keep `for the Croissant
  document`.
- **A11**: the `argument --namespace:` frame cannot carry
  `credentials-unsafe/registry`, so `loom id generate` checks the namespace
  with the library's `require_registry_namespace` after parsing (exit 1).
- **A12**: `PitloomConfig` configures logging only when its basename will
  warn (`file_names.bare_sbom_base`), so a library caller's logger is kept.
- **A15**: the report-only full run found 0 uncoded records in wider-scoped
  fixtures; the check is on, installed when `tests/conftest.py` is imported.
- **R1** (C2 ruling 10): each missing `input_datasets` name once per output.

### Follow-ups (not in C1a)

Done in C1b: the relative path with the cwd gone, blank `generate("   ")`,
`IdRegistry.load("")`/`save("")`.

- A RELATIVE path with the current directory removed still fails uncoded
  where it is resolved before any probe: `cli/id.py`
  (`_normalized_absolute`, a relative `--project-dir`, `id import`'s
  `.resolve()`), `_embed_generate.py`, `_embed_wheel_batch.py`
  (`Path(project_dir).resolve()`), `id_registry/resolve.py`,
  `_loom_caller.py` (`os.getcwd()`); a relative project path then says
  `input-not-found`, not `DIR=.`.
- `generate("   ")` (blank, not empty) strips to `""` and reads the cwd; the
  CLI names `'   '` as not found.
- `tests/extract/project/test_setuptools_hostile.py::test_a_long_unread_value_is_cut_in_the_warning`
  fails under a long `--basetemp` (the path is part of the cut text).
- The inventory still takes the best kind of the calls inside one value
  (`ValueError(str(CodedValueError(...)))` reads coded).
- `tests/messages/test_drift_strict.py` is 519 lines: split the child-pytest
  tests out.
- `discovery_chdir`'s gone-cwd line says "for resolving relative paths".
- `IdRegistry.load("")` names `.`, and `IdRegistry.save("")` raises an
  uncoded `ValueError`; `Path("")` cannot be told from `.` anywhere.
- `NAME_MAX_BYTES` counts bytes: an APFS name of 128-255 non-ASCII
  characters inside a path past PATH_MAX would read as missing.

## C1b as built

PR #550, 2026-11-26. Ruling Q7 (a), one PR. Re-measured at 785a40db: 214 broad handlers (141
swallow, 47 convert, 3 mixed, 11 re-raise, 12 guarded) in 110 files, plus 4
broad `contextlib.suppress` calls and 2 handlers catching a module constant
holding `ValueError` (`_usage_attach.PARSE_ERRORS`, `hdf5._READ_ERRORS`) that
a name-only probe misses. Size close to the plan, so no split.

- **Helper**: `core/internal_error.reraise_internal(exc)`; 162 handlers in 99
  files start with it (a re-runnable conversion script, kept out of the repo:
  adds `as exc` where missing, puts the call right after the `except` line,
  sorts the import).
- **Lint** `tests/core/test_internal_error_reraised.py`: resolves each
  `except` type in its module's namespace (a constant or an import is seen
  through; a local name falls back to its spelling). Only the first clause of
  a `try` that catches an `InternalError` is checked (a later one never sees
  one). Exemptions: starts with `reraise_internal(<name>)`; ends in bare
  `raise`/`raise <name>`; ends in `raise InternalError(...)` (it adds
  context: `provenance.build_provenance_annotation`, `_http_errors.warn_instead`,
  `Cap.__post_init__`); `extract/ai_model/formats/` (imports nothing of
  Pitloom's); an allowlist by (file, function) with a reason, 24 entries:
  the CLI's catch-all, `log_masking`'s 6 functions (never raise on the
  logging path), the build kill path's 4 (held, raised later), 2 thread
  entries that re-raise in the caller, `_usage_parse._hooked_call` (runs
  while a trace hook may be set: a Python call there is one a hook can
  abort), `rmtree_quietly`, `_remove_work_dir`,
  `_isolated_sys_modules`, the unlistable audit hook, `build_signals._arm`
  and `_restore`, and 4 argparse `type=` callables (argparse turns any
  `ValueError` into "invalid value", exit 2). `suppress`: 2 entries in
  `build_signals` (signal handler, cleanups); a stale entry fails.
- **Not swallowed, but not plain insertion** (Opus classification):
  - setuptools' missing private piece (`_models_wheel_setuptools_clone._private`)
    raised `InternalError` as control flow for an environment condition: now
    `BackendPieceMissingError` (`_models_wheel_types`), the discovery still
    warns and falls back; in the ratchet's `DETAIL_EXC` with its proof case.
  - `Cap.of_model` caught `InternalError` to drop a library caller's label:
    now checks the `format` field's shape first.
  - `_git_redirect._probe_within`'s thread hands an `InternalError` back to
    the caller's thread, which raises it (before: an untagged traceback from
    `threading.excepthook` and "no answer in time").
  - `_license_detect._shown` and `_pyproject_license._as_written`:
    `suppress(ValueError)` around `relative_to` became `is_relative_to`.
- **Route tests** `tests/core/test_internal_error_routes.py` (fail on base):
  the PyPI prefetch future, the Safetensors reader (was `Failed to read`),
  the embed's project authors (was "authors unread") and the redirect probe.
- **C1a follow-ups done**: a relative path with the cwd removed is the coded
  `DIR=.` line on every route probed (`core/current_dir.absolute_path`, used
  by `loom id`, `embed-wheel`, `project`, `generate`, `merge`, `enrich`,
  `fragment`, `wheel`, the wheel checks, `--id-registry`, the Git URL
  route's `id_registry`, `IdRegistry.save` and the `-o` write; the input
  probe and `read_project` check the cwd for a relative path that is not
  there): `tests/test_cwd_gone_relative_paths.py`, 31 cases, POSIX only. Blank
  `generate("   ")` is `input-not-found` naming `'   '`, as the CLI says;
  `IdRegistry.load("")` names `''`, `IdRegistry.save("")` is
  `option-invalid` `non-empty` (and no longer writes to the registry's own
  path). `Path("")` still cannot be told from `.`.
- **#548 delta points**: a drift guard pins one `FILE=` for a model's
  `over-cap` line and its `dataset-conflict` line
  (`tests/messages/test_dataset_conflict_sites.py`). GGUF naming kept as is
  (plan C2 section 11), on two fresh Opus opinions that agree: while a reader
  runs only `file_name` is set, so `shown_path` there is `file_name` (a
  no-op); passing the path as handed would split the reader's line from the
  assembler's in a direct `read_gguf()` call and move a wheel's rewrite from
  the field-aware `named_stably` to `scrub`'s free-text replace; every relayed
  route already prints one `FILE=` per model; no SBOM change either way.
- **Rulings from the parent session** (the user asked for no stops): no
  split, GGUF as above; the cwd follow-up widened to every CLI site the probe
  reached, as the same bug.

- **`report_wheel_failure`** keeps its own guard as a `reraise_internal`
  call (its callers' handlers start with one too, so its old `if` was dead).
- **Gates.** Two fresh Opus review rounds (round 1: `_hooked_call`'s
  insertions reverted, as a trace hook can abort a Python call there;
  allowlist keyed by qualified name; "ends in raise" refuses an early exit
  and a rebound name; the Git route's `id_registry`, `IdRegistry.save` and
  the `-o` write with the cwd gone; round 2: counts, CHANGELOG, one
  wrapped `except`). 56 mutants: all killed but equivalents (a second
  `absolute_path` on a path already checked; `Path(x)` where the input
  probe says `DIR=.` first). Full suite 30738 passed, 99.97% (changed files:
  three uncovered lines, all untouched ones); every CI linter; manual
  checks `-j 8` 620 pass, 0 fail; Windows dry run by both reviewers (the
  cwd tests skip on Windows by one module constant). No `SKILL.md` changed.

### Follow-ups (not in C1b)

- Both top-level reporters (`cli_error_handler`, the hook's failure report)
  print an `InternalError` as a plain uncoded `ERROR:` line, the traceback
  only under `-v`: nothing says it is a bug in Pitloom.
- An `InternalError` in an argparse `type=` callable is said as "invalid
  value" (exit 2): a carrier that `main()` unwraps would keep it.
- A reader-relayed line on a local route double-quotes a path holding a
  control character (`FILE=''sub/a\x1bb.gguf''`): `named_stably` writes the
  stable value quoted, then `scrub` finds the escaped path inside it again.
- `message-catalogue-sweep-c2-plan.md` is 34.6 KB, over the file-size cap.
- A relative `-o` with the cwd gone says `DIR=.` only at the write, after
  the whole run; an up-front check would fail fast.
- `discovery_chdir` (`core/_models_wheel_guard.py`) reads the cwd even for
  an absolute project: with the cwd gone, setuptools discovery warns `DIR=.`
  and falls back (the SBOM of a trivial project is unchanged).
- Library `generate(" ./ ")` strips the target and reads the project; the
  CLI says `' ./ '` is not found (as on 785a40db).
- `extract/remote/_git_run.py` `_watch_size`'s thread has no handler: a
  `tree_bytes` failure stops the size cap with only a thread traceback.
- `_probe_within`: an `InternalError` its thread meets after the join's
  limit is kept in `answer` and never raised (the probe was given up on).

## Plan section 9: overlap, as planned

- **Masking PR**: owns `logging_config.py` (split plus `one_line`, Q8),
  `core/url_masking/`, `log_masking.py`. C1a touches
  `messages/_field_writers.py` (A2, raise types only): the masking PR may
  reorder mask/cut/escape there; land masking first, C1a rebases (small).
  B1 does not edit `log_masking.py` (its handlers are allowlisted).
- **C2**: owns docs/skills quotes, per-line `since`, `ELEMENT=`, wording of
  the conflict, over-cap and author lines. Shared: `messages/_types.py`
  (C2 adds `Line.since`; C1a A2 changes `line_for`'s raise) and the
  generated pages. **Order: masking, C1a, C2, C1b.** C2 after C1a so its
  quote sweep sees C1a's new lines and sets their `since`; if C2 lands
  first, C1a's new lines carry `since="0.25.0"` explicitly. C1b last: it
  is a re-runnable mechanical conversion, so rebasing it is cheap.

## Appendix: plan probes at 4c194136 (abridged)

```text
loom wheel ""          ERROR: loom wheel: file='' is not a file
loom enrich ""         ERROR: loom enrich: '.': not an AI model file ... [model-wrong-format]
loom merge ""          WARNING: FILE=.markdownlint.json: SBOM fragment is not ... (merges the cwd)
loom project -o ""     ERROR: loom project: FILE=.: could not write for the SBOM; Is a directory [file-unwritable]
input_datasets="a.txt" 5 x WARNING: ... names input_datasets='a' / '.' / 't' / 'x' / 't' ...
[["a.txt"]]            TypeError code=None: unhashable type: 'list' (at exit, no fragment)
set_model(None)        TypeError code=None: Value must be of type str. Got NoneType
set_model_hyperparameters(["a"])  AttributeError code=None
dataset_type="bogus"   fragment dtypes ['text']
croissant="a\x00b"     ValueError code=None: embedded null byte
loom.run(), cwd gone   FileNotFoundError code=None at __enter__
any loom command, cwd gone   Traceback ... project.py default=Path.cwd()
loom.run("ro/f.json")  PermissionError code=None
loom enrich/model <300a>.gguf  ERROR: ... [Errno 63] File name too long (3.10/3.11/3.13 macOS)
--namespace https://user:ghp_...@   CLI [option-invalid]; IdRegistry(namespace=) [credentials-unsafe/registry]
symlink link.py -> real/s.py  software_File real/s.py; provenance Source: link.py
AST: 214 broad handlers; 16 guarded, 11 re-raise, 145 swallow, 42 convert (106 files)
```
