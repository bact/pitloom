---
Created: 2026-11-16
Last-Modified: 2026-11-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Examples: asserter `originator`

See also: [README.md](README.md) (sources of the inputs, how to read a
row, the matrix), [../asserter.md](../asserter.md),
[../basis.md](../basis.md).

The originator is the party that made the element. Every input found is a
statement, so the basis is `declared` (the default).

## originator, declared

| # | Element | Input | Field | Today |
| --- | --- | --- | --- | --- |
| OD-1 | `pkg:pypi/astropy@8.0.2` | `pyproject.toml`: `project.license = "BSD-3-Clause"` | licence | yes |
| OD-2 | same | PyPI JSON API: `info.license_expression: "BSD-3-Clause"` | licence | yes |
| OD-3 | same | sdist `PKG-INFO`: `License-Expression: BSD-3-Clause` | licence | yes |
| OD-4 | `pkg:pypi/ipython@9.18.1` | `pyproject.toml` states no `project.version` (dynamic); `PKG-INFO`: `Version: 9.18.1` | version | yes |
| OD-5 | `pkg:huggingface/AIMH/mental-bert-large-cased@2d8e57e` | card front matter: `license: cc-by-nc-sa-4.0` | licence | yes |
| OD-6 | `agentionai/Qwen3.8-27B-AP-GGUF`, file `Qwen3.8-27B-AP-IQ2_S.gguf` | header: `general.name = "Qwen3.8-27B"` | model name | yes |
| OD-7 | `BAAI/bge-m3`, file `onnx/model.onnx` | header: `producer_name: pytorch`, `producer_version: 2.1.2` | framework, its version | yes |
| OD-8 | `pkg:pypi/silero-vad@5.1.2`, file `silero_vad.onnx` | header: `graph.name = "spox_graph"` | model name | yes |
| OD-9 | `pkg:pypi/aiotask-context@0.6.1` | `PKG-INFO`: `License: UNKNOWN`; PyPI JSON API: `info.license: ""` | licence | yes |
| OD-10 | the SBOM-MinBench project | `uv.lock`: package `licenseid`, `version = "0.8.4"` | version of a dependency | yes |
| OD-11 | `deepset/roberta-base-squad2` | card `model-index`: `exact_match` 85.289 on `squad`, not verified (self-reported) | evaluation result | to check |

```text
OD-1   Source: pyproject.toml | Kind: manifest | Location: project.license | Asserter: originator | Basis: declared
OD-2   Source: PyPI JSON API | Kind: registry | Location: info.license_expression | Asserter: originator | Basis: declared
OD-3   Source: PKG-INFO | Kind: core-metadata | Container: astropy-8.0.2.tar.gz | Location: License-Expression | Asserter: originator | Basis: declared
OD-4   Source: PKG-INFO | Kind: core-metadata | Container: ipython-9.18.1.tar.gz | Location: Version | Asserter: originator | Basis: declared
OD-5   Source: Hugging Face Hub API | Kind: registry | Location: cardData.license | Asserter: originator | Basis: declared
OD-6   Source: Qwen3.8-27B-AP-IQ2_S.gguf | Kind: artifact-content | Location: general.name | Asserter: originator | Basis: declared
OD-7   Source: model.onnx | Kind: artifact-content | Location: producer_name | Asserter: originator | Basis: declared
OD-8   Source: silero_vad.onnx | Kind: artifact-content | Location: graph.name | Asserter: originator | Basis: declared
OD-9   Source: PKG-INFO | Kind: core-metadata | Container: aiotask_context-0.6.1.tar.gz | Location: License | Asserter: originator | Basis: declared
OD-10  Source: uv.lock | Kind: lock-file | Package: licenseid | Asserter: originator | Basis: declared
OD-11  Source: Hugging Face Hub API | Kind: registry | Location: cardData.model-index | Asserter: originator | Basis: declared
```

Notes:

- **OD-1 to OD-3** are one statement met at three sources. The source
  changes (manifest, registry, Core Metadata); the asserter does not: the
  registry relays what the uploader wrote.
- **OD-4**: the build backend wrote the version into `PKG-INFO`. From
  where Pitloom stands it is a statement of the project.
- **OD-5**: recorded as `CC-BY-NC-SA-4.0`. Only the case differs, a
  `form` step ([../change.md](../change.md)), so no `Written` is kept.
