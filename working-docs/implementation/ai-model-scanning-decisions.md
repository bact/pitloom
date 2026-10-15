---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model scanning: decisions

See also: [ai-model-scanning.md](ai-model-scanning.md) (the scanner design
and the map of these parts),
[ai-model-scanning-wheels.md](ai-model-scanning-wheels.md) (wheels and
`--scan-model-usage`).

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
  silent too). So does a whole attribute of JSON `null`, and a `null`
  `optimizer_config` falls through to `optimizer` as an absent one does.
  A `null` *inside* `layers` is a malformed layer and warns
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
