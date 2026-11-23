---
Created: 2026-11-16
Last-Modified: 2026-11-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Examples: asserter `other-party`

See also: [README.md](README.md) (sources of the inputs, how to read a
row, the matrix), [../asserter.md](../asserter.md) (the field table),
[../basis.md](../basis.md).

A party that is neither the element's maker nor the SBOM's maker said or
found the value: a registry, a hosting service, another project's file.

## other-party, declared

The party said so; no procedure of its own is known. The default.

| # | Element | Input | Field | Today |
| --- | --- | --- | --- | --- |
| PD-1 | `AdamCodd/vit-base-nsfw-detector` | Hub API: `author: "AdamCodd"` (the repository's owner) | supplier | yes |
| PD-2 | `licenseid` 0.8.4, as a dependency of the SBOM-MinBench project | that project's `uv.lock`: `sdist = { ..., hash = "sha256:15447cb2...9d58d7bc" }` | hash of the dependency's sdist | yes |
| PD-3 | `meta-llama/Llama-3.2-1B` | Hub API: `gated: "manual"` (41 of 711 cached model repositories are gated) | access condition | no |
| PD-4 | a base model, described from a quantiser's repository (`mradermacher/Gemma-2-Llama-Swallow-9b-it-v0.1-i1-GGUF`) | that repository's card: `license: [gemma, llama3.3]` | licence of the base model | no |
| PD-5 | `pkg:pypi/derailment@0.9.0` | PyPI JSON API: `yanked: true`, and a `yanked_reason` in the maintainer's words (the release's numbers are invalid; use 0.10.0 or later) | release status | yes |

```text
PD-1  Source: Hugging Face Hub API | Kind: registry | Location: author | Asserter: other-party | Basis: declared
PD-2  Source: uv.lock | Kind: lock-file | Package: licenseid | Location: sdist.hash | Asserter: other-party | Basis: declared
PD-3  Source: Hugging Face Hub API | Kind: registry | Location: gated | Asserter: other-party | Basis: declared
PD-4  Source: README.md | Kind: card | Container: mradermacher/Gemma-2-Llama-Swallow-9b-it-v0.1-i1-GGUF | Location: license | Asserter: other-party | Basis: declared
PD-5  Source: PyPI JSON API | Kind: registry | Location: yanked | Asserter: other-party | Basis: declared
```

Notes:

- **PD-1**: the Hub assigned the namespace. The owner chose the name;
  is the owner field the originator's statement relayed, as the
  card's fields are? Decided 2026-11-23: no, it stays `other-party`,
  `declared`, the registry's record
  ([../alignment.md](../alignment.md), "Acting on behalf of").
- **PD-2**: ruled 2026-11-16, `declared`. The lock tool copied the hash
  from the index; the lock file's project did not make that artefact. The
  pin beside it is the project's own statement (OD-10).
- **PD-3**: the repository's owner switches the gate on; the Hub
  enforces and reports it. The same question as PD-1 and PD-5, with
  the same answer.
- **PD-4**: the asserter is relative to the element. For the quantised
  repository itself the same line is `originator`, `declared`. It becomes
  `other-party` only when it is used to describe the base model, and by the
  licence table it then yields no relationship.
- **PD-5**: one real yank among 564 PyPI responses. The reason is the
  maintainer's own text, relayed; the flag is the registry's record of the
  maintainer's act. `yanked_reason` reads as `originator`; the field
  table gives the flag `other-party`. Decided 2026-11-23: both stay
  `other-party`, `declared`; the reason is a weak spot kept in view
  ([../alignment.md](../alignment.md), "Acting on behalf of").

### Looks like other-party, is the originator

| # | Element | Input | Why `originator` |
| --- | --- | --- | --- |
| PX-1 | `black-forest-labs/FLUX.2-klein-4B` | Hub API `tags`: `license:apache-2.0` | the Hub computes the tag from the card's `license: apache-2.0`; a relay, like OD-2 |

