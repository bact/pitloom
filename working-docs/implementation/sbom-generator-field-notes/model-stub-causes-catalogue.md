---
Created: 2026-10-30
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: why a model has no metadata, as a catalogue of causes

See also: [README.md](README.md) (index of these notes),
[message-catalogue-decisions.md](message-catalogue-decisions.md) (decisions
A to M this PR applies),
[provenance-injection-and-message-contract.md](provenance-injection-and-message-contract.md)
(section 2: the messages as a contract with the skills),
[message-catalogue-and-skills.md](../../design/message-catalogue-and-skills.md)
("The model-stub causes": D1 to D12),
[model-file-metadata.md](model-file-metadata.md),
[evidence-levels-and-provenance-of-absence.md](evidence-levels-and-provenance-of-absence.md)
(the cause in the SBOM, parked here),
[open-research-questions.md](open-research-questions.md).

Work of 2026-10-30: #404 (merged), catalogue PR 1a (commits ebd03963,
fab92221, f79c9b5b, 98935f5a). The maintainer took the plan's twelve
recommendations, D1 to D12.

## 1. The problem the family answers

- A model file Pitloom cannot read still becomes a stub in the SBOM: a
  package or file entry for the model with none of its metadata. The cause
  decides what a user can do (install an extra, supply another file, raise
  a cap, nothing), and the skills tell them. Before #404 the cause was in
  free text, in more than one wording (D7); the skills quoted wording by
  hand
  ([provenance-injection-and-message-contract.md](provenance-injection-and-message-contract.md),
  section 2).
- The catalogue gives each cause a code; the skill reads advice from the
  generated reference, not from the line.

## 2. Six codes, named by cause

| Code | Condition | Meaning (short) |
| --- | --- | --- |
| `library-missing` | `missing` | an optional library the step imports is not installed |
| `reader-unsafe` | `unsafe` | a wheel's model formats whose reader is not run on a wheel's files (`--trust-wheel-model` lifts it) |
| `model-unreadable` | `unreadable` | a reader failed, or a bound check refused the file |
| `model-wrong-format` | `wrong-format` | not an AI model file of a supported format |
| `parameter-count-invalid` | `invalid` | a tensor dimension or a stated count is not a non-negative integer; no count recorded |
| `hyperparameter-conflict` | `conflict` | a model's own hyperparameter named `parameters` is replaced by the parameter count |

(Meanings from `docs/message-codes.md`, generated.)

Rules applied (decision B of the taxonomy, D1): a family is named by its
cause, subject first; a test holds every family to its condition or to a
subject plus `-<condition>`. Not coded here: `model-gated` (a response,
not a cause) and `not-a-model` (merged into `wrong-format`).

## 3. Decisions that were not obvious

