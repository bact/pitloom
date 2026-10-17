---
Created: 2026-10-17
Last-Modified: 2026-10-17
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# G7 honesty rules and information SPDX 3.0.1 cannot record

See also: [g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md) (what G7 needs, in
what order), [roadmap.md](roadmap.md),
[g7-conformance-tests.md](../implementation/g7-conformance-tests.md) (the
tests that hold these rules).

## Rule

An incomplete, honest SBOM beats one that looks complete and is not. Raising
the G7 coverage figure is never a reason to write a value Pitloom does not
know. Concretely:

- A field stays absent when the source does not state it. No `NOASSERTION`,
  empty value, guessed type or default is written to turn a rule `present`
  (`tests/conformance/test_g7ai_carriers.py` fails on a placeholder).
- A value is written only with the strength the source gave it. A Hub card's
  `datasets:` list is the card's claim, not a verified training record; a Hub
  owner is the repository owner, not proven to be the producer. The
  provenance (`Source:`, `Method:`) says which.
- Where SPDX 3.0.1 has no matching property, Pitloom does not stretch a
  neighbouring one to fit without saying so. A workaround is allowed only when
  the SBOM says it is one (the parameter-count comment is the model).
- A coverage figure is the checker's reading of G7, never a compliance claim.
  Rules the checker does not check are listed as unchecked, not as missing and
  not as met.
- Where a choice cannot be made reliably (person or organisation, what a
  count means), Pitloom keeps the weaker form and leaves the upgrade to a
  reviewer or the `sbom-enrich` skill, which records its own provenance.

## What Pitloom cannot reliably do, extract or tell apart

Checked against the code unless marked *to verify*.

| Cannot | Why | What Pitloom does |
|---|---|---|
| Tell a person from an organisation | A name carries no type | Generic `Agent` for a producer (`originatedBy`, and `suppliedBy` for a Hub owner); a typed Agent comes from a fragment |
| Know a Hub owner produced the model | `model_info.author` is the repository owner | Recorded as producer with `Method: repository_owner` |
| Treat a Hub card's datasets as verified | The card lists them | A dataset reference with role `trainedOn` from the card; provenance names the card |
| Say what a parameter count means | A file gives stored tensor elements; the Hub gives its own total; quantisation may pack values (*to verify* per format) | `ai_hyperparameter` `parameters`, with a package comment that it is a count of elements, not a hyperparameter |
| Give a model file a version, producer or time | A bare file often carries none | Left out; the checker reports the rule `missing` |
| Hash a Hub model | Needs a request per file, and a repository has many files | `verifiedUsing` is written only for a local file |
| Canonicalise a licence without the `licenseid` database | The database is built separately | The licence is kept as read; one warning per run |
| Separate a system from its model | A model SBOM's root is the AI package | Both rules read the same package |

## G7 elements SPDX 3.0.1 has no property for

The mapping (`g7ai2026-to-spdx30.sssom.tsv`) marks 25 elements `GAP`, or
leaves them unreviewed. The checker reports them `out-of-scope`. Where Pitloom
reads such information today it records it only as follows:

| G7 element | Read by Pitloom | Recorded as | Honest? |
|---|---|---|---|
| Model parameter count (MDL-009.3) | Yes (file, Hub) | `ai_hyperparameter` `parameters` + comment | Yes: the comment says it is a workaround |
| Model architecture (MDL-009.2) | Yes | Appended to `ai_typeOfModel` after the model type | Weak: one list holds two meanings; a reader cannot tell them apart |
| Context length (MDL-010.3) | GGUF/others, in the source's own key | `ai_hyperparameter`, e.g. `llama.context_length` | Yes, under the source's key; not a G7 key |
| Input and output modality (MDL-010.1/.2) | ONNX graph signatures (and, wrongly, Safetensors tensor names: defect 1) | JSON inside `ai_informationAboutApplication` | Weak: a signature is not a modality; Pitloom does not infer one |
| Known biases | Yes (cards) | Text in the package `comment` | Yes: no property exists |
| Model's whole file metadata | Yes | A source-metadata `Annotation` | Yes: preserved, not interpreted |
| SBOM version, tool version, signature (MD-002/-005/-007) | Tool name only | Nothing | Left out |
| Post-training technique, openness category, data flow, dataset domain/format/synthetic method/copyright status/sensitive category | Not extracted | Nothing | Left out |
| Infrastructure, Security, KPI clusters | Not extracted | Nothing | Out of scope for Pitloom |

