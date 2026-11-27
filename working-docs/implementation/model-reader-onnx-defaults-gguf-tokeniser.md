---
Created: 2026-11-23
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Model readers: ONNX default graph names, GGUF tokeniser headers (#514)

Status: built and merged in #517 (2026-11-23; #516 closed for a branch
rename); rulings Q1-Q5 at the end. The plan below is kept as written, with
the build notes, review rounds and open items after it. Lessons for the
paper: [ai-model-scan-security-lessons-parsers-and-archives.md](ai-model-scan-security-lessons-parsers-and-archives.md),
3.14.

See also: [model-metadata-readers.md](../design/model-metadata-readers.md)
(step 3, GGUF), [ai-model-scan-bounds.md](ai-model-scan-bounds.md),
[evidence-levels.md](../design/evidence-levels.md).

## Context

Issue #514 (2026-11-23), found by the SBOM-MinBench 0.2 header probe with the
Pitloom 0.24.0 readers. Two defects, both changing counts in the LLMSC 2027
paper (the camera-ready recount comment in `llmsc2027-model-file-metadata.tex`):

1. ONNX: three tool-default `graph.name` values are recorded as the model name.
2. GGUF: `check_gguf_header` refuses every Gemma-4-family header, so no field
   of 81 files (8 repositories, in the dataset) is read.

## Facts checked (not taken from the issue)

### ONNX defaults, read from each tool's source

| `graph.name` | Source line | Settable? | `producer_name` written |
| --- | --- | --- | --- |
| `merged` | optimum-onnx `optimum/onnx/graph_transformations.py` l. 195, `merge_decoders(graph_name: str = "merged", producer_name: str = "optimum-onnx")`, commit f1fe36b4e827 (2026-05-13) | yes, argument default | `optimum-onnx` |
| `spox_graph` | spox `src/spox/_graph.py` l. 351-354 (`if self._name: ... else: name = "spox_graph"`), main fccdc4f6277e; `to_onnx_model(producer_name="spox")` l. 374 | yes, `Graph.with_name()` | `spox` |
| `mxnet_converted_model` | MXNet 1.9.1 (tag 3f8f3be9987e) `python/mxnet/onnx/mx2onnx/_export_onnx.py` l. 429-431, literal in `helper.make_graph(...)`; `_export_model.py` l. 144 `helper.make_model(onnx_graph)` | no, hard-coded | none (empty) |

Probe evidence (`s1-hf-model-headers.jsonl`, `onnx_raw`): `merged` 12 files
of 5 repositories, 8 with producer `optimum-onnx` and **4 with
`onnx.quantize`** (quantisation rewrites the producer after the merge);
`mxnet_converted_model` 1 file, empty producer. `spox_graph` is not in the Hub
probe: it is `silero_vad.onnx` of silero-vad 5.1.2 in
`s1-embedded-model-headers.jsonl`. The issue's table is correct.

### GGUF counts, from the probe file

`reader_error` + `ModelOverCap`: 96 rows. In the dataset (`in_dataset`):
93 = 81 Gemma-4-family files of 8 repositories + 12 files of
`audio-cpp/audio.cpp-gguf`; outside it 3 more (2 Gemma 4, 1
`Jmica/Drama-3-GGUF`, cause unknown). The issue's 81/8 + 12 holds for the
dataset. Largest array total among the 2,599 GGUF headers read today:
843,898 elements (641,850 strings, `Muse-Glimmer-30B`); a Gemma-4 tokeniser
has 1,301,338 (777,050 strings).

