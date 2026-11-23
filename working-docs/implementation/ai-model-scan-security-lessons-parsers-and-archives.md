---
Created: 2026-10-15
Last-Modified: 2026-11-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model scan lessons: parsers and archives

See also: [ai-model-scan-security-lessons.md](ai-model-scan-security-lessons.md)
(the entry page: setting, how the problems were found, principles),
[ai-model-scan-security-lessons-runtime-and-output.md](ai-model-scan-security-lessons-runtime-and-output.md)
(sections 3.4-3.6),
[ai-model-scan-security-lessons-transparency-and-correctness.md](ai-model-scan-security-lessons-transparency-and-correctness.md)
(sections 3.7-3.10).

## 3.1 The library parses far more than the SBOM needs

The root cause behind most memory and time findings: a format library
builds its whole in-memory structure to hand back a few header fields.

| Format, library | Hostile input | Measured |
|---|---|---|
| fastText, `load_model` | 308-byte header | 5 GB resident and climbing (full model load) |
| ONNX, `onnx.load` | 16 MiB of empty inputs | 3 GB (protobuf amplification) |
| GGUF, `GGUFReader` | 12 MB: 12 arrays x 1M uint8 | 4.96 GB, 49 s (one numpy view per element) |
| GGUF | 24 MB: arrays nested 5 deep | 3.3 GB |
| GGUF | 39 MB: 1M tensor infos | 3.6 GB, 30 s |
| PyTorch, fickling | pickle | ~200x amplification (one AST node per opcode) |
| Safetensors, `safe_open` | 70 MB `__metadata__` header | 3.8 GB, 12 s |
| Keras/PT2/`.npz`, `zipfile` | `.keras` of 3M empty entries, 16 MiB in the wheel | 1.8 GB (one `ZipInfo` per entry) |

Lessons:

- **Byte ceilings do not bound parser work.** A small file can declare
  millions of elements; the cost is in what the parser builds, not in the
  bytes read. Bounds must be on declared counts and structure, checked
  before the parser runs.
- **A pre-check must agree with the parser exactly.** The GGUF pre-walker
  first skipped scalar arrays ("one numpy view") and treated deep nesting
  as malformed; the library did neither, so each difference was a bypass.
  Rule adopted: anything the library would accept but the pre-check cannot
  follow is refused, not ignored.
- **Count everything into one budget.** Separate caps per kind (tensors,
  pairs, strings) let an attacker spend each to the limit; a single
  weighted budget (tensor/pair weight 4, element 1, from measured cost per
  kind) bounded the total.
- **Version drift is a bypass.** The pre-check knew GGUF v2-v3; a future
  version the library accepts would skip the check. Fail closed on a
  version the library reads but the check does not know.
