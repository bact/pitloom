---
Created: 2026-09-20
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Canonical output: names and key-order residue (follow-ups)

See also: [roadmap.md](roadmap.md) (entries) and "SBOM output" in
[CLAUDE.md](../../CLAUDE.md) (bit-for-bit determinism, RFC 8785, UTC).

Found during the PR #227 review. One principle: **the same input must give
the same bytes, and the same real-world thing must give the same identifier,
whatever the file format or surface.** Each item below is a policy first, then
one shared helper, then a test that runs every format/surface through it.

Sorted dict keys (for AI model metadata), UTC `Z` datetimes and LF line
endings were built in step 6.5 -- see
[sdist-own-config.md](../implementation/sdist-own-config.md). What is left:

## 1. Key-order residue

- **Not audited yet:** project-metadata sources (`pyproject.toml`,
  `setup.cfg`, lock files, installed metadata) for any dict/set emitted in
  source order.
- **Deliberately unsorted:** list-valued fields such as `inputs`/`outputs`
  (tensor or I/O names) keep the source order, which can be meaningful
  (ONNX I/O). Decide per field whether that order is semantic before
  sorting it.

## 2. Names in identifiers

- **Done (IRI validity):** every id and namespace segment built from a name
  is percent-encoded by one helper (`pitloom.core.iri`), lossless and
  byte-identical for already-valid names; `name` keeps the source text. See
  [iri-name-encoding.md](../implementation/iri-name-encoding.md).
- **Open: name comparison across types.** Package names compare under
  PEP 503; AI model, dataset and fragment names still compare as raw strings
  (registry keys, lineage lookup by `name`). Decide whether case or Unicode
  normalisation applies there -- a matching question, separate from the id
  encoding above.
- **Open: `pitloom.loom` run namespaces.** One run mints ids under several
  `doc_name`s -- the model name, each dataset name, the script path and
  `"loom"` -- with a random `uuid4` document uuid, so one fragment spans
  several namespaces and differs every run. Found while fixing the encoding.
- **Open: `loom model` registry lookup key.** `generate_model_sbom()` looks
  the model up by file stem (`weights`), while `loom id import` and harvest
  key it by element `name` (its title). For a model whose title is not its
  stem, an imported id is never reused and a new one is minted. Decide one
  key, or try both as `pitloom.loom.run()` does with its name list.