The 12 audio-cpp headers hold up to 63 million array elements in at most
64 MiB of header (the probe's `bytes_read`), so at least ~98 % of those
elements are 1-byte scalars (a string takes >= 8 bytes): embedded file data
as `uint8`/`int8` arrays. Inferred from sizes, not read.

### Measurements (this Mac, Python 3.10, gguf 0.19.0 = newest on PyPI)

Synthetic Gemma-4-shaped header (262,144 tokens, 514,906 merges, `scores`
float32, `token_type` int32, 700 tensors; 19.8 MB), built in the scratchpad:

| Path | Time | Peak RSS (process) |
| --- | --- | --- |
| `gguf.GGUFReader` alone | 7.2 s | 927 MiB (import of gguf+numpy: 30 MiB) |
| `read_gguf` with the cap lifted | 7.7 s | 958 MiB |
| `_gguf_bounds` struct walk (every string hopped) | 0.56 s | 70 MiB (Pitloom import included) |

So `GGUFReader` costs ~0.69 KiB and ~5.5 us per array element (one numpy
view each, scalar or string, `gguf_reader.py` l. 247-254); the struct walk
~0.7 us per string hop and nothing per element of a scalar array.

## Part 1: ONNX

**Add the three names to `_EXPORTER_DEFAULT_GRAPH_NAMES`, matched by
`graph.name` alone**, each with a comment naming tool, file, line and
commit/tag (and the same for the existing four where a source line can be
found; else keep "seen from").

Rejected: keying on `producer_name`. 4 of the 12 `merged` files carry
`onnx.quantize`, and MXNet writes no producer: a producer rule would miss 5
of 14. A pair list `(producer, name)` misses the same files.

**Plus a producer rule (ruled 2026-11-23, Q3):** `graph.name` is also no
name when, stripped and casefolded, it equals the stated `producer_name` or
starts with `<producer_name>_` or `<producer_name>-`. An empty producer turns
the rule off. Both checks live in `_resolve_onnx_name` (one place); the list
keeps the cited names even where the rule also catches them (`tf2onnx`,
`spox_graph`), since a later tool (`onnx.quantize`) may rewrite the producer.
Sweep (offline, 2026-11-23): over the 396 ONNX rows of both probe files and
the 5 ONNX fixtures, the rule drops only `spox_graph`/`spox`; it keeps
`inception_v2`/`onnx-caffe2` and `main`/empty.

Unknown defaults: neither the list nor the rule is complete, so an unknown
default is still recorded as the name. It stays visible: provenance says
`Field: graph.name`, and the fact-check probe's `name_evidence`
(`header_name_contains_producer`, file-stem match) surfaces new candidates;
each is added to the list with its source line.

## Part 2: GGUF, options compared

The cost is in `GGUFReader`, which parses every element at construction and
cannot skip a key. The budget only guards it. So "skip the tokeniser arrays"
is possible only if Pitloom stops calling `GGUFReader` for the header.

| | A. Raise budget to 2,000,000 | B. Pitloom header reader, array contents skipped | C. Separate tokeniser budget, `GGUFReader` kept |
| --- | --- | --- | --- |
| Gemma-4 header | read, 7.7 s, ~960 MiB | read, ~0.6 s, ~70 MiB | read, 7.7 s, ~960 MiB |
| Worst accepted header | ~1.4 GiB, ~11 s (was ~1.1 GiB) | parsed items 1,000,000 (Python objects, no numpy views) + skip-hop cap ~3 s; memory follows the parsed items only | main 1.1 GiB + tokeniser budget: ~2.5 GiB |
| 12 audio-cpp files (63 M elements) | refused (`over-cap`) | 1-byte arrays skipped in O(1): **read**; a string array over the hop cap: fields before it read (`over-cap` warning) | refused, unless the data sits under `tokenizer.*` and fits that budget |
| Headroom over Gemma 4 | 1.5x | hop cap 4,194,304 = 5.4x Gemma's string hops | as chosen |
| Change size | 1 constant, docs, tests | new `formats/gguf_header.py` (~300 lines), `gguf.py` adapter rewrite, parity test | key-prefix split in the walker; the cost of A plus a rule keyed on a name an attacker controls |
| Against the rules | cap still bounds reading, but more is read than reported | nothing is parsed that is not reported; tokeniser length and type come from the header count: measured once the walk reached the array's end, declared when a cap stopped it mid-array | as A |

C is dominated by A (same real-file cost, worse worst case, a key-name
rule), so it is dropped.

**Decision: B (ruled 2026-11-23, Q2)**, step 3 of
[model-metadata-readers.md](../design/model-metadata-readers.md) cut to what #514
needs. It lowers time 12x and memory 13x on Gemma 4, lowers the worst case
below today's, and frees the cap from counting work Pitloom never needed.
The 12 audio-cpp files are read (Q1): skipping their 1-byte arrays costs
nothing, and caps bound reading only. Both parts ship in one PR (Q5).

### B in detail

- New `src/pitloom/extract/ai_model/formats/gguf_header.py`, stdlib only
  (isolation test `tests/extract/ai_model/formats/test_isolation.py` covers
  it): `read_gguf_header(data, limits, read_arrays) -> GgufHeader` with
  `version`, `endian`, `fields` (in file order: key, value type, scalar value
  or `ArrayInfo(length, element_type, values | None)`), `tensor_shapes`.
  Grown from `_gguf_bounds._Walker` (same struct layout, nesting, string and
  fits-in-file checks).
- Array values are read only for keys in `read_arrays`
  (`{"general.datasets"}`, the one consumer: `_gguf_datasets._listed_names`),
  within the existing datasets cap of 1,000. Every other array: scalar
  elements skipped by offset arithmetic, string and nested elements hopped,
  each hop charged to `max_gguf_skip_hops` (4,194,304; ~3 s measured).
- `formats/_limits.Limits` gains `max_gguf_parsed` (1,000,000: tensors,
  pairs, read array elements, tensor and pair weight kept at 4),
  `max_gguf_skip_hops`, `max_gguf_string_bytes` (8 MiB per string),
  `max_gguf_total_string_bytes` (64 MiB over all parsed strings: keys and
  values decoded, not hopped ones; today bounded only by the file size),
  `max_gguf_nesting` (4). A hit on any of them is a partial read (Q4). Errors from `formats/_errors.py`.
- `_gguf_bounds.py` becomes the adapter (as `_pickle_bounds.py` is for the
  pickle walker): maps format errors to `ModelOverCap(Cap(...))` /
  `ModelLimitExceeded(LIMIT_GGUF_*)`. Cap words: `GGUF-header` (parsed
  units) kept, new `GGUF-skipped-element` for the hop cap.
- `gguf.py`: `_load_fields` reads the header through the adapter;
  `_read_fields`, `_field_value`, `_array_summary`, `_array_length` work on
  plain values (float32 spelling via `numpy.format_float_scientific` kept;
  strings decoded `surrogateescape` as now). `gguf` stays a runtime
  dependency (`LlamaFileType` names, `READER_SUPPORTED_VERSIONS`), so the
  `library-missing` path and the `gguf` extra do not change. `gguf.py` is at
  497 lines: split the field categorisation into `_gguf_fields.py` first.
- Behaviour kept: versions 2 and 3; a version gguf rejects is still a read
  error; truncation is now our own `ValueError` text (the stub's reason
  changes wording, not code). Side effect: tensor types are no longer parsed,
  so a removed quant type (`Q4_0_4_4`, the 3 TinyStories `ValueError` rows)
  no longer fails the read; listed in the recount.
- **A cap hit stops the walk; what was read is kept (ruled 2026-11-23, Q4).**
  When the hop cap, the parsed budget, the string cap or the nesting cap is
  hit inside the key/value section, the reader returns the fields before it
  and no tensor shapes. The array being walked when the cap hit keeps its
  length and type as **declared** (its header count, the walk not having
  reached its end): recorded with a `declared` method in its provenance and
  worded so in the warning, never as measured. An array whose end the walk
  reached (scalars skipped by offset arithmetic within the file, strings
  fully hopped) is measured. `read_gguf` records those fields and says once:
  `WARNING: FORMAT=gguf FILE=<file>: larger than the <N>-<unit> <cap> cap;
  fields from <key> on and the tensor shapes not read [over-cap]` (when the
  cap hit inside array `<key>`, its length is the declared one), through
  `warn_over_cap(..., outcome=...)` (precedent: `fasttext.py` l. 229), the
  outcome a new constant beside `PARAMETER_COUNT_SKIPPED` in
  `messages/_model_stub.py`, the key through `loggable()`. No parameter
  count is recorded. A hit in the tensor-info section keeps every field and
  drops the count with the same warning. Counts that cannot fit in the file
  (`LIMIT_GGUF_TENSORS`/`PAIRS`/`ARRAY`) and an unbounded version stay
  refusals (`model-unreadable`): the data is malformed, not large.
- Evidence level: model fields have no `not_measured` record yet (only
  dataset keys do, `_loom_dataset_keys.py`); the warning is the record for
  now, and the partial read is listed under
  [evidence-levels.md](../design/evidence-levels.md) for when model facts gain one.
- Not in scope: lifting GGUF from the wheel/download `reader-unsafe` gate;
  short arrays as values.

## Message catalogue

No code added or renamed. A partial header is said through the existing
`over-cap` code (its `MODEL_LINE` takes a free outcome); a malformed count
stays `model-unreadable` (`LIMIT_GGUF_*`). New: one outcome constant in
`messages/_model_stub.py` (no `since`: not a code). If the generated
reference shows outcomes, regenerate it (`scripts/generate_message_reference.py`)
and update what the skills quote. PR #515 touches
`src/pitloom/messages/models.py`, `docs/message-codes-models.md`,
`docs/message-codes-files.md` (`over-cap` section),
`skills/*/references/messages-*.md` and `model-stub-diagnosis.md`, none on a
GGUF or ONNX entry. Start the branch from main after #515 merges and re-check
those files for overlap.

## Files

- `src/pitloom/extract/ai_model/onnx.py` (list, producer rule, docstring of
  `read_onnx`).
- GGUF: `formats/gguf_header.py` (new), `formats/_limits.py`,
  `_gguf_bounds.py`, `gguf.py`, `_gguf_fields.py` (split), `_gguf_datasets.py`,
  `messages/_model_stub.py` (outcome constant).
- Docs: `docs/ai-model-scan-limits.md` row "GGUF header budget" (now a
  partial read, not a stub) + hop cap row; `docs/ai-model-formats.md` l. 51
  (GGUF reader row) and l. 160 (defaults list, producer rule);
  `docs/metadata-provenance.md` l. 107 (`file_name_stem`: "or a name derived
  from the writing tool"). The two big docs are already over 30 KB (roadmap
  item): net growth kept near zero.
- Skills: `skills/sbom-generate/references/known-limitations.md` l. 117 (add
  the producer rule) and a line on a partly read GGUF header;
  `skills/sbom-enrich/references/model-stub-diagnosis.md` if it lists what an
  `over-cap` model keeps. Grep `skills/` for `GGUF-header`, `1000000`,
  `exporter default`; a fresh read of each changed reference. No `SKILL.md`
  body documents the cap or the defaults today.
- Working docs: `implementation/ai-model-scan-bounds.md` (GGUF budget
  rationale), `design/model-metadata-readers.md` (step 3 status),
  `design/ai-model-corpus.md` l. 37 ("no large `tokenizer.*` arrays"),
  field notes `model-file-metadata.md` (three defaults; `merged` under
  `onnx.quantize`), security lessons (GGUFReader per-element cost; a vocabulary
  growth crossing a count cap set on 2026 models).
- `CHANGELOG.md`: a Fixed bullet (ONNX default names, Gemma-4 GGUF headers
  read) and a Changed bullet (a GGUF header over a cap is read in part, with
  a `WARNING:`), both linking the PR.

## Tests (each must fail on current `main`; checked with a PYTHONPATH-pinned
run on the base tree)