## other-party, detected

The party got the value by its own procedure on the thing itself, exact
or not (ruled 2026-11-16). Pitloom did not run that procedure. `Basis`
is written.

| # | Element | Input | Field | Today |
| --- | --- | --- | --- | --- |
| PT-1 | `pkg:pypi/aiofiles@25.1.0`, `aiofiles-25.1.0.tar.gz` | PyPI JSON API: `digests.sha256: a8d728f0...4d23d5b2` | hash | yes |
| PT-2 | `pkg:pypi/pyspark@4.3.0`, `pyspark-4.3.0.tar.gz` | PyPI JSON API: `digests.sha256: e8c51794...622476c6`, `size: 455910862`; the file is over a download cap and is not fetched | hash, size | yes |
| PT-3 | `pkg:huggingface/AIMH/mental-bert-large-cased` | Hub API: `sha: 2d8e57e2c258...` (the revision) | version of the repository | yes |
| PT-4 | `pkg:pypi/aiobotocore@3.10.0` | PyPI attestation, verified: built from `https://github.com/aio-libs/aiobotocore`, `refs/tags/3.10.0`, commit `65f5b5a7...` | source repository and commit | no |
| PT-5 | `microsoft/Phi-3.5-mini-instruct` | Hub API `tags`: `arxiv:2404.14219`, `arxiv:2407.13833`, extracted by the Hub from links in the card (346 of 711 cached repositories carry such a tag) | cited paper | yes |
| PT-6 | `albert/albert-base-v2` | Hub API: `safetensors.total: 11842272` | parameter count | yes |
| PT-7 | an installed environment (no stored input) | `pipdeptree`: the versions installed, the dependency tree | dependency version | yes |
| PT-8 | `EleutherAI/pythia-160m` | Hub API: `safetensors.total: 212654688` (`F16`: 162,323,040; `U8`: 50,331,648) | parameter count | yes |
| PT-9 | `deepset/roberta-base-squad2` | Hub API, card `model-index`: `exact_match` 79.9309 on `squad_v2`, `verified: true` | evaluation result | to check |

```text
PT-1  Source: PyPI JSON API | Kind: registry | Location: urls.digests.sha256 | Asserter: other-party | Basis: detected
PT-2  Source: PyPI JSON API | Kind: registry | Location: urls.digests.sha256 | Asserter: other-party | Basis: detected
PT-3  Source: Hugging Face Hub API | Kind: registry | Location: sha | Asserter: other-party | Basis: detected
PT-4  Source: PyPI attestation | Kind: registry | Location: <statement of the attestation> | Asserter: other-party | Basis: detected
PT-5  Source: Hugging Face Hub API | Kind: registry | Location: tags | Asserter: other-party | Basis: detected
PT-6  Source: Hugging Face Hub API | Kind: registry | Location: safetensors.total | Asserter: other-party | Basis: detected
PT-7  Source: pipdeptree | Kind: environment | Asserter: sbom-tool | Method: derived | Tool: pipdeptree | Basis: measured
PT-8  Source: Hugging Face Hub API | Kind: registry | Location: safetensors.total | Asserter: other-party | Basis: detected
PT-9  Source: Hugging Face Hub API | Kind: registry | Location: cardData.model-index | Asserter: other-party | Basis: detected
```

Notes:

- **PT-1** and SM-1 hold the same value: PyPI's figure and Pitloom's own.
  Pitloom's `measured` stands; they agree, so nothing more is recorded.
