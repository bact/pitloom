---
Created: 2026-09-30
Last-Modified: 2026-10-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model scanning

See also: [model-metadata-extraction.md](model-metadata-extraction.md) for
the per-format readers and
[recurring-bug-patterns.md](recurring-bug-patterns.md) for the
`physical_path`/`distribution_path` hazard this design removes;
[ai-model-scan-bounds.md](ai-model-scan-bounds.md) for the bounds on a
reader; [ai-model-scan-security-lessons.md](ai-model-scan-security-lessons.md)
for the lessons from the review rounds, with measurements.

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
- `extract/ai_model/reader_requirements.py` -- each reader's optional library,
  and the one message for a missing one.
- `extract/ai_model/limits.py` -- `ModelLimitExceeded`, the entry cap and the
  read-charging hook; `archive_member.py` (bounded member reads, ZIP check),
  `_pickle_bounds.py`, `_gguf_bounds.py` -- see
  [ai-model-scan-bounds.md](ai-model-scan-bounds.md).
- `extract/_reader_log.py`, `extract/ai_model/_stderr_capture.py` and
  `extract/_interrupt_hold.py` -- capture of what a reader logs and prints.

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
  Pinned by `test_scan_non_models_are_silent`
  (`tests/extract/scanner/test_scanner_project.py`).
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

- **Exception text is scrubbed.** After a reader fails, `read_model_candidate()`
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

- **A PyTorch extension needs a PyTorch header (round 6).** `.pth` is also
  the suffix of Python path-configuration files (`distutils-precedence.pth`,
  `a1_coverage.pth`, `*-nspkg.pth`), plain text that every wheel built with
  setuptools or coverage carries. The extension fallback in
  `detect_ai_model_format_from_header()` accepts `.pt`/`.pth` only for a ZIP
  local header or a pickle PROTO opcode with protocol 2..5 (`torch.save` writes
  the ZIP form, or with `_use_new_zipfile_serialization=False` a protocol 2
  pickle, `\x80\x02`); any other header, an empty one included, is no model,
  silently. A file that cannot be read has no header: the unreadable-file
  warning and `detect_ai_model_format()` name its format from the suffix alone
  (`detect_ai_model_format_from_name()`). Both `tests/fixtures/aimodels/pytorch`
  files are ZIPs. `torch` is not installed here, so the legacy claim rests on
  its documented protocol default, not a live `torch.save`.
- **`loom model`/`loom enrich` open the path as typed, else its resolved
  form.** `missing/../x` resolves to `x` lexically but does not open as typed,
  so the existence check and the generator must agree on one path
  (`existing_model_path()`); a path that opens as typed keeps its spelling in
  every log line.

## Decided in the outcome-parity PR (#270)

Rule: one confirmed model file gives exactly one `ai_AIPackage` on every
surface, whatever its read outcome. Code: `read_model_candidate()` in
`scanner.py` (the single read rule), `local_model_candidate()` in
`scanner_project.py` (the single-file producer), `_EXTENSION_ADMITS` and
`contradicted_format()` in `ai_model/reader.py`.

- **D1/D4 `loom model`, `generate FILE`, `enrich`, `generate_model_sbom()`,
  `enrich_model()` on a confirmed model whose read fails:** a stub SBOM (or
  the fragment) and the scan's own `WARNING:`, exit 0. They go through
  `read_model_candidate()`, so the message, entry cap and stub are the scan's.
  The enrichers read the README or model card next to the file, not the
  model, so the fragment is useful. A file that is not a model stays the one
  `ERROR:` (`ValueError`, exit 1); an absent file stays `FileNotFoundError`.
- **D2 a parse failure in a scan is a stub, not a drop.** Dropping claimed
  there was no model and made the entry set depend on read order (the budget)
  and on whether a library was installed.