- **The real fix is not reading the structure at all**: header-only,
  stdlib-only readers that seek past what they do not emit, tested for
  parity against the libraries. Built: the pickle walker, CRFsuite (0.21.0)
  and the GGUF header (#517, 3.14).

## 3.2 Native code in-process

- **libhdf5:** two 8 KiB files, each a 1-27 byte mutation of a valid `.h5`,
  found within a few hundred random mutations: one segfaults the
  interpreter, one busy-loops forever. Committed as regression fixtures.
- **No interrupt.** A Python signal handler does not run while native
  code holds the interpreter, so Ctrl-C and `TerminationGuard` cannot stop
  a hung native parser.
- **Response:** gate the native and amplifying readers (fastText, GGUF,
  HDF5, ONNX, PyTorch pickle) for wheels: list the model with format only,
  plus one `INFO:`, unless the user passes `--trust-model-files`. No
  config key for the opt-in, because a config file can live in the
  untrusted tree. A local project scan is not gated (the user's own tree),
  which is documented as unsafe for an untrusted checkout; the same gate
  without an opt-in (`reader-unsafe/remote`) covers a model file and a
  project read from a Git URL's temporary clone, keyed on the one
  `in_remote_clone()` ContextVar, so no call site can forget it.

## 3.3 Archives inside archives

- **Wheel members:** `ZipInfo.file_size` is attacker-controlled. Copy with
  a running byte counter on 8 KiB reads, abort at the ceiling, delete the
  partial file; never `shutil.copyfileobj` without a counter.
  `zf.open()` before creating the target, so an encrypted or unsupported
  member leaves no file.
- **Temp names never derived from member names** (Windows reserved names
  like `CON.npy`, long names, `:` and newlines): `{index}{suffix}` only.
- **Aggregate budget.** A per-member ceiling still lets many members fill
  the disk; a per-wheel budget (4x the ceiling) counts bytes copied and
  bytes read inside model archives.
- **Nested decompression.** A model archive (`.keras`, `.pt`, `.pt2`) is
  itself a zip: a few KiB of deflate inflate to gigabytes. Every inner
  metadata member is read through one helper with `read(CAP + 1)`.
- **Declared lengths inside formats:** numpy reads the declared `.npy`
  header length before checking it; a v2 header declaring 4 GiB in a
  48 MiB deflated member inflated it. Check the length field first.
- **The central directory is a bomb too** (round 5b): `zipfile` builds an
  object per entry before any reader looks. A pre-check of the end record
  was added, then bypassed (round 5c) three ways because it did not find
  the same record `zipfile` uses: `zipfile` looks for the ZIP64 record at
  the locator's offset first; it accepts the last 22 bytes as the end
  record before searching for a signature (a signature planted in the
  record's own fields blinded our search); and CPython 3.10's search
  window is one byte wider than 3.14's. A 268 KB wheel reached 807 MB.
  Also, `zipfile` walks the directory by its byte size and ignores the
  declared entry count, so a lying count passed.
- **Lesson: never re-implement the parser's decision; reuse it.** Fixed
  by calling `zipfile._EndRecData` (the function `ZipFile` itself calls) on
  one handle, pinning its shape with a test, failing closed if it changes,
  and counting the real entries by streaming the directory before
  `ZipFile` runs. A private stdlib name is a lesser risk than a second
  implementation that silently disagrees.
- **"The parser's decision" differs across patch releases of one minor
  version.** The CVE-2025-8291 fix changed what `zipfile._EndRecData`
  reports for a ZIP64 archive (3.11.9 and 3.11.14 disagree), so the start
  of the directory computed for one is 76 bytes off for the other, the walk
  read garbage and "left it to `zipfile`": a bypass. Agree with the running
  interpreter (probe it, do not read the version), fail closed when the walk
  cannot account for the directory, and keep an unpatched interpreter in CI:
  CI's Windows 3.11.9 leg caught it; every local interpreter was patched.
- **Check and use the same handle.** Checking a path and then reopening it
  is a time-of-check/time-of-use gap.

## 3.14 Replacing the library: what it refused for free (#517, 2026-11-23)

The GGUF bound of 3.1 (one budget of 1M units before `GGUFReader`) refused
every Gemma-4 header: a 262,144-token vocabulary and 514,906 merges make
1,301,338 array elements, 777,050 of them strings. The SBOM-MinBench 0.2
header probe found 93 such files in its dataset (81 Gemma-4 files of 8
repositories, 12 of one audio repository). The budget only guarded
`GGUFReader`, which cannot skip a key, so #517 replaced it with a
stdlib-only header reader that passes over array contents (a fixed-size
array in one offset step, a string array one length prefix at a time).

| Gemma-4-shaped header (19.8 MB, 700 tensors) | Time | Peak RSS |
| --- | --- | --- |
| `gguf.GGUFReader` (gguf 0.19.0) | 7.5 s | 927 MiB |
| `read_gguf` with Pitloom's reader (imports included) | 0.3 s | 78 MiB |

Measured on macOS, CPython 3.10.19, on main at `0b0538c5`.

Two independent reviews and two mutation runs still found what the first
build missed:

- **The library's own limits were bounds nobody listed.** `GGUFReader`
  builds a numpy array per tensor shape, and numpy refuses more than 64
  dimensions (`maximum supported dimension for an ndarray is currently
  64`), so a many-dimension tensor failed in milliseconds. The new reader took
  any dimension count that fit in the file, and the tensor-size check
  multiplied every declared 64-bit dimension into one Python integer:
  5,000 dimensions took 0.10 s, 10,000 0.26 s, 20,000 1.04 s, 40,000
  4.12 s (quadratic; about 40 minutes at 1M dimensions, 8 MB). llama.cpp
  refuses more than `GGML_MAX_DIMS` (4) (`ggml/src/gguf.cpp` l. 661 at
  commit a8f8294c); the reader now does the same, and the size product
  stops once past what the rest of the file can hold.
- **A declared length checked against a cap before the file.** A string
  declaring 2^40 bytes in a file of under 100 bytes was reported as over the 8 MiB
  string cap, a partial read of a large file, when the file was malformed.
  Which outcome a lie got depended on its size.
- **A partial read looked complete in the SBOM.** Only the `WARNING:` said
  the walk stopped; the artifact-metadata annotation listed fewer keys
  than `GGUF.kv_count` with no marker. Reusing the entry-cap count would
  have added `maxEntries: 1000`, naming a cap that never applied.
- **The library had its own crash.** A local run of the fuzz harness
  (13,759 inputs) found that `GGUFReader` reads a scalar cut at the end of
  the file as a zero-length view, and the `TypeError` escaped Pitloom's
  `except (OSError, ValueError)` on main.

Lessons:

- **Before replacing a parser, write down what it refuses.** Probe it with
  many dimensions, huge counts and a length past the end, and keep each
  refusal in the new reader, citing the format's reference implementation
  rather than the library.
- **Is it in the file? Then is it over a cap?** The first is malformed,
  the second a partial read: check in that order.
- **Every product or sum of declared numbers stops early** once past what
  the file can hold.
- **A partial read needs an output marker with its own cause**, tested on
  every surface (a project's own model file keeps no metadata annotation,
  so there the warning is the only record).
