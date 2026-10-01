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

A raw (non-ZIP) `.pt` is bounded like an inner member: its first pickle must
end within the 8 MiB cap (the tensors that follow a legacy pickle are not
read), so a legacy file with a larger first pickle keeps a stub.

What the bounds below do not cover, by design, until the metadata-only
readers ([model-metadata-readers.md](../design/model-metadata-readers.md)):

- **GGUF CPU.** `gguf.GGUFReader` loops in Python once per tensor, key/value
  pair and array element (scalar or string, at any nesting depth), keeping a
  numpy view for each: ~1.1 KiB and 6 us per string, ~0.5 KiB per scalar,
  ~3.5 KiB per tensor or pair. The walker charges all of them to one budget of
  1M (a tensor or pair weighs 4, an element 1) and refuses nesting deeper than
  it follows, so a hostile header is refused in well under a second; the
  largest accepted headers measured ~1.1 GB and 6 s (990k strings, 8 MB),
  ~0.9 GB and 8 s (250k tensors, 10 MB), ~0.6 GB (250k pairs), ~0.5 GB
  (990k scalars). Before the combined budget, 12 x 1M uint8 elements (12 MB)
  peaked at 5 GB, arrays nested 5 deep were not followed by the walker but
  were by the reader (24 MB, 3.3 GB), and 1M tensor infos (39 MB) took 3.6 GB.
  A real vocabulary plus merges is ~0.5M elements, so the budget cannot drop
  further without stubbing real models. GGUF is also gated in a wheel. Replacing
  `GGUFReader` with our own key/value reader, which makes the walker
  unnecessary, is part of the metadata-only readers
  ([model-metadata-readers.md](../design/model-metadata-readers.md)).