- **D3 the header must not contradict the suffix.** Magic formats need their
  magic (no extension fallback); ZIP formats (`.keras`, `.pt2`, `.npz`) a ZIP
  header; `.pt`/`.pth` as before; ONNX and HDF5 any non-empty header (no
  signature at offset 0; an HDF5 userblock moves it). An empty header is never
  a model. A contradicted suffix gives one `WARNING: FORMAT=<fmt> FILE=<path>:
  header is not <fmt>; not listed as an AI model`, except `.pth`/`.pt` (path
  configs) and empty files. `IdRegistry.generate` uses the same rule, suffix
  filter included (`is_model_candidate_name()`): a `.dat` with GGUF magic or an
  `.nc`/`.mat` HDF5 file gets no entity, as in a scan.
- **D3 Git LFS pointer (review round 1, user decision U1):** a header opening
  `version <spec URL>` (the three URLs git-lfs's pointer decoder accepts:
  `git-lfs.github.com/spec/v1`, `hawser.github.com/spec/v1`,
  `git-media.io/v/2`) is no model under any suffix, `.pt`/`.pth`/`.onnx`/
  `.h5`/`.hdf5` included (the suffix table would otherwise admit it).
  The line must be complete, ending `\n` or `\r\n` as git-lfs compares the
  whole value (`/spec/v1x` is no pointer). `SNIFF_BYTES` grew from 9 to 44
  for it (the longest opening line, CRLF included; one tiny bounded read). The reason is `header is a Git LFS pointer`, through
  `NotAModel.reason`, so the CLI errors carry it. A `.bin`/`.zip` pointer
  names no format: one `WARNING:` without `FORMAT=` (round 2; round 1 left it
  silent). `read_ai_model()` itself gives the same reason (and `file is
  empty`) instead of "unsupported format" for a supported suffix; both it and
  `NotAModel` take it from `refusal_reason()`, so a surface cannot word it
  differently (round 3), and `read_ai_model()` refuses a non-regular path
  (`not an AI model file ...`) rather than run a reader on a directory.
  An empty ZIP (`PK\x05\x06`, `np.savez(f)` with no array) counts as a ZIP.
- **D5 HDF5:** one `WARNING:` per unparsable attribute (`model_config`,
  `training_config`); any part that is not an object (`config`, a layer,
  `build_config`, `optimizer_config`), a `layers` that is not a list, a
  `class_name`/`name`/optimizer class that is not a string, and JSON nested
  too deeply (`RecursionError`) count; the 500-character cut is on the same
  line. The parser stops at the first problem and the warning lists the
  fields not read at that point (`skipped`), computed from the stage reached
  (`ConfigProblem.lost`), not a fixed list. Absent is not a problem, and a
  key present with `null` counts as absent for an object part (`config`,
  `layers`, `build_config`, `optimizer`): JSON `null` carries no data, so
  AGENTS.md's "absent source data is not an error" applies (main was
  silent too). A `null` *inside* `layers` is a malformed layer and warns
  (`layers[<i>] is not an object`). A valid config
  without class or name keeps the old cut-only notice. Parsing lives in
  `ai_model/hdf5_config.py` (hdf5.py was near the size limit).
- **HDF5 string-array attributes** (`h5py.string_dtype()` arrays read as
  `object` ndarrays) are decoded per element, joined by newline; `tobytes()`
  of an object array is its pointers, so the text, and the SBOM, differed per
  run. Round 2: only `hasobject` arrays are walked element by element;
  fixed-length `S`/`U` arrays are decoded in blocks (a Python object per
  element cost ~160 bytes, a 20 MB `S1` array reached 3.2 GB). A compound
  dtype with an object field (`kind == "V"`, `hasobject`) is an unsupported
  attribute: one `WARNING:`, its fields skipped. An attribute h5py cannot
  convert at all (opaque) is the same, per attribute, not a lost file.
- **The suffix filter stays in `discover_ai_models()`**, not in
  `read_model_candidate()`: `loom model weights.dat` with GGUF magic keeps
  working, since a single file named by the user is judged by its header alone
  (intended; the docstrings of `_read_local_model()` and
  `local_model_candidate()` say so).
