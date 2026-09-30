---
Created: 2026-09-30
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model scanning

See also: [model-metadata-extraction.md](model-metadata-extraction.md) for
the per-format readers and
[recurring-bug-patterns.md](recurring-bug-patterns.md) for the
`physical_path`/`distribution_path` hazard this design removes.

## Purpose

One discovery policy for every surface that finds AI models among a
distribution's files. The project directory (`loom project`,
`embed-wheel --project-dir`, the Hatchling hook) and a built wheel (`loom
wheel`, `wheel --embed`, `embed-wheel` without `--project-dir`) both use it.

## Modules

- `extract/scanner.py` -- the policy: `ModelCandidate`, `UsageSource`,
  `is_model_candidate_name()`, `discover_ai_models()`,
  `attach_usage_references()`, `scan_ai_models()`. It imports no producer.
- `extract/scanner_project.py` -- the project-directory producer:
  `project_candidates()`, `project_sources()`, `scan_project_for_ai_models()`.
- `extract/scanner_wheel.py` -- the built-wheel producer:
  `scan_wheel_for_ai_models()`; see "Wheels" below.
- `extract/ai_model/reader.py` -- the format authority:
  `read_ai_model_header()`, `detect_ai_model_format_from_header()`,
  `detect_ai_model_format()`, `read_ai_model(model_format=)`.

## Candidate model

A producer yields lazily, one object per file, and does no I/O until the
shared code asks.

- `ModelCandidate.sniff()` returns at most `SNIFF_BYTES` bytes, `b""` when
  the file is absent. A genuine access failure raises `OSError`; the scanner
  warns once and skips the candidate.
- `ModelCandidate.materialize()` returns a context manager yielding a real
  path for the reader. It may raise; that is a read failure.
- `UsageSource.open()` returns a context manager yielding a binary stream.
  It may raise.
- `physical_path` on both is stable: project-relative, or the distribution
  path when the file has no project-relative path; for a wheel member, its
  raw archive name. Never a temporary path; the shared code trusts it and
  prints it as `FILE=` (escaped when not printable).

## Format authority

Magic bytes win; the extension is the fallback. The decision takes a header
and a name, so a producer with no path can use it. The scanner decides once
per file and passes the result to `read_ai_model(model_format=)`, so a file
is never detected as X and then read as Y. `loom model` passes no format and
keeps detecting from the path.

`read_ai_model_header()` returns `b""` when the file is absent
(`FileNotFoundError`, `NotADirectoryError`, `IsADirectoryError`, or a
Windows directory) and re-raises any other `OSError`, such as
`PermissionError`. `detect_ai_model_format()` still never raises.

## Path rules

- `distribution_path` decides the suffix filter, the extension fallback and
  `file_name`. The installed name is what code refers to.
- `physical_path` is stable and printed as `FILE=`. The joined
  `project_dir / physical_path` is used only to open the file.
- Example: Hatchling `force-include = {"assets/weights.dat" =
  "pkg/model.npy"}` gives a model named `model.npy`, and `pkg/use.py`
  containing `"model.npy"` becomes a usage edge. Before, the `.dat` file
  failed the suffix filter and was skipped.
- The reverse direction is lost: `force-include = {"assets/blob.npy" =
  "demo/blob.dat"}` was found by the static scan before (physical suffix)
  and is now dropped (installed suffix `.dat`). This makes the static scan
  agree with `--allow-build`, which already keyed on the installed name.
  Pinned by `test_scan_renamed_to_non_model_suffix_is_not_discovered`.
- A model whose stat is denied (e.g. inside a `chmod 000` directory) used
  to abort the scan with `PermissionError` on Python 3.10-3.13; it now gives
  one `FORMAT= FILE=` warning and no model (see Known limit).

SBOM bytes under `--allow-build` were already free of temporary paths
(guards in `_ai_package.py` and `enrich/`). What leaked was `FILE=` on
stderr and `format_info.physical_path` in memory. The guards stay as
defensive code for a hand-built `AiModelMetadata`.

## Pass 2 (usage)

- The `.py` filter is `distribution_path.endswith(".py")`.
- Open, read, strict UTF-8 decode and matching share one `try`. A broad
  `except` logs one `WARNING: FILE=...: could not read for usage scanning`
  and continues with the next source.
- It runs even when no model was found, so unreadable sources are still
  reported.
- **1 MiB cap** (both producers): `fh.read(cap + 1)`; a longer source gives
  one `FILE=...: larger than the 1048576-byte usage-scan cap; skipped`. The
  bounded read is the check: `ZipInfo.file_size` is archive-controlled, so it
  is never trusted. A source of exactly 1 MiB is scanned. Before, a project
  `.py` of any size was read whole.