- **D2: `library-missing` owns its text.** `required library not
  installed: <module>; install pitloom[<extra>]`. The extra is a closed
  field: the old text said `pip install gguf` (the package); the user is
  now told the extra (CHANGELOG, #404). It covers *every* optional library
  a step imports (`pitloom.core.optional_libraries`): the model readers,
  the Hugging Face Hub client, `spdx3-validate`, PyPA `build` and
  `magika`. Actor is `user`
  (D3), because an extra changes the environment and runs native parsers
  on the user's files: the advice is for the user, not for an agent to
  run.
- **A behaviour change comes with it.** A missing `magika` or PyPA `build`
  now raises `ImportError`, not `RuntimeError` (CHANGELOG, #404); the
  exception carries the code (`CodedImportError` stands beside
  `CodedValueError`, both copyable and picklable through one mixin; the
  `RemoteSourceError` that raised `TypeError` on copy was fixed in #396).
- **A field name swallowed by a parameter.** No catalogue field may share
  a name with a parameter of `emit` or of a coded exception: a field
  named `extra` was swallowed by `emit`'s own parameter, and the clash is
  now tested (design record).
  Do: when a template engine passes named values through a function, test
  the field names against that function's parameters.
- **D4 and D5: one `model-unreadable`, with a closed detail.** A reader's
  failure is free text (`<error>`); a bound check's reason is a closed
  table of six texts the readers raise from `pitloom.messages`, and an AST
  test holds every `ModelLimitExceeded` raise to it. No variant, because
  the advice and the SBOM effect do not differ (decision C).
- **D6: a closed field may repeat in a line**, a free one may not:
  `FORMAT=<format> FILE=<file>: header is not <format>; ...`. The design
  record gives no reason for the asymmetry; a closed value has a fixed
  vocabulary, a free one does not (*inference*).
- **D7: `read_ai_model()` refuses a file no reader reads in the words
  `loom model` uses** (`not an AI model file of a supported format`), not
  "Unsupported model format ... Supported extensions". One code, on every
  surface; effect `thinner` (D8). The library and the single-file commands
  had said it in different words.
- **D9: a reader's raise is detail, not a message.** A raise in
  `extract/ai_model/` (but the dispatch `reader.py`) is out of the ratchet
  by location, because only the scanner calls the dispatch and only the
  dispatch names a reader (both tested): 25 sites. With 15 sites coded the
  ratchet fell from 556 to 516 uncoded sites (172 to 163 modules; commit
  ebd03963). The scanner's line is the message; a reader's text is its
  detail (decision J).
- **D10: row 1 is split.** 1a is this PR (the 18 covered sites and the
  detail rule). 1b (also 0.22.0) takes the 27 sites of fields read in
  part. Six sites moved to later PRs. The design record's counts and the
  migration plan's row-1 count (68 sites) are in different units and were
  not reconciled for these notes.
- **D11: the generated catalogue has its own page.** `docs/message-codes.md`
  holds what the generator writes; `docs/messages.md` keeps the line
  grammar, what a code guarantees and the trust rule (f79c9b5b). The
  generator also writes both skills' `references/messages.md` and, behind a
  second marker, the model table of the enrich skill's
  `model-stub-diagnosis.md` (what each code leaves of a model), which a test
  holds complete.
- **D12, parked: the cause in the SBOM.** An entry for a model with no
  metadata does not say why. `Reason:` on a format-only entry would need
  three more reason codes, a carrier on `AiModelMetadata`, merge
  semantics and an edit to the frozen scan-limits page. After 0.22.0. This
  is the same gap as
  [evidence-levels-and-provenance-of-absence.md](evidence-levels-and-provenance-of-absence.md):
  stderr says why; the SBOM, which outlives the run, does not.

## 4. Same code on every surface

A project scan, a wheel scan, `loom model`, `loom enrich`, `loom generate`
naming a file, `loom model` naming a Hub model without its client, the
Hatchling hook and the library each end the line in its code
(`tests/test_model_stub_surfaces.py`, 303 lines). An outcome-parity test
holds each kind of file to one code on every surface; the GitHub Action
keeps an `INFO:` line's code in its `::notice::` annotation (fab92221).
This is the "a test on one surface does not cover the others" rule of the
usage-surfaces section of `AGENTS.md`, applied to a code.

## 5. A generated page and a Windows checkout

The new page is generated; a Windows checkout rewrites line endings to CRLF
and the generator's `--check` then reads the page as stale. `.gitattributes`
now keeps the page LF, and a test holds every generated file to that rule
(f79c9b5b).
Do: a generated file that a test compares byte for byte needs an
`.gitattributes` entry, and a test that every such file has one.

## 6. Left open

- **A found-but-failing import is reported as not installed.** The readers
  raise `missing_library()` from any `ImportError`, so a library that is
  installed but fails to load (a native extension for another ABI, a
  broken wheel) is told "install pitloom[gguf]", which the user has done.
  The design record says this is unchanged from before; that the advice
  then misleads is an inference. Not measured: how often it happens.
- The `Build:` warning for a missing PyPA `build` keeps no code: its
  prefix is no frame yet (migration step 6).
- `hyperparameter-conflict` is the first entry whose actor and effect are
  both `none`: the SBOM states what the input holds and nobody needs to
  act.
- Whether an agent that reads the code behaves better than one that reads
  the free text is not measured (see the open questions).
