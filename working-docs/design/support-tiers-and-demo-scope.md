---
Created: 2026-10-17
Last-Modified: 2026-10-18
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
  (`docs/g7-sbom-for-ai.md`, "Gaps by format and backend") and listed in the
  ledger below, with what is missing and its target date.
- A fix that makes an SBOM dishonest (a value that is not true) is not a
  completeness gap: it is fixed in any tier. The model-inputs fix of
  2026-10-17 touched PT2 for that reason.
- New formats start in tier 2.

## Demo scope

| Axis | In scope |
|---|---|
| Minimum elements standard | A few clusters of G7 SBOM for AI: Metadata, System, Model, Dataset |
| SBOM format | SPDX 3.0 (3.0.1) |
| AI model sources | Tier 1: Safetensors, ONNX, GGUF, NumPy, fastText and the Hugging Face Hub |
| Python build backends | Hatchling, setuptools, Poetry |

Out of scope for the demo: the Infrastructure, Security and KPI clusters; other
SBOM formats; tier 2 formats beyond keeping them working. CISA 2026 and FSCT
2024 are checked by the same tests and reported on the user page; NTIA and
BSI are not.

## Parity principle

Decided 2026-10-18 (user): surface parity holds from the start. The CLI, the
library, the Hatchling hook, the GitHub Action and the skills give the same
result for the same input; a difference is a bug, not a ledger entry. Tiers
apply only to AI model file formats and Python build backends.

Test: `tests/conformance/test_g7ai_surfaces.py` runs each input through every
surface that can take it (library, `loom model`, `loom generate`, `loom
project`, `loom wheel`, the hook) and compares the checker's outcome for every
G7, CISA 2026 and FSCT 2024 rule, the elements and property names, and the
names, versions, package URLs and hash values. One allowed difference: the
hook adds `builtTime` (it runs during a build). The Action and the skills run
the same `loom` commands and are not tested separately.

Format and backend ledger (a gap, where it is, what it needs, target). Target date for every gap
(user decision 2026-10-18): 2026-10-19. A gap not closed by then stays listed with the date missed.

| Gap | Surfaces or formats | Needs | Target |
|---|---|---|---|
| Hub model has no file hash (MDL-007/008) | Hugging Face source | A per-file hash request or a Merkle root over file hashes | 2026-10-19 |
| Dataset licence, provenance and statistics reach no model SBOM | all (no reader feeds Croissant in) | A reader route, then the `loom` SDK (B7) | 2026-10-19 |
| `INFO:` notices for information read but not recordable | all readers | The shared helper in the honesty doc | 2026-10-19 |
| Model files carry no version, producer or time | tier 1 file formats | Nothing to read: stays `missing` | n/a |
| G7 scenarios: model files, a Hub model, a library-built model and a project per backend | done 2026-10-18 | Hatchling, setuptools and Poetry give the same G7 outcomes | done |
| A setuptools project ships a model only when `package-data` lists it | setuptools | Nothing: the SBOM describes what would ship | n/a |
| Tier 2 formats | Keras, HDF5, PyTorch, PT2, CRFsuite | Anything beyond keeping them working | 2026-10-19 |

## Demo on 2026-10-19: decisions of 2026-10-18

- Hugging Face and NumPy are tier 1 and in the conformance table (scenarios
  `hub` and `numpy`).
- Only an SBOM whose one root is a single AI model is judged by that model
  for the System-level (SLP) properties; the checker names the model it
  judged (`systemJudgedByModel`). A project that ships a model has a root of
  its own and is judged by its own package (first decided for such projects
  too, then narrowed the same day).
- The ledger above says, per gap, what is missing and when it will be fixed;
  the date for each is 2026-10-19.

## Demo: definition of done

Each item is done (2026-10-18):

1. Table scenarios for the tier 1 sources and a project per backend, each
   with expected cells and the honesty guards (`tests/conformance/`).
2. A coverage report for those scenarios, with the previous iteration's
   figures ([g7-conformance-tests.md](../implementation/g7-conformance-tests.md)).
3. The tier and parity ledger published in the user docs, in the user's words
   (`docs/g7-sbom-for-ai.md`, no link into `working-docs/`).
4. Known honest gaps listed on that page: what Pitloom leaves out and why.

The open questions (NumPy and the Hugging Face Hub in the demo; parity
targets) were settled by the decisions of 2026-10-18 above.