## Decided in the wheel-scanning PR

- **Exception text is scrubbed.** After a reader fails, `_read_candidate()`
  replaces the path that was read in every spelling (as given and as
  resolved, longest first: macOS `/var` vs `/private/var`; each raw, as
  `repr` escapes it -- a Windows path's backslashes are doubled in
  `str(OSError)` -- and with forward slashes) in the message with the
  candidate's `physical_path`, then escapes it if not printable. The sniff
  and usage branches do the same with `read_path`, the file a project
  producer's `sniff`/`open` read (an absolute path, for `--allow-build` a
  temporary extraction directory). A project warning therefore shows the
  relative path, not an absolute one, and stderr is the same on every
  machine. A copy failure
  (`OSError` while creating or writing the temporary file) is re-raised
  without its filename, as its text would name the path.
- **Renamed-model `Source:` is restored.** Every reader writes `Source:
  {model_path.name}`, so a copy named `0.safetensors` would put that name in
  the SBOM. After `read_ai_model()`, an exact `Source: <copy name>` prefix
  (the value itself, or followed by ` |`) is rewritten to the distribution
  basename. It is a byte change for a static project rename
  (`Source: weights.dat` becomes `Source: model.npy`), which makes static
  and `--allow-build` agree with `file_name`.
- **Sort and dedupe.** File order is unchanged: `zip_file_members()` keeps
  archive order and identical bytes give identical `File-N` ids. Duplicate
  arcnames are dropped there (last wins, one `overwritten by later entry`
  warning from `read_wheel`), so the wheel scanner never sees two. The
  scanner itself does not dedupe: a project producer must give one
  `ProjectFile` per distribution path (its contract).

## Known limits

A candidate with an allowed suffix that exists but cannot be read (denied
file or directory) gives one `FORMAT= FILE=` warning ("could not read
header"; `FORMAT` is the extension-derived format, or `unknown` for `.bin`
and `.zip`) and is skipped. `ModelCandidate.sniff` raises `OSError` for this
and returns `b""` only for absence, so every producer shares the one path.
A readable `.bin` with no model magic stays a silent skip.

A raw (non-ZIP) `.pt` pickle is handed to fickling as a file, not bounded
by the inner cap below: it is not an inner member, and its size is the
file's own (a wheel copy is under the ceiling; a project file is read in
place).

## Paths rejected

- A `display` field on `ModelCandidate`: for every producer it equals
  `physical_path`; two fields for one value can drift.
- `(path, read_text)` tuples for pass 2: a stream-returning `open` lets one
  shared function enforce a read cap without trusting archive metadata.
- Leaving `scan_project_for_ai_models` in `scanner.py`: `scanner.py` would
  import the producer that imports it, an import cycle.
- `functools.partial` for the producer callables: mypy strict infers the
  wrong types for `partial(path.open, "rb")`.

## Order (PR C)

- **Key:** `(distribution_path, physical_path)`, both plain `str`, compared
  by code point. `distribution_path` first: it is `software_File.name` and
  the order `get_wheel_files` already uses. `physical_path` (the stable
  form) breaks a tie between two files with one arcname. Never `Path`
  objects: `PureWindowsPath` compares case-insensitively.
- **Where:** the candidates are sorted at the top of `discover_ai_models()`,
  before any sniff or read. The returned list, the reads and the
  `FORMAT= FILE=` warnings then all follow one order. Sorting the returned
  models instead gives the same list but leaves warning order input-driven.
- **Why there:** every consumer is positional.
  `enrichment_results_by_model[index]` and `resolved_entity_ids[index]` in
  `add_ai_models()` line up with `run_enrichers_for_models()` output, and
  `resolve_ai_model_entity_hits()` gives a pinned registry id to the first
  claimant. Sorting in `build()`, in assembly or after enrichment misaligns
  them.
- **`usage_files`:** each ends `sorted(set(...))`, keyed by the exact
  distribution-path string (the key of `file_spdx_ids`; no
  normalisation here). A wheel producer must list members with
  `zip_file_members()`, as `read_wheel` does, or the keys miss; see
  [archive-member-names.md](archive-member-names.md). `sources` are iterated
  sorted by distribution path, so `could not read for usage scanning`
  warnings come out in a stable order.
- **No shipped bytes moved:** all three callers already pass files sorted
  by `get_wheel_files`, and no golden fixture holds more than one model.
  The sort protects library callers of `scan_project_for_ai_models()` and
  PR D's zip-order wheel producer.
- **Rejected:** sorting in `build()` (misaligns enrichment and claims);
  `order=True` on the dataclasses (compares callables on a tie).
