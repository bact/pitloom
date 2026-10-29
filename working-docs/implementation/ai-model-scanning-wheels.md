---
Created: 2026-10-15
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model scanning: wheels and usage

See also: [ai-model-scanning.md](ai-model-scanning.md) (the scanner design
and the map of these parts),
[ai-model-scanning-decisions.md](ai-model-scanning-decisions.md) (the
decisions that led here).

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
- **Config.** `max-model-extract-bytes` (default 512 MiB) applies to wheel
  targets: `--max-model-extract-bytes` (argparse type
  `positive_byte_ceiling`) or the `max_model_extract_bytes=` keyword
  (`generate()`, the wheel generators, `ConfigOverrides`), else the
  `--config`/`pitloom_config=` key, else the default; the Action input
  appends the flag. It follows `max-source-metadata-bytes` (one
  `ConfigOverrides` field, one `apply_overrides` line, an embed batch
  validates once before its inert warning), but with `trust_wheel_model`'s
  INERT rows: every non-wheel kind warns. `generate()` validates it before
  dispatching, so a bad value is an error on an inert target too; the project
  generator takes no such parameter, and its callers settle it with
  `forward_options` and `project_target_kind`. `<= 0` is an error; unlike
  `max-source-metadata-bytes`, zero is not "unlimited", because this is a
  safety ceiling. Every surface shares `require_positive_ceiling()` (a
  `bool`/non-integer/`<= 0` is one line naming the surface), and the scan
  entry runs it again on a library `PitloomConfig`, never parsed, before it
  touches the wheel.
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
  The undo of both captures (`_reader_log.py`, `stderr_capture.py`) is
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