- **OD-6 to OD-8**: a value in a model file's header was put there by the
  tool the originator ran. `spox_graph` is a poor name and still the
  stated one; compare the name made from a file name in
  [sbom-tool.md](sbom-tool.md#sbom-tool-inferred) (SI-2), the sibling file
  that states none.
- **OD-9** is a claim with a `placeholder` value
  ([../value-strength.md](../value-strength.md)); the registry's empty
  string is `absent`, no claim.
- **OD-10**: the pin is the depending project's statement about its
  dependency. The hash the same lock entry records is another matter:
  [other-party.md](other-party.md#other-party-declared) (PD-2).
- **OD-11**: a self-reported result. The same card holds results the
  Hub generated itself, which are `other-party`, `detected`
  ([other-party.md](other-party.md#other-party-detected), PT-9).

## Two originator statements that differ

Both are `originator`, `declared`. By the ruling of 2026-11-16 both are
declared licences and the record says they conflict (the licence points parked then are ruled since: [../asserter-licence.md](../asserter-licence.md)).

| # | Element | Input one | Input two |
| --- | --- | --- | --- |
| OC-1 | `pkg:pypi/crc32c@2.9.post0` | `PKG-INFO`: `License: LGPL-2.1-or-later` | `PKG-INFO`: classifier `GNU Lesser General Public License v2 or later (LGPLv2+)`, which the benchmark's classifier table reads as `LGPL-2.0-or-later` |
| OC-2 | the SBOM-MinBench project | `pyproject.toml`: `license = "Apache-2.0"` | `CITATION.cff`: `license: CC-BY-4.0`; licence files `LICENSE` (CC BY 4.0 text), `LICENSE-CODE`, `LICENSE-DATA-SEEDS` (CC BY-SA 4.0 text) |

OC-2 is the case of the ruling on file names: the files name their scope
(code, data seeds), the manifest states the code's licence, the citation
file the data's. Nothing here is wrong; one licence per project is the
wrong question.

## A licence file matched to an id

These examples were written while the point was parked. Ruled since
([../asserter-licence.md](../asserter-licence.md)): the gate ("The gate for a text
match", 2026-11-19 and 2026-11-20) and the form ("The form of a text
match", 2026-11-21: form A). The examples stay as written. The
file is the originator's declaration (ruled); the id comes from a match
Pitloom ran. "Matched id", "Score" and "Coverage" are what LicenseID
0.8.4 returned in the benchmark's probe, not re-run here and not taken
as true. "The file holds" is from reading the file, 2026-11-16.

| # | Element | File | Matched id | Score | Coverage | The file holds | Match |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OL-1 | `pkg:pypi/flask@3.0.3` | `LICENSE.txt` | `BSD-3-Clause` | 1.0 | 0.9954 | the three-clause BSD text (repository tag `3.0.3`) | right |
| OL-2 | `pkg:pypi/python-dateutil@2.9.0.post0` | `LICENSE` | `Apache-2.0` | 0.9187 | 0.2639 | a short Apache 2.0 notice for later contributions, then the full BSD three-clause text, which the file says applies to all code (repository tag `2.9.0.post0`) | partly: names the licence present as a notice, misses the one present in full |
| OL-3 | `pkg:pypi/dbldatagen@0.4.0.post1` | `LICENSE` | `OpenMDW-1.0` | 0.641 | 1.297 | "Databricks License", the vendor's own text (repository default branch; the release's own file not read) | wrong |
| OL-4 | `pkg:pypi/amrita-core@1.4.0` | `LICENSE`; no `License`, no `License-Expression`, no classifier | not run in the benchmark | - | - | not read | - |
| OL-5 | `pkg:huggingface/black-forest-labs/FLUX.2-klein-4B@e7b7dc2` | `LICENSE.md`; the card states `apache-2.0` | `Pixar` | 0.9947 | 1.0078 | the Apache License 2.0 text, with the standard section 6 and no Pixar change (pinned revision) | wrong |

The two forms that were under discussion, on OL-3 (form A is ruled; by
the gate OL-3 as written names no id):

```text
A  Source: LICENSE | Kind: package-file | Asserter: originator | Method: matched | Technique: license-text | Tool: licenseid==0.8.4 | Basis: declared
B  Source: LICENSE | Kind: package-file | Asserter: originator | Written: <the text, by its hash> | Change: <a fifth step kind, not named yet> | Tool: licenseid==0.8.4 | Basis: declared
```

Form A is the `matched` exception; form B is a change step, for which
[../change.md](../change.md) has no kind yet (text to id is none of the
four).

- **OL-1**: both forms read well; the match is right.
- **OL-2**: the match is half right, at a score of 0.9187. The low
  coverage (0.2639) is the only sign.
- **OL-3**: form A says the originator declared `OpenMDW-1.0`. It did
  not: it declared its own licence text, which LicenseID places nearest
  to that id, at 0.641.
- **OL-4**: the licence file is the only statement the project makes. By
  the ruling its match is the declared licence; without it the SBOM has
  none.
- **OL-5**: the card and the file agree (Apache 2.0); the match does
  not, at 0.9947. Form A would write `Pixar` as a declared licence of
  the originator and, by the "all declared, record the conflict"
  ruling, a conflict with the card that does not exist. A second Hub
  input in the probe shows the same id and the same score for a
  `LICENSE` beside a card that states `apache-2.0` (not read here).
  Re-run on 2026-11-19 with LicenseID 0.9.0, on the file at `main` (not
  the pinned revision): the same order, `Pixar` at 0.9947, then
  `Apache-2.0` at 0.9937. The file ends at "END OF TERMS AND
  CONDITIONS", without the appendix.
- **Q**: a score cannot be the gate: OL-5 is wrong at 0.9947 and OL-2
  half right at 0.9187. What makes a match a declared licence: an
  exact match only, or a match kept as `sbom-tool`, `detected`, beside
  the originator's declared text?

## originator, detected and inferred

Both cells are closed (ruled 2026-11-23; [../basis.md](../basis.md),
rule 4): an originator's claim is `declared`. Pitloom would have to
know that the originator got the value by a procedure (`detected`) or
from a proxy (`inferred`); a source seldom says so. The inputs that
were looked at: one candidate for `detected` (OX-4), none for
`inferred`, then three near inputs.

| # | Element | Input | Why it was a candidate for `detected` |
| --- | --- | --- | --- |
| OX-4 | `eddiegulay/wav2vec2-large-xlsr-mvc-swahili` | card `model-index`: `wer` 0.2 on `common_voice_13_0`, not verified; the repository carries the tag `generated_from_trainer` (10 of 711 cached repositories do) | the tag says the training tool wrote the card, so the result is that tool's own evaluation run for the originator |

```text
OX-4  Source: Hugging Face Hub API | Kind: registry | Location: cardData.model-index | Asserter: originator | Basis: declared
```

A tag is not enough to know the procedure: a person can keep the tag
and edit the number. So OX-4 is `declared`, like OD-11.

Near inputs:

| # | Input | Why not `detected` |
| --- | --- | --- |
| OX-1 | a wheel's `RECORD` hashes, written by the build backend | ruled 2026-11-16: stays `declared`; Pitloom cannot see how it was made |
| OX-2 | `pkg:cargo/actix-web@4.19.0`: `.cargo_vcs_info.json` holds the commit `fdb6503d...`, written by the publishing tool | the nearest to "known": the format says a tool recorded it. Not a Python source, not read by Pitloom |
| OX-3 | `QuantFactory/Qwen2.5-7B-HomerCreative-Mix-GGUF`: card `model-index` result 78.35 on IFEval with `source: Open LLM Leaderboard`, not verified | the originator relays another party's measurement; in the card it is the originator's statement. A registry that relays the originator keeps `originator` (OD-2); a card that quotes a leaderboard does not become `other-party` (ruled 2026-11-23; [../asserter.md](../asserter.md), rule 2): a person may misquote where a registry does not |

A cell opens again when a source that states its own procedure is
read. Outside Python the benchmark has
such sources: it records a commit as written by the publisher's tool
(`.cargo_vcs_info.json`, npm `gitHead`, a NuGet `repository` commit).

## Closed cells

`measured`, `lower-bound` and `not-measured` are Pitloom's only. The
nearest originator input is a stated hash: the Git LFS pointer of the
README worked example (`Kind: pointer`, `Location: oid`), which is
`declared`.