1. `tests/extract/ai_model/test_onnx_mocked.py` l. 231 parametrize: add
   `merged`, `spox_graph`, `mxnet_converted_model` -> `None`; keep
   `merged_decoder` -> itself (a default only matches whole). Producer rule,
   one case per boundary: `tf2onnx`/`tf2onnx` and `Spox_Graph`/`spox` dropped;
   `foo-bar`/`foo` dropped; `spoxnet`/`spox` kept (no separator);
   `resnet50`/`pytorch` kept; `spox_graph2`/empty producer kept (rule off,
   and not on the list); a blank producer of spaces kept.
2. `test_onnx_integration.py`: a real `onnx.helper` model named `merged` with
   producer `onnx.quantize` -> no name, file stem shown.
3. GGUF real shape (new `tests/extract/ai_model/test_gguf_tokeniser.py`):
   `gguf_builders` grows a `tokeniser(n_tokens, n_merges)` helper; a
   262,144-token / 514,906-merge header is read: name, architecture,
   `tokenizer.ggml.tokens.length` = 262144, `merges.length` = 514906, types
   `STRING`, parameter count from tensors. Built in `tmp_path` (~20 MB,
   ~0.6 s), never downloaded.
4. Cap boundaries: parsed budget at cap and cap+1; hop cap at cap and cap+1
   (monkeypatched `Limits`; one test where only the hop cap trips, one where
   only the parsed budget trips); total parsed string bytes at cap and cap+1
   (cap+1 a partial read); a large `uint8` array is read, with a
   size-ratio timing check (1e3 vs 1e7 elements), not a 63 M one.
