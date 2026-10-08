---
Created: 2026-10-08
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model corpus: real-world fixtures to size and rank hardening

Status: idea, not started. Noted 2026-10-08 during the #294 reviews.

See also: [roadmap.md](roadmap.md),
[model-metadata-readers.md](model-metadata-readers.md),
[known-bugs.md](known-bugs.md),
[tests/fixtures/README.md](../../tests/fixtures/README.md),
[ai-model-scan-security-lessons.md](../implementation/ai-model-scan-security-lessons.md).

## Why

The resource and security controls (entry cap 1,000, label cap 4,096 bytes,
chunk cap 1 MiB, name cap 1,024, header bounds, wheel gate, byte budget)
are set from format knowledge and synthetic hostile files. Several are of
merit, but with few real data points we cannot say how likely each is to
trigger, so we cannot rank them or tune a default. Readers are also
checked against the few files we hold; every metadata-correctness round
(#294) found format quirks only a real file exposed (older ONNX IR listing
weights as inputs, `.pt2` layouts, big-endian GGUF, `num_features` in
`FEAT`, not the header).

## What we hold

About 25 files, mostly tiny, many hand-built or from one tool version:

| Format | Fixtures | Gap |
|---|---|---|
| GGUF | 4 (about 3.5 MB) | one producer family; no big-endian or v2 real file; no large `tokenizer.*` arrays |
| ONNX | 5 (about 13 MB) | few exporters; no external-data model; no `ai.onnx.ml` model |
| Safetensors | 5 | no kohya/LoRA file with `ss_*` keys; no sharded index |
| fastText | 2 | no unsupervised (cbow/skipgram) model; one `.ftz` |
| CRFsuite | 2 (+5 PyThaiNLP, out of tree) | no model with many labels |
| PyTorch / PT2 | 2 / 1 | no real `torch.save` zip from a major model; `torch` not installed |
| Keras / HDF5 / NumPy | 1 / 1 / 4 | no Keras v3 zoo model; no large `.npz` |

## What to collect

- **Small models, many of them:** diversity per byte. Different producers,
  versions, languages (Thai, CJK, RTL names and labels), odd but legal
  metadata (empty, unicode, long keys, duplicate keys, numbers at the edge
  of their type), each format's older and newer layouts.
- **Large models, a few of them:** the boundaries the caps exist for. Many
  tensors, thousands of metadata keys, big vocabularies in GGUF, long
  `metadata_props`, large label sets, multi-GB files for streaming and
  memory behaviour (only header reads; never load the weights).
- **Hostile-but-real:** files in the wild that violate their own format
  (truncated downloads, Git LFS pointers, renamed extensions, wrong
  endianness). Keep synthetic hostile files separate (`hostile/`).

## How to hold it

- Not in the repository: licence and size. A small curated set (permissive
  or CC0 licence, each under a few hundred KB) may be committed with a
  `details/` note; the rest lives outside, listed in a manifest with source
  URL, licence, size and SHA-256, fetched by a script into a cache.
- Tests that need the corpus are marked and skip when it is absent; the CI
  default stays small. A scheduled job may run the whole corpus.
- Never redistribute a model whose licence forbids it; record the licence
  per entry (our own tool can read it).

## What to measure

Per file and per format, from one run over the corpus (a small script, not
a product feature):

- how often each cap or bound is hit (entries, labels, label bytes, name
  length, chunk size, depth), and the distribution behind it;
- header read time and peak memory against file size;
- metadata key counts and the longest name, key and value;
- how often each reader warns, stubs, or finds no name, version or licence;
- disagreement with the reference library (the correctness checks used in
  the #294 review, automated).

The output ranks hardening work by observed likelihood and shows whether a
default (for example 1,000 entries) sits well above real files or close to
them.

## Open

- Where the out-of-tree corpus lives and who may fetch it (CI cache,
  release artefact, a separate repository).
- A privacy rule: collect counts and distributions, not model text, into
  any shared report (training text can sit in names and vocabularies).
- Whether the PyThaiNLP models and Hugging Face small models are enough for
  a first pass, and which large GGUF/ONNX/Safetensors files to start with.
