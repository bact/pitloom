---
Created: 2026-10-01
Last-Modified: 2026-10-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Lessons from scanning AI models in untrusted packages

See also: [ai-model-scanning.md](ai-model-scanning.md) (the design as
built), [model-metadata-readers.md](../design/model-metadata-readers.md)
(the planned header-only readers), `docs/ai-model-scan-limits.md` (the
user-facing caps).
See also: [SBOM generator field notes](sbom-generator-field-notes/README.md).

Experience notes from PR #263 (scan AI models inside built wheels), written
as raw material for a paper on building an SBOM generator for AI artefacts.
Every number below was measured (peak resident memory under a watchdog,
macOS, CPython 3.10 unless stated); "PLAUSIBLE" findings are left out.

## 1. Setting

- Pitloom generates SPDX 3 SBOMs for Python packages, including the AI
  models they ship (`ai_AIPackage` elements with format, hyperparameters,
  inputs/outputs). Before #263 only a project directory was scanned; #263
  added scanning inside built wheels.
- **Threat model change.** A project directory is usually the user's own
  tree. A wheel is often someone else's: a dependency, a download, a pull
  request artefact in CI. The SBOM generator becomes a parser of hostile
  input, run automatically, often in CI with no human watching.
- **The core tension.** An SBOM wants as much metadata as possible; every
  extra field read is attack surface. Model formats are designed for
  loading, not inspection, and their libraries parse (or load) far more
  than an SBOM needs.
- Formats involved: GGUF, ONNX, PyTorch (`.pt` pickle and zip, PT2),
  Safetensors, Keras (v3 zip, legacy HDF5), NumPy (`.npy`, `.npz`),
  fastText.

## 2. How the problems were found

Nine review rounds over the one PR, each by a separate AI reviewer agent
(Claude Opus) with a fresh context, fixes by another agent (Claude Sonnet),
coordination and design decisions by a third, decisions confirmed by the
human maintainer:

| Round | Scope | Notable outcome |
|---|---|---|
| 1-2 | PR, security | Native-library crashes/hangs, decompression bombs, log injection, aggregate size |
| 3 | fixes of round 2 | GGUF bound bypassed three ways; stderr race |
| 4 | fixes of round 3 | Python dict memory never released |
| 5a | fixes of round 4 only | Non-determinism from a Rust hash map; Python 3.14 hang |
| 5b | whole PR, fresh reviewer | A fix of 5a lost model names; ZIP central-directory bomb |
| 5c | fixes of 5b only | Our own ZIP pre-check disagreed with `zipfile` three ways |
| 6 | whole PR | `.pth` path-config files taken for PyTorch models; DEBUG names unescaped |
| 7 | surfaces, skills, docs, comments | no code bug; stub test wrong under `--enrich`, mislabelled library ceiling error, stale docs |

What made the reviews productive:

- **Measure, don't reason.** Every resource claim was checked with a
  hostile input under a watchdog (RSS limit plus timeout). Several "this is
  bounded" arguments that read correctly were false when measured.
- **Each fix round introduced the next round's top finding.** Round 3's
  bounds were bypassable; round 5a's determinism fix lost model names;
  round 5b's ZIP check was bypassable. A short review of each fix commit
  alone was worth more than another whole-PR pass.
- **Alternate narrow and wide reviews.** Narrow (one fix commit) finds
  regressions in new code; wide with a reviewer that never saw earlier
  rounds (5b) found what anchored reviewers had stopped questioning.
- **Mutation testing as the test-quality check.** Surviving mutants
  pointed at missing boundary tests (exactly-at-cap, budget filled
  exactly), vacuous tests (an assertion that passed with the guarded check
  removed) and equivalent mutants that prove nothing.
- **Agents break process rules under pressure.** Fix agents occasionally
  ran a forbidden git write or wrote outside the scratch area; restating
  the hard rules at the top of every brief, and verifying afterwards,
  was necessary.

## 3. Findings by class

The findings, by class, are in three parts:

- [ai-model-scan-security-lessons-parsers-and-archives.md](ai-model-scan-security-lessons-parsers-and-archives.md):
  3.1 the library parses far more than the SBOM needs, 3.2 native code
  in-process, 3.3 archives inside archives.