5. Partial read: a header whose second array trips the hop cap keeps
   `general.name` and the first array, has no parameter count, and warns
   once `[over-cap]` naming the key; a key with a newline is escaped; a cap
   hit in the tensor infos keeps every field. The array cut mid-walk carries a `declared`
   provenance method; a fully walked one does not. Existing `_HOSTILE_GGUF` cases
   in `test_model_bounds.py` re-pointed: scalar arrays are no longer
   charged; cap hits become partial reads; count-beyond-file cases stay
   refusals.
6. Parity drift guard: new reader vs `GGUFReader` on every fixture under
   `tests/fixtures/aimodels/gguf/` and builder shapes (big-endian, nested,
   empty array, float32 `1e-6`, non-UTF-8 string, `general.datasets`):
   identical fields, raw metadata, shapes, datasets.
7. Surfaces: extend `tests/test_model_producer_surfaces.py` (or a sibling)
   so the Gemma-shaped file, a partly read header (its `[over-cap]` line)
   and a `merged` ONNX come out the same on the CLI (`loom generate` model
   target and project scan), the library (`read_ai_model`,
   `generate_project_sbom`) and the Hatchling hook. The Action runs the CLI:
   no separate test.
8. Classify each new test with `-m platform --collect-only`; mark
   `pytest.mark.platform` (files, mmap).
