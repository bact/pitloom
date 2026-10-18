---
Created: 2026-10-17
Last-Modified: 2026-10-17
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Support tiers and demo scope

See also: [roadmap.md](roadmap.md),
[g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md),
[g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md),
[ai-model-formats.md](../../docs/ai-model-formats.md) (what each format gives).

Decided 2026-10-17 (user) so that a demo can be finished by the weekend.

## Tiers of AI model file formats

| Tier | Formats | Policy |
|---|---|---|
| 1 | Safetensors, ONNX, GGUF, NumPy, fastText, and the Hugging Face Hub as a source | The most complete support. Every feature and every G7 increment is built and tested here first |
| 2 | Keras, HDF5, PyTorch classic, PT2 / ExecuTorch, CRFsuite | Kept working. A bug fix may wait; it is written down, with a follow-up, and not silently dropped |

Rules:

- A lower-tier gap is documented where users read it
  (`docs/ai-model-formats.md`) and listed in the follow-ups below, with what
  is missing and the format's reader.
- A fix that makes an SBOM dishonest (a value that is not true) is not a
  completeness gap: it is fixed in any tier. The model-inputs fix of
  2026-10-17 touched PT2 for that reason.
- New formats start in tier 2.

## Demo scope

| Axis | In scope |
|---|---|
| Minimum elements standard | A few clusters of G7 SBOM for AI: Metadata, System, Model, Dataset |
| SBOM format | SPDX 3.0 (3.0.1) |
| AI model formats | Safetensors, ONNX, fastText, GGUF (tier 1 also lists NumPy: see open questions) |
| Python build backends | Hatchling, setuptools, Poetry |

Out of scope for the demo: the Infrastructure, Security and KPI clusters; other
standards (NTIA, CISA, BSI) and SBOM formats; tier 2 formats beyond keeping
them working.

## Parity principle

Every feature behaves reasonably alike across the usage surfaces (CLI, library,
Hatchling hook, GitHub Action, skills) and across file formats. It does not
have to be at once: a gap is allowed if it is listed with a target date.

Parity ledger (a gap, where it is, what it needs, target). Targets are to be
set; none is invented here.

| Gap | Surfaces or formats | Needs | Target |
|---|---|---|---|
| Hub model has no file hash (MDL-007/008) | Hugging Face source | A per-file hash request or a Merkle root over file hashes | to set |
| Dataset licence, provenance and statistics reach no model SBOM | all (no reader feeds Croissant in) | A reader route, then the `loom` SDK (B7) | to set |
| `INFO:` notices for information read but not recordable | all readers | The shared helper in the honesty doc | to set |
| Model files carry no version, producer or time | tier 1 file formats | Nothing to read: stays `missing` | n/a |
| G7 scenarios: model files, a Hub model, a library-built model and a project per backend | done 2026-10-18 | Hatchling, setuptools and Poetry give the same G7 outcomes | done |
| A setuptools project ships a model only when `package-data` lists it | setuptools | Nothing: the SBOM describes what would ship | n/a |
| Tier 2 formats | Keras, HDF5, PyTorch, PT2, CRFsuite | Anything beyond keeping them working | to set |

## Demo on 2026-10-19: decisions of 2026-10-18

- Hugging Face and NumPy are tier 1 and in the conformance table (scenarios
  `hub` and `numpy`).
- A project that ships only an AI model, with no system of its own, is judged
  by the model for the System-level (SLP) properties: done in the checker,
  which names the model it judged (`systemJudgedByModel`).
- The ledger below says, per gap, what is missing and when it will be fixed;
  dates are for the user to set.

## Demo: a proposed definition of done

1. Table scenarios for the four demo formats, NumPy and a project per backend,
   each with expected cells and the honesty guards.
2. A coverage report for those scenarios, with the previous iteration's
   figures.
3. The tier and parity ledger above published in the user docs, in the user's
   words (no link into `working-docs/`).
4. Known honest gaps listed on the demo page: what Pitloom leaves out and why.

## Open questions

- NumPy is tier 1 but not in the demo's format list. Keep it in tier 1 and
  out of the demo, or add it to the demo?
- Hugging Face Hub is a source, not a file format. Does it stay in the demo?
- Parity targets (dates) for the ledger.