- [ai-model-scan-security-lessons-runtime-and-output.md](ai-model-scan-security-lessons-runtime-and-output.md):
  3.4 Python runtime surprises, 3.5 logs and terminals are an output
  channel, 3.6 determinism.
- [ai-model-scan-security-lessons-transparency-and-correctness.md](ai-model-scan-security-lessons-transparency-and-correctness.md):
  3.7 transparency, 3.8 correctness bugs found on the way, 3.9 found while
  planning the next fixes, 3.10 Git LFS pointers.

## 4. Principles that came out of it

1. An SBOM generator must read metadata, never load the artefact the way
   its runtime does.
2. Bound declared structure (counts, lengths, nesting) before any parser
   runs; byte ceilings alone do not bound work.
3. A pre-check must use the parser's own decision procedure, or it will
   disagree with the parser on hostile input. Nuance: a pre-walk built on
   the parser's own decoder inherits its conversions (`genops` calls `int()`
   on decimal text before yielding), so it pays the parser's costs and
   limits before any bound of yours applies. Reuse the opcode table, not
   the decoder.
4. Fail closed on anything the check does not understand (unknown
   versions, a missing private API).
5. Gate native and amplifying parsers for untrusted input; make the
   opt-in explicit and not settable from the untrusted input itself.
6. Keep what cannot be read as a visible, minimal entry with one message;
   never drop it silently.
7. Every cap needs a stable order for what it keeps, a message when it
   bites, and a documented effect on output.
8. Treat logs as an output channel to an untrusted terminal or CI runner.
9. Measure every resource claim with hostile input under a watchdog;
   review every fix commit on its own.
10. A detection threshold must stay looser than the refusal cap, or an
    over-cap file is misclassified rather than refused; and it must match
    the library's own bound, inclusive or exclusive.
11. Take identity from what the artefact declares, chosen by a rule close
    to its ecosystem's installer (Pitloom is laxer: where the file name names
    none it falls back to a single mismatched `.dist-info` with a `WARNING:`,
    where pip refuses), and check the rule against real artefacts before
    adding options for cases nobody has.
12. Decide "is this a model" from content that cannot contradict the
    name, and once decided, list it whatever happens when reading it. A
    suffix that trusts any header (`.onnx`, `.h5`) is still contradicted by
    a known text signature: a Git LFS pointer is no model under any suffix.
13. Never decode a numpy `object` array through `tobytes()`: it holds
    pointers, so the "text" differs per run. Decode per element, but only
    where `dtype.hasobject`: a fixed-length `S`/`U` array has stable bytes
    and must keep a bulk path (a Python object per element costs ~160
    bytes; a fix for one bug class, pointer bytes, must not open another,
    memory). Decide on `dtype.hasobject`, not `kind`: a compound dtype with
    a string field has `kind == "V"` and still holds pointers.
14. A value read from untrusted JSON that reaches a typed output field
    (a name, a class) needs a type check, and deep nesting needs a
    `RecursionError` guard; both are per-attribute problems, not a crash.
15. A value can have a dtype and no data: an HDF5 attribute with an empty
    dataspace (`h5py.Empty`) has `.dtype` but no `reshape`/`tolist`, so a
    decoder that dispatches on `dtype` alone raises `AttributeError`, outside
    the errors an attribute read catches. Treat it as absent.
16. A placeholder for content that was never fetched (a Git LFS pointer)
    is a state of the checkout, not of one file: detect it exactly, report
    it once per run, and never let its bytes stand for the content's
    identity (a model entry, a registry key).

## 5. Status at the time of writing

- #263 after round 7: the ZIP check (round 5c) uses `zipfile._EndRecData` on
  one handle and walks the real directory; every round-5c repro is refused at
  43-65 MB (was 797-844 MB), on 3.10 and 3.14, and the hostile wheel scan
  dropped from 831 MB to 44 MB.
- Header-only readers, planned (only the pickle walker and CRFsuite are built in
  0.21.0): they remove the
  library-amplification and native-code classes (3.1, 3.2, most of 3.4's
  stderr work) but not the archive, determinism and transparency classes;
  see [model-metadata-readers.md](../design/model-metadata-readers.md),
  "What the readers remove, and what stays".
