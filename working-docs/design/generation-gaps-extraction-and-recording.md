---
Created: 2026-10-23
Last-Modified: 2026-10-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Generation gaps: extraction gaps and recording gaps

See also: [g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md)
(the honesty rules and the G7 tables this page sorts),
[sbom-format-gaps.md](sbom-format-gaps.md) (the ledger of recording gaps),
[g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md),
[provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md),
[roadmap.md](roadmap.md), issues
[#110](https://github.com/bact/pitloom/issues/110) (a provenance profile) and
[#147](https://github.com/bact/pitloom/issues/147) (SPDX 3.1).

> **Status (2026-10-23):** a way of sorting what is already written down; the
> mechanisms in [Recording a gap](#recording-a-gap-the-ladder) beyond the first
> two are unbuilt and untested. Nothing here changes the output.

A minimum element (a G7, BSI, CISA, FSCT or NTIA field) can be missing from an
SBOM for two unrelated reasons. They have different owners, different fixes and
different tests, and the docs mixed them.

1. **Extraction gap**: Pitloom cannot obtain the value, or cannot decide
   between several. The question is *can we extract it, or resolve a conflict
   about it?*
2. **Recording gap**: Pitloom has the value but the format has no place for it.
   The question is *can we record it in the serialisation?* The answer depends
   on the format's specification, so a way to record it has to be invented, and
   said to be invented.

| | Format records it | Format cannot record it |
| --- | --- | --- |
| **Pitloom can extract it** | Built: the cell is `present` | **Recording gap**: a workaround or an extension |
| **Pitloom cannot extract it** | **Extraction gap**: the field stays absent | Both; the recording gap waits on the extraction one |

## Extraction gaps

The value is not in a source Pitloom reads, is in one it does not read yet, is
in several that disagree, or needs a judgement.

| Kind | Example (checked against the code, 2026-10-23) | Where it is fixed | Meanwhile |
| --- | --- | --- | --- |
| The source never carries it | A bare Safetensors file has no version, producer or time | Nowhere: a fragment or the user supplies it | Absent; no `WARNING:` (absent data is not an error) |
| The source carries it; no reader | Hub `config.json` fields no reader maps; a Hub model's file hash (a request per file) | The extractor: [model-metadata-extraction.md](model-metadata-extraction.md), [known-bugs.md](known-bugs.md) | Absent |
| Sources disagree | A fragment against a value read from the file; two fragments; a lock file against an installed version | The merge rules: [docs/fragments.md](../../docs/fragments.md), issue [#150](https://github.com/bact/pitloom/issues/150), provenance in the SBOM | The earlier element wins, with a `WARNING:`; a value Pitloom only generated yields to a fragment's (#349) |
| Needs judgement | A person or an organisation; what a parameter count means; a modality from a tensor signature | The `sbom-enrich` skill or a fragment, each recording its own provenance | The weaker form (a generic `Agent`) |
| Not an artefact fact | Data flow, security controls, infrastructure, KPIs | Out of Pitloom's scope | Absent |

Rules that already hold: absent source data stays absent and silent; a value
carries the strength its source gave it; no placeholder turns a rule `present`.
An extraction gap is tracked in the extractor's design doc or `known-bugs.md`,
not in the format ledger.

## Recording gaps

Pitloom holds the value, and SPDX 3.0.1 has no property for it, a broader one,
or one used for two meanings. Each is an entry in
[sbom-format-gaps.md](sbom-format-gaps.md) (FG-n). Today's cases:

| Element | Extractable now | Recorded as |
| --- | --- | --- |
| Parameter count | File and Hub | `ai_hyperparameter` `parameters` plus a comment saying it is a workaround (FG-1) |
| Architecture | GGUF, Safetensors, Hub | Appended to `ai_typeOfModel`: two meanings in one list (FG-2) |
| Context length | GGUF, Hub | `ai_hyperparameter` under the source's own key, not a G7 key |
| Input and output | ONNX, Keras, HDF5, PT2 signatures | JSON in `ai_informationAboutApplication`, read as intended use by presence (FG-3) |
| Post-training technique | Hub `base_model` relation, GGUF file type | Comment on the `descendantOf` relationship, a `quantization` hyperparameter |
| A model's known biases | No reader; a fragment or the SDK can give them | Text in the package `comment` (`Known biases: …`); a dataset's biases have a native property, `dataset_knownBias`, which the Croissant reader fills |
| SBOM tool version | Pitloom knows its own | Nothing: 3.0.1 has no Tool version (3.1 adds one) |
| The rest of the 25 catalogue-only G7 elements | Mostly not | See FG-4 |

## Recording a gap: the ladder

From least to most invented. Take the first rung that is honest for the fact.

1. **A broader native property, with the workaround stated in the SBOM** (the
   parameter-count comment). Visible to every consumer and to the checkers. It
   must say it is a workaround, or it is a stretched property recorded silently.
2. **A Pitloom-owned `Annotation` statement** with its own schema URL, as the
   provenance (`https://pitloom.dev/provenance/fields/1`) and the artefact
   metadata statements already are. A custom taxonomy would key one statement
   by the mapping's element slug (`g7ai2026:model-architecture`) so the fact has
   one unambiguous place. Standard SPDX tools keep it and ignore it, and a
   conformance checker does not count it, so it preserves a fact without
   flipping a cell. Unbuilt.
3. **An SPDX 3 extension.** The v3.0.1 bindings Pitloom uses carry
   `extension_Extension` and `extension_CdxPropertiesExtension`; whether
   Pitloom's serialiser, the SHACL validation and the consumers accept an
   extension element is untested. Issue #110 asks for a provenance profile on
   the same footing. Unbuilt, untested.
4. **A proposal to the standard**: the FG entry, grouped and written up. SPDX
   3.1 (issue #147) adds some of what the mapping lists (a Tool version, a
   Hardware profile), which retires an entry when Pitloom writes 3.1.

Constraints on every rung: the SBOM still validates against the SPDX schema and
SHACL; output stays deterministic; the honesty rules apply (say that it is a
workaround; never a placeholder); the notice
(`FORMAT=… FILE=…: no SPDX 3.0.1 property: …`) stays for what is not recorded
natively. A fact recorded on rung 2 or 3 appears in the coverage report as
"emitted but unchecked" (`EMITTED_BUT_UNCHECKED`), not as `present`, until the
checker reads it.

## What AI enrichment can and cannot do

The `sbom-enrich` skill works on the first kind of gap. It can read prose
(a README, a model card) and propose a value for an element the file does not
state, or weigh sources that disagree, and it records its own provenance. It
cannot widen the format: whatever it proposes is written as a fragment of
ordinary SPDX 3.0.1, so an element with no property stays unrecordable, however
well the skill knows the value. A recording gap is closed by a change to
Pitloom's output (one of the rungs above) or to the standard, not by a better
guess. So the skill:

- helps with extraction gaps of the *needs judgement* and *source never
  carries it, but the project's prose does* kinds, each value tagged with its
  weaker provenance, and never as a placeholder;
- does not stretch a property to make a recording gap look closed; it writes
  only into a place Pitloom already records the fact (the stated workarounds),
  and reports the rest as not recordable (`SKILL.md`, step c of the
  minimum-elements workflow).

A value the skill proposes for an element that has no honest place is kept for
the user's report. It is not written, and it does not flip a checker cell.

## Open questions

1. Which rung for architecture and context length, the two cases where rung 1
   is weak? A rung-2 statement beside the existing entry, or replacing it?
2. Does an SPDX extension element validate and round-trip through the JSON-LD
   serialiser and `spdx3-validate`? A one-element experiment answers it.
3. Should the checker read a Pitloom statement (rung 2) as evidence? That makes
   a coverage figure depend on a Pitloom-only convention.
4. Sort the gap tables of `g7-ai-sbom-coverage.md` and the G7 page of `docs/`
   by kind (extraction or recording), so each gap names its owner. Not done.