`tests/conformance/test_g7ai_sssom_gaps.py` pins the first rows: the elements
the checker cannot check although Pitloom writes a mapped property.

## Known honesty defects (found 2026-10-17, unfixed)

Found while checking the table against the code, not by the checker.

1. **Weights recorded as model inputs.** The Safetensors reader writes each
   tensor key as `inputs` (`{"name": "model.layers.0...weight"}`,
   `extract/ai_model/safetensors.py`, provenance "tensor keys"), and the NumPy
   reader writes an array's shape and dtype as `inputs`. A weight or an array
   is not an input of the model. The assembler puts `inputs` into
   `ai_informationAboutApplication`, so the SBOM says a model takes its own
   weights as input. (ONNX inputs and outputs are real graph signatures.)
   *To verify:* HDF5, Keras and PT2 `inputs`.
2. **Presence is not meaning.** The checker reads `ai_informationAboutApplication`
   as model intended use (MDL-006.4), input preprocessing (MDL-010.4 and
   SLP-008.3) and system input/output, by the property being there. An
   input/output signature is none of these. So these cells are `present` for
   `safetensors` and `onnx` on the strength of defect 1 and of signatures, not
   of any intended-use or preprocessing statement: MDL-006, MDL-006.4,
   MDL-010, MDL-010.4, SLP-008, SLP-008.3. They should be read as `missing`
   (`intended_use` and `unintended_use` come only from cards and the like).
3. **Two meanings in one list.** `ai_typeOfModel` holds the model type and the
   architecture, in that order, with nothing to tell them apart.

Proposed fix, to confirm: stop writing weight names and array shapes as
`inputs` (the file's own metadata stays in the source-metadata annotation; a
tensor inventory, if wanted, gets its own named place); write signature
`inputs`/`outputs` only where the format has them (ONNX); tell the checker
repo that `informationAboutApplication` presence is weaker than the element
(an issue in the rule notes, not a change of its rules); keep architecture
apart from type or name it in the notice below. The expected table then
loses those cells: that is the point.

## Extractable but not recordable: a notice

Proposed, not built. When a reader finds a value that belongs to a G7 element
with no SPDX 3.0.1 property and Pitloom has no honest way to record it, say so
once, so a reader of the log knows the SBOM is silent on purpose and not
because the source lacked it.

- **Level.** `INFO:` when the value is simply not written. `WARNING:` when it
  is written through a stretched property (architecture in `ai_typeOfModel`, a
  modality inferred from a shape), because the SBOM could mislead.
- **Shape.** One line per source, not per field, in the shared literal prefix
  style: `FORMAT=gguf FILE=m.gguf: not recorded, no SPDX 3.0.1 property:
  context_length, post_training_technique`. `KEY=VALUE` pairs, a value that may
  hold a space last.
- **Not for absence.** A field the source does not carry stays silent
  (`CLAUDE.md`: absent source data is not an error). The notice is only for a
  value that was read and dropped.
- **One helper.** One function builds the line, as the `FORMAT=%s FILE=%s`
  warnings do, so the wording cannot drift across readers.
- **Tests.** Per reader: a source with the value logs the notice once; a source
  without it logs nothing; the SBOM bytes do not change; the names listed are
  the G7 element names, so a new SPDX property that makes one recordable
  removes it from the list (a drift guard against `EMITTED_BUT_UNCHECKED` and
  the mapping snapshot).
- **Surfaces.** CLI, library, hook and Action all go through the readers, so
  one place covers them; `--quiet` behaviour follows the existing logging.

Open: whether the notice defaults on or sits behind a flag (it is stderr only
and does not touch the SBOM); and the exact list of names per reader, from a
sweep of what each reader reads and drops.

## Rules for each coverage increment

1. Before flipping a cell, state in the increment log what the source said and
   what Pitloom did not infer.
2. Add a test where the source lacks the value and the cell stays `missing`.
3. Add the element to the table above if it can be read but not recorded.
4. If a flip rests on a weaker form (generic Agent, the card's claim), say so
   in the provenance and in the log entry.