- **Pure-Python amplification.** fickling builds an AST per opcode (~200x the
  pickle's size): a pickle at the 250k-opcode cap measured ~100 MB and 0.4 s. The
  safetensors `__metadata__` and ONNX readers build their result before the
  entry cap cuts it, so the cap bounds the SBOM, not the reader's peak
  memory.
- **Safetensors header.** The 8-byte length is read before `safe_open` and
  refused over 16 MiB (the library allows 100 MB; a 34.9 MB header peaked at
  1.7 GB above baseline, a 15.7 MB one at 0.8 GB, the bound's worst case).
- **Native readers.** libhdf5, protobuf (ONNX) and fastText are gated in a
  wheel, not bounded; a project scan runs them on the user's own tree.
  Under `--trust-wheel-model` a hostile wheel can crash or hang them
  (measured: a 16 MiB ONNX of empty inputs peaked at 3 GB; of two 8 KiB
  HDF5 files mutated from a valid `.h5`, one segfaults and one never
  returns).

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
max_bytes, trust, gate_hint)` serves `loom wheel`, `wheel --embed`,
`embed-wheel` without `--project-dir`, `generate()` on a `.whl`,
`generate_wheel_sbom()` and `embed_wheel_sbom()` without `project_dir`.
`--project-dir` keeps scanning the project; `--sbom` scans nothing; the Hatchling hook scans its project
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
  so (`AI model scan: more than N bytes ... copied or read from <wheel>`; the
  wheel's name, escaped). The bounded reads inside a model archive
  (`read_archive_member()`) count too, through a context variable set around
  each materialised model (`limits.charging_reads`): 100 `.keras` members
  that each inflate to 8 MiB are 800 MiB of work, however small the copies.
  A reader lets the `ScanBudgetExceeded` through like any
  `ModelLimitExceeded`.
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
  the shared `logging_config.loggable()`. Reader text goes through
  `one_line()`, which collapses whitespace and then applies `loggable()`, so
  a multi-line exception cannot spill untagged lines; `_detail()` never
  prints an empty detail (an exception without a message gives its class
  name). Capture is per thread: one dispatcher handler, installed on the
  first capture and removed by the last (a lock and a count, so blocks of
  several threads may end in any order), hands a record to the capture of
  the thread that logged it (`record.thread`) and passes the records of
  other threads on to the parent logger (by `threading.get_ident()` when
  `logging.logThreads` is off and `record.thread` is `None`). A block nested
  in another of the same thread restores the outer capture on leaving.
- **Unsafe readers are gated** (security; `--trust-wheel-model`). A reader
  that calls a native library in Pitloom's process is an unbounded
  CPU/memory (or crash) surface no byte ceiling covers, and a signal handler
  does not run under native code, so Ctrl-C cannot interrupt it: fastText (a
  hostile 308-byte header measured 5 GB resident and climbing), HDF5 (two
  committed 8 KiB files, `tests/fixtures/aimodels/hostile/`, segfault and
  hang libhdf5), ONNX (protobuf amplification: 16 MiB peaked at 3 GB) and, in
  pure Python, PyTorch `.pt`/`.pth` through fickling (~200x) and GGUF through
  `GGUFReader`'s per-element loop. A wheel's hostile file is the likelier input, so the default there is: sniff only
  (no materialise, no loader), `_stub()`, and one `INFO:` per run listing
  every gated format met, sorted, and naming the flag (`ReaderGate.report()`
  after the scan, through the same once-per-run slot style as the usage hint,
  so an `embed-wheel` batch says it once). `WHEEL_GATED_FORMATS`
  (`scanner_wheel.py`) is the set of formats; the scanner sees it only as a
  `ReaderGate` on each `ModelCandidate`, so a project producer could use it. `--trust-wheel-model`
  (`trust_wheel_model=`; `ConfigOverrides.trust_wheel_model` for
  `embed_wheel_sbom()`) lifts the gate: a plain opt-in like `--allow-build`,
  `store_true` with a `None` default so the inert-option machinery can tell
  "not given" from "given", and no config key, since a config can live in
  the untrusted tree. Live on wheel, `wheel --embed` and standalone
  `embed-wheel`; `INERT` on every other kind. A project scan is not gated:
  the tree is the user's own, but that is unsafe for an untrusted checkout.
  Metadata-only readers that never hand the file to a native library are
  the real fix: [model-metadata-readers.md](../design/model-metadata-readers.md).
- **Bounds before a parser runs** (project scans too; all raise
  `ModelLimitExceeded`, which a reader's broad `except` lets through; the
  scanner logs one `FORMAT= FILE=: <reason>; metadata not read` and keeps the
  stub). Pickle (`_pickle_bounds.py`): `pickletools.genops` walks the opcodes
  (no allocation per opcode), refuses more than 250k, and only the bytes of the
  first pickle reach fickling; fickling's stderr (it prints per failure, 62 MB
  in one measured case) is captured, per thread, by a process-wide `sys.stderr` proxy
  (`_stderr_capture.py`, installed under a lock and count like the log
  capture below; `contextlib.redirect_stderr` swaps the stream for every
  thread and, with two overlapping, could leave it swapped for good) into a
  bounded sink and summarised in one
  warning. GGUF (`_gguf_bounds.py`): a `struct` walk over the key/value
  section refuses tensors, pairs and array elements over one weighted budget
  of 1M, arrays nested deeper than the walker follows, or a count that cannot
  fit in the file, before `GGUFReader`; a merely truncated file is left to the
  reader. Safetensors (`safetensors.py`): the 8-byte header length is read
  first and refused over 16 MiB. NumPy (`numpy.py`): the `.npy` header length field is read first
  and refused over numpy's own 10000 (numpy reads the declared length before
  checking it: a v2 header declaring 4 GiB in a 48 MiB deflated member
  inflated it), and an `.npz` stops reading after 1001 members. Entry caps
  (`limits.cap_entries()`, in the scanner, so one place for every reader):
  the first 1000 of `inputs`, `outputs`, `hyperparameters`, `properties` and
  `raw_metadata` in source order, the provenance of the dropped keys removed,
  one warning naming the fields cut.
- **Enrichment stays off** for a wheel: no README or model card is read from
  an archive.
- **Rejected:** materialising siblings (no reader reads one: Keras reads
  inside its own zip, ONNX loads no external data); a compression-ratio gate;
  a separate config key for the budget (derived from the ceiling instead);
  wrapping fickling's stream with a raising reader (it seeks backwards and
  reads whole when non-seekable: a bounded `BytesIO` is simpler and equal).