9. Manual CLI check: cases in `scripts/manual_cli_checks/_checks_model.py`
   (Gemma-shaped header, partial header); no new option, so no
   `_matrix_plan.py` entry.

## Windows dry run

Builders use `write_bytes` (no CRLF); the mmap is closed before `tmp_path`
cleanup (Windows cannot delete a mapped file); no POSIX path in the new
tests; stub reasons quote paths through `quote_source`; the timing test is a
ratio, not seconds. ONNX change has no path logic.

## Recount after the fix

- ONNX, offline now: the probe's `onnx_raw.graph_name` gives the expected
  change without network: 13 Hub files and 1 embedded file lose their name
  and fall back to the file stem (the producer rule adds none).
- GGUF, needs the network probe (not run here): the probe caches results,
  not bytes, in `.cache/s1/results/<sha256(url)>.json`, and keeps a cached
  `reader_error`. Either delete the cache files of the 96 `reader_error` /
  `ModelOverCap` rows (and the 3 `ValueError` rows) or add a retry predicate
  beside `_under_new_cap`; install the fixed Pitloom in the probe's uv
  environment; rerun. Expected: 83 Gemma-4 files and the 12 audio-cpp files
  `read`; Drama-3 and the 3 TinyStories rows reported as found. Check per
  row: `pitloom_fields.name`/`architecture` present, the tokeniser lengths
  in `raw_metadata`, no `[over-cap]` on stderr unless a partial read.