- **PT-2** is the case the widening was ruled for: the only hash of the
  file is PyPI's. It is not `measured` (Pitloom read nothing) and it is
  more than a bare statement (PyPI computed it from the upload). The
  outcome of this source was called `declared-only`; with the value
  now `detected` the word misled, and it is dropped since 2026-11-23:
  the outcome is `used`
  ([../basis.md](../basis.md#outcome-of-a-source)).
- **PT-4**: the builder observed what it built from, and the index checks
  the signature. Not read by Pitloom today; a candidate source for the
  source repository of a dependency.
- **PT-5**: the paper link is the originator's; the id in the tag is the
  Hub's extraction. Pitloom reads the tag.
- **PT-6, PT-8**: the Hub's total against Pitloom's own sum over the same
  file, for the 128 repositories of the model header probe that hold one
  safetensors file: 113 equal (PT-6 is one), 15 differ. For PT-8 Pitloom's
  sum is 212,654,700, twelve more than the Hub's. The cause was not
  looked into. A parameter count is not a hash: which tensors
  count is a rule, and two correct tools with two rules differ. By
  precedence Pitloom's `measured` value stands and the difference is a
  conflict with rule `basis-order`. Ruled 2026-11-23 that this
  holds, where both values are about one element
  ([../basis.md](../basis.md#precedence-for-content-facts)).
- **PT-7** (decided 2026-11-23): Pitloom starts `pipdeptree`
  itself. By asserter rule 3, and by the SSN reading in which Pitloom is
  the platform and `pipdeptree` a sensor it hosts, this is
  `Asserter: sbom-tool`, `Tool: pipdeptree`, with basis `measured`. So
  the example is no `other-party` claim any more; it stays on this
  page, where it was written, and counts in the `sbom-tool`,
  `measured` cell of the matrix. No technique is registered for it
  yet.
- **PT-9**: the Hub's model card specification says a verified result
  carries a signature that proves the "evaluation was generated by Hugging
  Face (vs. self-reported)". The same card holds self-reported results
  (OD-11): one field, two asserters, told apart by `verified`. Verified
  metrics are rare in the cached responses: tens, against thousands of
  self-reported ones.

## other-party, inferred

The party concluded the value from a proxy. What the Hub does is from its
documentation ("Model Cards", read 2026-11-16); the inputs are cached API
responses in which the API holds a value and the card's front matter does
not state it.

| # | Element | Input | What the Hub does when the card is silent | Today |
| --- | --- | --- | --- | --- |
| PI-1 | `deepset/roberta-base-squad2` | Hub API: `library_name: transformers`; the card states none (232 such repositories; 397 where the card states it) | detects the library from the files present | no: Pitloom reads the card's value only |
| PI-2 | same | Hub API: `pipeline_tag: question-answering`; the card states none (195 such; 328 where the card states it) | for `transformers` models, infers the task from `config.json` | no: Pitloom reads the card's value only |
| PI-3 | `unsloth/Llama-3.1-Nemotron-Nano-8B-v1` | Hub API `tags`: `base_model:finetune:nvidia/Llama-3.1-Nemotron-Nano-8B-v1`; the card sets no `base_model_relation` (266 such; 19 where the card sets it) | infers the relation to the base model | yes: read from the tag |

```text
PI-1  Source: Hugging Face Hub API | Kind: registry | Location: library_name | Asserter: other-party | Basis: inferred
PI-2  Source: Hugging Face Hub API | Kind: registry | Location: pipeline_tag | Asserter: other-party | Basis: inferred
PI-3  Source: Hugging Face Hub API | Kind: registry | Location: tags | Asserter: other-party | Basis: inferred
```

Notes:

- **PI-1, PI-2**: the same field is `originator`, `declared` when the card
  states it. To tell the two apart Pitloom compares the API's value with
  the card's front matter: stated there, the originator's; absent there,
  the Hub's inference. Some four in ten responses are the Hub's.
- **PI-3**: Pitloom records the relation today with no sign that the Hub
  inferred it, which it did in 266 of 285 cached cases. Only the
  relation is in question here; whether the card names the base model
  was not checked for this input.

## Closed cell

`other-party` never has `measured`: the nearest input is PT-1, a correct
and exact digest, which is `detected` because the procedure was not
Pitloom's.
