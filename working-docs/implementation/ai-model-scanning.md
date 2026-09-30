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
distribution's files. Today the project directory (`loom project`,
`embed-wheel`, the Hatchling hook) uses it; a wheel producer is a planned
extension.

## Modules

- `extract/scanner.py` -- the policy: `ModelCandidate`, `UsageSource`,
  `is_model_candidate_name()`, `discover_ai_models()`,
  `attach_usage_references()`, `scan_ai_models()`. It imports no producer.
- `extract/scanner_project.py` -- the project-directory producer:
  `project_candidates()`, `project_sources()`, `scan_project_for_ai_models()`.
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
  path when the file has no project-relative path. Never a temporary path;
  the shared code trusts it and prints it as `FILE=`.

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

## Known limit

The exception text after `FILE=<stable>;` can still name a real or
temporary path (for example ONNX's "Failed to load ... from <path>"). Only
`FILE=` is stable. Scrubbing it is decided in the wheel-scanning PR, which
adds temporary copies of wheel members.

A candidate with an allowed suffix that exists but cannot be read (denied
file or directory) gives one `FORMAT= FILE=` warning ("could not read
header"; `FORMAT` is the extension-derived format, or `unknown` for `.bin`
and `.zip`) and is skipped. `ModelCandidate.sniff` raises `OSError` for this
and returns `b""` only for absence, so every producer shares the one path.
A readable `.bin` with no model magic stays a silent skip.

Provenance `Source:` names the physical file for a renamed model: static
`assets/weights.dat`, but `--allow-build` `pkg/renamed.npy`. Fixed in PR D
section 3.3(2).

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
- **Open, for PR D:** `ProjectMetadata.files` order drives `File-N` ids
  (`_document_files.py` does not sort), so the wheel producer must sort its
  files the same way. Two candidates with the same distribution and
  physical path still give two models; deduping them is deferred to PR D.

## Wheels and `--scan-model-usage` (PR D)

A `scanner_wheel.py` producer, a `scan_usage` gate on `scan_ai_models()`,
and a read cap inside `attach_usage_references()`.
