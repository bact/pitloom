---
Created: 2026-09-30
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Metadata-only AI model readers (pre-1.0)

Status: planned, not built; lands after 0.20.0, which ships with #263's
gates and bounds and serves as the stable baseline the new readers are
tested against. Replaces the earlier subprocess-isolation plan
(kept below as the fallback for HDF5 only). Summarised in
[roadmap.md](roadmap.md) as one bullet linking here.

See also: [ai-model-scanning.md](../implementation/ai-model-scanning.md)
(what shipped in #263: the wheel gate, `--trust-wheel-model`, the input
bounds and the measured worst cases).

## Problem

Pitloom is an SBOM generator, not a machine-learning runtime. It needs a
model file's metadata (format version, hyperparameters, class name, input
and output shapes, key/value header fields), never its weights or graph.
Yet most readers hand the whole file to the format's own library, which
parses (and in fastText's case loads) far more than Pitloom emits:

| Format | Reader today | What that library does | What Pitloom emits |
|---|---|---|---|
| fastText | `fasttext.load_model` | full inference load, weight matrix included | args (dim, epoch, lr, ...), labels |
| ONNX | `onnx.load(load_external_data=False)` | parses the whole protobuf, every graph node | opsets, `metadata_props`, producer, graph name, input/output specs |
| GGUF | `gguf.GGUFReader` | one numpy view per tensor info, key/value pair and array element | every key/value field (`general.*` identity, hyperparameters, the rest as properties) |
| PyTorch `.pt` | fickling `Pickled.load` | one Python AST node per opcode (~200x) | top-level class name |
| Safetensors | `safe_open` | parses the whole JSON header | `__metadata__`, tensor names (as inputs) |
| HDF5 / legacy Keras `.h5` | `h5py.File` | native libhdf5 | four root attributes |
| NumPy, Keras zip, PT2 | header / `config.json` only | already metadata-only | -- |

Every memory, time and crash finding of #263's security reviews came from
this mismatch: the cost of a read scales with the file's declared
structure, not with the few fields Pitloom keeps, and a native parser
(libhdf5, protobuf, fastText) can segfault, hang, or ignore Ctrl-C. #263
bounds the inputs and gates these formats in wheels; that is a cap on the
symptom, not a fix.

## Decision

Replace each library read with a small, pure-Python, stdlib-only reader
that reads only the bytes holding the emitted fields, seeks past everything
else by its declared length, and stops.

- **Cost follows the header, not the model.** Every read is bounded by a
  byte budget and a count budget fixed per format; declared lengths are
  checked against the file size before seeking.
- **No execution, no native code.** A hostile file can at worst make the
  reader refuse it (`ModelLimitExceeded` or a malformed-file error, same
  stub-plus-one-`WARNING:` path as today).
- **Same metadata.** A reader must produce exactly the `AiModelMetadata`
  the current reader produces for every fixture (parity, below). A field
  the old reader emitted but the new one cannot read without walking
  weights is a design question to raise, not a silent drop.
- **The native libraries leave the runtime dependencies.** `fasttext`,
  `onnx`, `gguf`, `fickling` and `safetensors` move from the `ai` extra
  and per-format extras to a test-only `model-parity` dependency group.
  Installing Pitloom alone then scans every format it has a reader for.
  (`h5py` stays until HDF5 has its own reader.)
- **The wheel gate lifts per format** as its reader lands: a format whose
  reader is metadata-only is no longer in `WHEEL_GATED_FORMATS`. When HDF5
  is the only gated format left, `--trust-wheel-model` applies to it alone;
  it is retired when HDF5 has its own reader or leaves the gate another way.

## Per-format plan

In rough order of size (smallest first, so the harness and conventions
settle on the easy ones):

1. **Safetensors.** 8-byte little-endian length (already capped at
   16 MiB), then one bounded read and `json.loads` of the header. Emit
   `__metadata__` and the tensor names, the names cut by the entry cap as
   today.
2. **PyTorch `.pt`/`.pth`.** Stream `pickletools.genops` over the bounded
   `data.pkl` (or the raw legacy pickle) that `_pickle_bounds.py` already
   walks; record the first `GLOBAL`/`STACK_GLOBAL` target (resolving the
   memo for `STACK_GLOBAL`'s two strings) and stop. No AST, no fickling.
   Parity: the class name must equal fickling's top-level class on every
   fixture; the rules for which global counts as "top-level" must match
   fickling's, verified on the fixtures, not assumed.
   `genops` only decodes (no `find_class`, no object construction), but it
   converts the decimal `INT`/`LONG` text arguments with `int()`, which is
   quadratic once `sys.set_int_max_str_digits` is off
   (`PYTHONINTMAXSTRDIGITS=0`, or CPython 3.10.0-3.10.6 without the limit):
   measured 3.4 s for one 1M-digit `LONG`, ~4 min extrapolated at the 8 MiB
   cap. The reader therefore walks opcodes with its own argument decoder
   built from `pickletools.opcodes` (the opcode table, not `genops`): it
   skips decimal arguments by length without converting them, since the
   class name never needs a number.
3. **GGUF.** The `_gguf_bounds.py` walker already parses the header
   structure; extend it to return key/value values, skip large arrays by
   seeking once the emitted value is known, and never read tensor infos
   beyond counting them. This removes `GGUFReader` and most of the
   combined budget. Parity caveat, a bug in today's output: `gguf.py`'s
   `_field_value` renders an array field as its *last element*
   (`parts[-1]`). On `stories260K.gguf` this emits
   `tokenizer.ggml.scores = '-252.0'` (the last score) and
   `tokenizer.ggml.tokens = '[226, 128, 138]'` (the UTF-8 bytes of the last
   token, as a list of ints). Fixed before 0.20.0 in its own small PR: an
   array field is emitted as `<key>.length = N` only; the parity test then
   pins that behaviour.
4. **fastText (`.bin`, `.ftz`).** Magic and version, then the fixed
   `Args` struct (dims, epochs, lr, loss, model, ...), then stream the
   dictionary (`nwords`, `nlabels`, per entry a NUL-terminated string,
   `int64` count, `int8` type) keeping only labels, bounded by the entry
   cap; stop before the input matrix. Quantised `.ftz` shares the header
   and dictionary layout: verify on a real `.ftz`.
5. **ONNX.** Walk the `ModelProto` wire format by field number and wire
   type: read `ir_version`, `producer_*`, `domain`, `model_version`,
   `doc_string`, `opset_import` and `metadata_props`; inside `graph`,
   read `name`, `input` and `output` (`ValueInfoProto` with its
   `TypeProto` shape) and skip `node`, `initializer` and every other field
   by length. Needs a minimal varint/length-delimited decoder, not the
   protobuf runtime.
6. **HDF5 (optional).** The four root attributes need the superblock, the
   root group's object header and its attribute messages, possibly a
   dense-attribute B-tree/heap. This is the largest reader; see open
   questions. Until then HDF5 stays gated in wheels.

One format per commit (or per PR for ONNX and HDF5), each with its own
parity and hostile-input tests.

## Parity testing

The existing fixtures (`tests/fixtures/aimodels/`, 25 real files) and the
native libraries become the test oracle:

- **Drift test per format:** for every fixture of that format, the new
  reader's `AiModelMetadata` equals the old library reader's, field by
  field (paths excluded as today). The library readers stay in the test
  tree (or as a `tests/` helper) for this purpose only; the test is marked
  and skipped with a reason when the `model-parity` group is not installed,
  and CI installs it.
- **Hostile corpus:** every reproducer from #263's reviews (GGUF counts and
  nesting, pickle amplification, ONNX empty-entry floods, oversized
  Safetensors headers, the two HDF5 crash files) becomes a regression
  input: refused or read within a fixed memory and time bound, never a
  crash. The watchdog harness pattern (RSS limit plus timeout) moves into
  a test helper.
- **Mutation fuzzing:** the existing `fuzz` group (atheris) gets one target
  per reader; truncation and byte-mutation of each fixture must only ever
  yield metadata or a refusal.
- **More fixtures where coverage is thin:** a real `.ftz`, an ONNX model
  with symbolic dimensions, a GGUF with nested arrays, a legacy raw pickle.
  Each recorded in `tests/fixtures/README.md` with its source and licence.

## A separable library

The readers are written so they can later become their own distribution
(model-format metadata, useful beyond SBOMs), without committing to that
now:

- One subpackage (working name `pitloom.extract.ai_model.formats`) with no
  import from the rest of Pitloom; stdlib only.
- Input: a binary file object (seekable) plus an explicit limits object.
  Output: a plain frozen dataclass per format (raw fields, no SPDX, no
  provenance strings). Pitloom's adapter maps it to `AiModelMetadata` and
  adds provenance, warnings and `FORMAT=`/`FILE=` wording.
- Its own exception hierarchy (limit exceeded, malformed, unsupported
  version); no logging through Pitloom's logger; no global state.
- Own tests runnable on their own; typed (`py.typed`), mypy strict.

Extraction into a separate project is a later decision (name, licence
stays Apache-2.0, release cadence, whether Pitloom vendors or depends on
it).

## Fallback: subprocess isolation (HDF5 only, if needed)

If a pure-Python HDF5 reader proves too costly, run only the HDF5 read in a
child process: path in, `AiModelMetadata` as JSON out (never pickle), a
wall-clock timeout and a memory limit set by the parent (`setrlimit` on
POSIX, a Job Object on Windows; macOS ignores `RLIMIT_AS` for some
allocators), and on timeout or limit the child is killed and the entry
falls back to the format-only stub with one `WARNING:`. Open points carried
over: worker start cost, determinism of relayed logs, the Windows Job
Object dependency, and ownership by `TerminationGuard`.

## Open questions

- **HDF5:** own reader (superblock versions 0-3, compact vs dense
  attributes, variable-length strings) vs `pyfive` (pure Python, but a
  new dependency with numpy) vs the subprocess fallback vs keeping it
  gated. Decide after the other five land and the reader conventions are
  proven.
- **Dependency change:** moving the native libraries to a test group drops
  the `ai`/per-format extras; whether to keep the extras as empty
  compatibility names until 1.0 (private alpha: probably not).
- **fastText labels:** a supervised model's dictionary can hold millions
  of words; streaming is linear in the dictionary size. Whether a time or
  count budget should stop early with the labels found so far (and one
  `WARNING:`), or refuse.
- **GGUF array fields:** see the parity caveat in the per-format plan.