- **Messages split by owner:** `discover_ai_models()` words the scan's
  `OSError` and `NotAModel` warnings; the single-file surfaces turn
  `NotAModel` into a `ValueError`. Pure text helpers (`scrub`, `detail`) moved
  to `extract/_scanner_messages.py`; the reader-record relay stays in
  `scanner.py` so its logger name is unchanged.
- **Rejected:** magic-only detection (ONNX has none); a per-surface outcome
  (keeps the parity gap for registry v3 and G7 #3); a stub for a bound but an
  error for a parse failure on a single file (two rules, still unlike a scan).
- **Not changed:** ids stay outcome-dependent (`AIPackage-ok-1` read,
  `AIPackage-safetensors-3` stubbed); registry v3 owns that.
- **Follow-ups** (roadmap): Keras v3 failing whole on a bad
  `config.json`; scan `FORMAT=hdf5` vs a reader result of `keras`.

## Known limits

A candidate with an allowed suffix that exists but cannot be read (denied
file or directory) gives one `FORMAT= FILE=` warning ("could not read
header"; `FORMAT` is the extension-derived format, or `unknown` for `.bin`
and `.zip`) and is skipped. `ModelCandidate.sniff` raises `OSError` for this
and returns `b""` only for absence, so every producer shares the one path.
A readable `.bin` with no model magic stays a silent skip, as does an empty
file.

A raw (non-ZIP) `.pt` is bounded like an inner member: its first pickle must
end within the 8 MiB cap (the tensors that follow a legacy pickle are not
read), so a legacy file with a larger first pickle keeps a stub.

What the bounds do not cover, by design, until the metadata-only readers
([model-metadata-readers.md](../design/model-metadata-readers.md)): see
[ai-model-scan-bounds.md](ai-model-scan-bounds.md).

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
  `generate <dir>`, `embed-wheel --project-dir`, the Hatchling hook (which
  reads the project's own config), `wheel`, `wheel --embed` and standalone
  `embed-wheel` (the wheel ones through `--config`/`pitloom_config=` only). `hasDataFile` therefore no longer appears
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
  them.` The setting's spelling is the one producer-specific part
  (`USAGE_SETTING_PROJECT`/`USAGE_SETTING_WHEEL` in `scanner.py`): a wheel
  reads no implicit config, so its hint says `scan-model-usage = true in a
  --config file or pitloom_config`.
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
`--project-dir` keeps scanning the project; `--sbom` scans nothing; the
Hatchling hook scans its project directory, never a wheel.

- **Members** come from `wheel_members()` -- no logger, as `read_wheel()`
  already reported every name (two reports would double each
  `ARCHIVE= ENTRY=` warning) -- minus the wheel's own `.dist-info/`
  (`matching_dist_infos()`: the top-level directory `{name}-{version}.dist-info`
  that the wheel *file name* names, via `wheel_name_version()`, names PEP 503-
  and versions PEP 440-compared; skipped only when exactly one directory
  matches; a name that is not a wheel file name skips nothing; any other
  `*.dist-info/` is scanned). Rejected
  (round 5c): "holds a `METADATA` or `WHEEL`" -- a hostile wheel hid a model
  under `x.dist-info/WHEEL`. `distribution_path` is
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
  `read_model_candidate()` logs `FORMAT=%s FILE=%s: N bytes exceeds the M-byte scan
  ceiling; metadata not read` (`read more than M bytes, over the ...` when the
  copy was aborted: the size is then a lower bound, not known), so no
  producer writes a `FORMAT=`/`FILE=` string.
- **Stub rule.** A model over the ceiling, or met once the wheel budget is
  spent, is kept as a format-only `AIPackage` (the format as its name, the
  file's name and the link to it; as for a missing optional library) with the
  one `WARNING:`. Dropping it would make the SBOM claim the wheel holds no
  such model.
- **Per-wheel budget.** `BUDGET_FACTOR` (4) times `max-model-extract-bytes`
  (2 GiB by default; derived, no key) bounds the bytes copied across all
  members: an archive of many just-under-ceiling models cannot fill the
  disk. Bytes actually read are counted, plus a declared-size prefilter;
  once spent, the budget stays spent (a later small model does not sneak
  in), the remaining models become stubs, and one `WARNING:` per wheel says
  so (`AI model scan: the per-wheel budget of N bytes for copying and reading
  model files in <wheel> is spent; the model that would pass it and the models
  not yet read are listed without metadata`; the wheel's name, escaped). The bounded reads inside a model archive
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
- **Bounds** (inner-member read cap, header and opcode bounds, entry caps,
  ZIP central directory, the audit that every cut is reported, what is left
  open): [ai-model-scan-bounds.md](ai-model-scan-bounds.md).
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
  The undo of both captures (`_reader_log.py`, `_stderr_capture.py`) is
  bounded by one shared helper, `extract/_interrupt_hold.py`: a second
  `KeyboardInterrupt` in the undo is held for 3 tries, then raised, and the
  lock is taken with a 5 s timeout (`LockNotReleased`). Retrying every
  interrupt for ever was unkillable on CPython 3.14, where an interrupt can
  arrive after a lock is acquired and before the `try` that releases it,
  leaving the lock held for good (3 of 3 runs of a reproducer hung there).
  Accepted cost: when that happens the logger or `sys.stderr` may stay as
  the interrupt found it; the process is ending on that interrupt.
- **Unsafe readers are gated** (security; `--trust-wheel-model`). A reader that
  calls a native library in Pitloom's process is an unbounded CPU/memory (or
  crash) surface no byte ceiling covers, and a signal handler does not run under
  native code, so Ctrl-C cannot interrupt it: fastText (a hostile 308-byte
  header measured 5 GB resident and climbing), HDF5 (two committed 8 KiB files,
  `tests/fixtures/aimodels/hostile/`, segfault and hang libhdf5), ONNX (protobuf
  amplification: 16 MiB peaked at 3 GB) and, in pure Python, PyTorch
  `.pt`/`.pth` through fickling (~200x) and GGUF through `GGUFReader`'s
  per-element loop. A wheel's hostile file is the likelier input, so the default
  there is: sniff only (no materialise, no loader), `_stub()`, and one `INFO:`
  per scan listing the gated formats met that its claim accepts, sorted, and
  naming the flag (`ReaderGate.report()` after a scan that succeeded, none on
  failure, when no SBOM is written; the claim is per format, so an
  `embed-wheel` batch names each format once, in the first wheel that has it:
  a per-batch slot named only the first wheel's formats). `WHEEL_GATED_FORMATS`
  (`scanner_wheel.py`) is the set of formats; the scanner sees it only as a
  `ReaderGate` on each `ModelCandidate`, so a project producer could use it.
  `--trust-wheel-model` (`trust_wheel_model=`;
  `ConfigOverrides.trust_wheel_model` for `embed_wheel_sbom()`) lifts the gate:
  a plain opt-in like `--allow-build`, `store_true` with a `None` default so the
  inert-option machinery can tell "not given" from "given", and no config key,
  since a config can live in the untrusted tree. Live on wheel, `wheel --embed`
  and standalone `embed-wheel`; `INERT` on every other kind. A project scan is
  not gated: the tree is the user's own, but that is unsafe for an untrusted
  checkout. Metadata-only readers that never hand the file to a native library
  are the real fix:
  [model-metadata-readers.md](../design/model-metadata-readers.md).
- **Enrichment stays off** for a wheel: no README or model card is read from
  an archive.
- **Rejected:** materialising siblings (no reader reads one: Keras reads
  inside its own zip, ONNX loads no external data); a compression-ratio gate;
  a separate config key for the budget (derived from the ceiling instead);
  wrapping fickling's stream with a raising reader (it seeks backwards and
  reads whole when non-seekable: a bounded `BytesIO` is simpler and equal).