- The paper's own Hub probe (SBOM-MinBench 0.1 sample): the public
  repository's `sbomminbench/experimental/s1-hf-model-headers.jsonl` has 7
  `reader_error` rows, all GGUF `ModelOverCap`, one file each (checked
  2026-11-23): `audio-cpp/audio.cpp-gguf` (`ace-step-1.5-base-bf16.gguf`),
  `farbodtavakkoli/OTel-2.0-Decision-26B-A4B-4bit`,
  `HauhauCS/Gemma-4-E4B-Uncensored-HauhauCS-Aggressive`,
  `Jmica/Drama-3-GGUF`,
  `mradermacher/Goetia-26B-A4B-v1.3-Absolute-Heretic-ARA-GGUF`,
  `unsloth/gemma-4-26B-A4B-it-GGUF`, `unsloth/gemma-4-E4B-it-GGUF`. Same
  procedure (that repository's probe and cache). Expected: the 5 Gemma-4
  files and the audio-cpp file `read`; Drama-3 as found.
- Probe caveat, not Pitloom's: `_gguf_header_complete` decides header length
  with `GGUFReader`, which fails on unknown quant types, so the probe keeps
  widening to 64 MiB; some of its 82 `over_cap` GGUF rows may be that, not a
  large header. Note for SBOM-MinBench.

## Gates

Tier 1 per round (touched tests, linters, SBOM/stderr diff vs main on the
GGUF and ONNX fixtures). Gate A: full suite `-n 4`, every CI linter incl.
pyrefly, each regression test failing on base, branch coverage of changed
files, manual checks `--only` model area. Gate B: mutation testing of
`gguf_header.py`, the adapter and the ONNX list; parity/determinism harness;
Windows dry run; fresh-context sweep; a bounded fuzz run of
`fuzz/fuzz_gguf_header.py` (it goes through `read_gguf`) seeded with the
hostile cases (`_HOSTILE_GGUF`, truncation, huge string length, nesting,
out-of-range type ids, counts beyond the file). PR labelled `test-all-os` (mmap, file
I/O).

## Build notes (2026-11-23)

- Measured on the built reader: the synthetic Gemma-4 header reads in
  0.08 s through `read_gguf` (was 7.7 s through `GGUFReader`), about 0.1 us
  a hopped string; the 4,194,304 hop cap is about 0.5 s.
- Fixture SBOMs and stderr (4 GGUF, 5 ONNX) are byte-identical to `main`.
- A local 60 s mutation run (atheris does not build on macOS) found, on
  `main`, a scalar cut at the end of the file read by `GGUFReader` as an
  empty array: a `TypeError` escaped `read_gguf`. The new reader refuses it
  as a read failure (regression case `value-cut`); the branch ran 13,759
  inputs with no crash. The CI fuzz job is seeded by `fuzz/gguf_seeds.py`.
- `general.datasets` strings are all parsed (within the reader's bounds):
  the datasets cap counts distinct datasets, not elements.
- Tensor data past the end of the file is still refused for every type the
  `gguf` package sizes; an unknown tensor type is read (shape counted).

## Start order (user, 2026-11-23, relayed)

1. Now, on `main`: ONNX list and producer rule, `formats/gguf_header.py`,
   the adapter, the `gguf.py` split and rewrite, the tests. Commit to the
   branch (DCO sign-off).
2. Last: the outcome constant in `messages/_model_stub.py`, the generated
   message reference, the skill references, the docs (`docs/message-codes-*`,
   `skills/**`, `docs/ai-model-*.md`).
3. After #515 merges: merge `main`, regenerate with
   `scripts/generate_message_reference.py`, re-check `messages/models.py`,
   `docs/message-codes-models.md`, `docs/message-codes-files.md`,
   `model-stub-diagnosis.md`, `known-limitations.md`; Gate A; push. No push
   before #515 merges unless the user says so.

## Rulings (user, 2026-11-23)

- Q1: read the 12 audio-cpp files (no declared-element ceiling).
- Q2: option B.
- Q3: add the producer rule.
- Q4: a cap hit keeps the fields read before it, with a `WARNING:`.
- Q5: one PR for both parts.

## Still open

- ONNX gives a model no name field: `GraphProto.name` is "The name of the
  graph". Should `graph.name` become a weak fallback ranked below the file
  stem or a stated name, instead of the model name less a list of defaults?
  It would change names in SBOMs (`inception_v2` -> file stem). Not ruled;
  this PR keeps the list plus the producer rule.

- Whether the probe's `_gguf_header_complete` (GGUFReader) is replaced in
  SBOM-MinBench before the recount (its repository, not this PR).

- `general.datasets` is decoded whole (`_DATASETS_KEEP`), each element
  charged to the parsed budget the tensor infos share: a huge datasets
  array can cost the parameter count. Cutting it at a multiple of the
  1,000-dataset cap would hide distinct entries after duplicates. Kept
  whole; revisit if a real file trips it.
- The producer rule drops a real name that starts with a short producer
  name and a separator (`pytorch-ssd` from `pytorch`). Accepted as ruled
  (Q3); no such file in the probe sweep.

## Gate B notes (2026-11-23)

- Hand mutation, 46 mutants over `gguf_header.py`, the adapter, the field
  mapping, `gguf.py` and the ONNX rule: 44 killed; 2 survivors (array state
  not reset after a pair; a blank producer read as an empty prefix) each
  got a test.
- Fresh-context review: a string length past the end and over a cap was an
  `over-cap` partial read; now malformed whatever the caps. A cut at an
  empty key or a key over a bound names the pair, counted from 1.

## Second review round (2026-11-23, PR #517)

An independent review of `086b180f` and a delta review of its fix:

- Quadratic CPU: the tensor data check multiplied every declared
  dimension (40,000 dims of `2**64-1`: 4 s). Now a tensor of more than 4
  dimensions is malformed, as llama.cpp refuses it (`ggml/src/gguf.cpp`
  l. 661, `GGML_MAX_DIMS` 4 in `ggml/include/ggml.h` l. 49, llama.cpp
  a8f8294c of 2026-11-23); the size product stops once past what the file
  can hold, exactly as the old check decides (a scalar `()` is one element).
- A partial read looked complete in the SBOM: the pairs not reached are
  `raw_metadata_unread`, counted in the artifact-metadata annotation's
  `truncatedKeyCount` (`truncated`), with `maxEntries` only for the entry
  cap. A project's own model files ship and keep no annotation, so there
  the warning alone says it.
- An array of an empty key cut by a bound warns `pair <N> length as
  declared`, matching the recorded `.length`.