- **Closed in PR D:** `ProjectMetadata.files` order drives `File-N` ids
  (`_document_files.py` does not sort); the wheel producer keeps archive
  order, as `read_wheel` does, so no sort is needed. Duplicates: see
  "Decided in the wheel-scanning PR".

## Wheels and `--scan-model-usage` (PR D)

A `scanner_wheel.py` producer, a `scan_usage` gate on `scan_ai_models()`,
and a read cap inside `attach_usage_references()`.

### Usage gate (step 10, landed first)

- **What the flag gates:** only pass 2 (`attach_usage_references()`, which
  reads every Python source). Discovery (pass 1) always runs, so an AIPackage
  is present whatever the flag says. Gating pass 1 would make `--no-...`
  silently drop models.
- **Default off, everywhere:** `--scan-model-usage`/`scan-model-usage`
  (CLI > config > default, setup.cfg too) on every live surface: `project`,
  `generate <dir>`, `embed-wheel --project-dir` and the Hatchling hook (which
  reads the project's own config). `hasDataFile` therefore no longer appears
  by default; this changes hook and `project` output.
- **`scan_usage` and `usage_hint` have no default** on `scan_ai_models()`
  and both producers' wrappers, so a new caller cannot forget either.
  Callers pass `scan_usage=cfg.scan_model_usage is True` and
  `usage_hint=lambda: cfg.scan_model_usage is None`.
- **The setting is tri-state:** `PitloomConfig.scan_model_usage` is `None`
  when never given (off, plus the hint), `False` when given as false on any
  surface (off, silent), `True` on. Readers keep `None` for an absent key;
  `apply_overrides()` replaces only on non-`None`, so a config `false` is
  not collapsed to unset.
- **One INFO line:** emitted from `scan_ai_models()` only, when the pass is
  off, the setting was never given and at least one model was found; never
  from a caller or when no model exists. Every surface therefore words it
  identically. Text: `Found N AI model file(s); pass --scan-model-usage (or
  set scan-model-usage = true) to also record which Python files reference
  them.`
- **`usage_hint` is lazy** (`Callable[[], bool]`): `scan_ai_models()` calls
  it only when the pass is off and a model was found, so it may claim a
  once-per-run slot. An eager bool would let a model-less first wheel of a
  standalone `embed-wheel` batch use up the batch's one hint. A batch
  hints once, from the first wheel that has models (its count):
  `EmbedFileCache.first_use()` inside the callable, keyed per project
  directory for `--project-dir` and one shared key for standalone.
- **Inert elsewhere:** sdist, env, model, Hugging Face, both enrich kinds
  and `embed-wheel --sbom` warn that `--scan-model-usage` has no effect
  (`INERT` rows).

### Wheels (step 9)

`scan_wheel_for_ai_models(wheel_path, *, scan_usage, usage_hint,
max_bytes)` serves `loom wheel`, `wheel --embed`, `embed-wheel` without
`--project-dir`, `generate()` on a `.whl`, `generate_wheel_sbom()` and
`embed_wheel_sbom()` without `project_dir`. `--project-dir` keeps scanning
the project; `--sbom` scans nothing; the Hatchling hook scans its project
directory, never a wheel.

- **Members** come from `zip_file_members(zf, name, None)` -- no logger, as
  `read_wheel()` already reported every name (two reports would double each
  `ARCHIVE= ENTRY=` warning) -- minus `*.dist-info/*`. `distribution_path` is
  the normalised name (the same string as `software_File.name`), so
  `contains` and `hasDataFile` resolve; `physical_path` is the raw
  `orig_filename`, exactly what `read_wheel` stores in
  `ProjectFile.physical_path`. Traversal and absolute names never reach the
  scanner, and no member name is ever joined onto a path.
- **Copy out, bounded.** A reader needs a real path, so a model is copied to
  `{member index}{lower-case suffix}` in a temporary directory made on first
  use (a wheel without models makes none). The name is never derived from
  the member name: normalised basenames can still be Windows-reserved
  (`CON.npy`), long, or contain `:`/newlines. Checks: (1) declared
  `file_size` above the ceiling: `ModelTooLarge`, no file made; (2)
  `zf.open()` first, then `open(target, "xb")`, so an encrypted or
  unsupported member leaves no file; (3) a running byte counter on 8192-byte
  reads aborts at the ceiling and deletes the partial file (CPython already
  truncates a lying central-directory size with a CRC error, but the guarantee
  must not depend on that). `shutil.copyfileobj` is not used (no counter). No
  compression-ratio check: sparse real models deflate 1000:1. The ceiling is
  per member; total time over many members is not capped.
- **One owner of the messages.** The materialiser raises `ModelTooLarge`;
  `_read_candidate()` logs `FORMAT=%s FILE=%s: N bytes exceeds the M-byte scan
  ceiling; metadata not read` (`read more than M bytes, over the ...` when the
  copy was aborted: the size is then a lower bound, not known), so no
  producer writes a `FORMAT=`/`FILE=` string.
- **Stub rule.** A model over the ceiling, or met once the wheel budget is
  spent, is kept as a format-only `AIPackage` (name from the file, format
  from the sniff, the file link; as for a missing optional library) with the
  one `WARNING:`. Dropping it would make the SBOM claim the wheel holds no
  such model.
- **Per-wheel budget.** `BUDGET_FACTOR` (4) times `max-model-extract-bytes`
  (2 GiB by default; derived, no key) bounds the bytes copied across all
  members: an archive of many just-under-ceiling models cannot fill the
  disk. Bytes actually read are counted, plus a declared-size prefilter;
  once spent, the budget stays spent (a later small model does not sneak
  in), the remaining models become stubs, and one `WARNING:` per wheel says
  so (`AI model scan: more than N bytes ... copied from this wheel`).
  Members are visited in sorted order, so which models are read is
  deterministic.
- **Signals.** The temporary directory is made with `registered_temp_dir()`
  inside `guard.hold(MODEL_SCAN_ACTIVITY)`: `TerminationGuard` arms only
  inside a hold, so a bare `with TerminationGuard():` would leave a SIGTERM
  uncaught. The hold spans each model's whole copy (polled with
  `raise_if_pending()` per chunk, so a signal stops the copy at the next
  chunk), not the parse: a hung parser must stay killable. The activity is
  named "the AI model file copy", so the message's "during" (in the hold) and
  "after" (parsing the copy) are both true. Nested in an `embed-wheel` batch
  the guard is the batch's owner. The Hatchling hook gets no guard: it makes
  nothing to clean up. A leftover directory is named by its basename only,
  "in the system temp directory" (`mkdtemp`'s default): a full path is a
  machine-specific string in a log.
- **Config.** `max-model-extract-bytes` (default 512 MiB) is a config key
  only: no flag, no keyword. It applies to wheel targets and comes from
  `--config`/`pitloom_config=`. `<= 0` is a one-line config error; unlike
  `max-source-metadata-bytes`, zero is not "unlimited", because this is a
  safety ceiling. A library caller's `PitloomConfig` is never parsed, so the
  scan entry runs the same validator
  (`require_max_model_extract_bytes()`, a `bool`/non-`int`/`<= 0` is the same
  one-line error) before it touches the wheel.
- **Inner members are bounded too** (`extract/ai_model/archive_member.py`).
  A model archive (`.keras`, `.pt`, `.pt2`) is untrusted, and a few KiB of
  deflate inflate to gigabytes, so every reader reads a metadata member
  (`config.json`, `data.pkl`, `model.json`, the PT2 `extra/` files, an `.npy`
  v3 header length) through `read_archive_member()`: `read(CAP + 1)`, reject
  when longer. `CAP` is 8 MiB: these members are KiB to a few MiB even for a
  model with thousands of layers, and nothing Pitloom reads needs more. A
  `.pt` `data.pkl` is read into a `BytesIO` of at most `CAP` for fickling
  (whose `Pickled.load` would `read()` a non-seekable stream whole, and
  allocates what a `BINBYTES8` header claims). The error is an
  `ArchiveMemberTooLarge`, not a `ValueError`, so each reader's broad
  `except` lets it through; the scanner logs one `archive member X larger
  than N bytes; metadata not read` and keeps the stub. It applies to project
  scans too: same readers.
- **Reader logs.** Every reader warning goes through one route: the scanner
  captures the records a reader logs while it runs
  (`extract/_reader_log.py`, a handler on the `pitloom.extract.ai_model`
  logger, propagation off for the duration) and logs them again under
  `FORMAT= FILE=`, escaped, with the path scrubbed and a `Source: 0.pt`
  quoted by a reader put back to the member's name. A reader called without
  the scanner (`loom model`) escapes the member names it quotes itself, with
  the shared `logging_config.loggable()`. Not thread-safe: a record another
  thread logs on a reader's logger during a scan would be relayed too.
- **Enrichment stays off** for a wheel: no README or model card is read from
  an archive.
- **Rejected:** materialising siblings (no reader reads one: Keras reads
  inside its own zip, ONNX loads no external data); a compression-ratio gate;
  a separate config key for the budget (derived from the ceiling instead);
  wrapping fickling's stream with a raising reader (it seeks backwards and
  reads whole when non-seekable: a bounded `BytesIO` is simpler and equal).
