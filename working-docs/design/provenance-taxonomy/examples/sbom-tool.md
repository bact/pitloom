---
Created: 2026-11-16
Last-Modified: 2026-11-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Examples: asserter `sbom-tool`

See also: [README.md](README.md) (sources of the inputs, how to read a
row, the matrix), [../basis.md](../basis.md),
[../method.md](../method.md).

Pitloom worked the value out. The method class gives the default basis
(`derived` gives `measured`, `matched` gives `detected`, `synthesized`
gives `inferred`), and `Basis` is written with it.

## sbom-tool, measured

One right answer; any correct tool gives the same.

| # | Element | Input | Value | Today |
| --- | --- | --- | --- | --- |
| SM-1 | `pkg:pypi/aiofiles@25.1.0`, `aiofiles-25.1.0.tar.gz` | the file's bytes | SHA-256 `a8d728f0...4d23d5b2` | yes |
| SM-2 | same | the file system's size of the file | 46,354 bytes | yes |
| SM-3 | `AdamCodd/vit-base-nsfw-detector`, `model.safetensors` | the header's tensor shapes; 23,192 bytes read of a file of 344,391,328 | 86,092,034 parameters | yes |
| SM-4 | `pkg:pypi/magika@0.6.1`, `models/standard_v3_2/model.onnx` | `graph.initializer`, `graph.sparse_initializer` | 784,519 parameters | yes |
| SM-5 | `agentionai/Qwen3.8-27B-AP-GGUF`, `Qwen3.8-27B-AP-IQ2_S.gguf` | `tensor_infos`; 16,777,216 bytes read of a file of 9,607,980,896 | 27,320,697,856 parameters | yes |

```text
SM-1  Source: aiofiles-25.1.0.tar.gz | Kind: artifact-content | Asserter: sbom-tool | Method: derived | Technique: content-hash | Basis: measured
SM-2  Source: aiofiles-25.1.0.tar.gz | Kind: artifact-content | Asserter: sbom-tool | Method: derived | Technique: file-stat | Basis: measured
SM-3  Source: model.safetensors | Kind: artifact-content | Location: tensor shapes | Asserter: sbom-tool | Method: derived | Technique: tensor-element-sum | Basis: measured
SM-4  Source: model.onnx | Kind: artifact-content | Location: graph.initializer, graph.sparse_initializer | Asserter: sbom-tool | Method: derived | Technique: tensor-element-sum | Basis: measured
SM-5  Source: Qwen3.8-27B-AP-IQ2_S.gguf | Kind: artifact-content | Location: tensor_infos | Asserter: sbom-tool | Method: derived | Technique: tensor-element-sum | Basis: measured
```

Notes:

- **SM-1** equals the digest PyPI states for the file
  ([other-party.md](other-party.md#other-party-detected), PT-1). Two
  claims, one value: agreement, recorded once.
- **SM-3**: checked against another party. For 128 repositories of the
  probe that hold one safetensors file, the Hub's own total
  (`safetensors.total`) equals Pitloom's sum in 113 and differs in 15
  ([other-party.md](other-party.md#other-party-detected), PT-6, PT-8).
  The test of `measured` was "one right answer; any correct tool
  gives the same". The sum over the tensors of the file passes it;
  "parameter count" needs a rule for which tensors count, and does not.
  Ruled 2026-11-23: the count stays `measured`, for the quantity
  the technique names, and the technique states its rule
  ([../basis.md](../basis.md#precedence-for-content-facts)).
- **SM-3, SM-5**: the count is exact although a small part of the file was
  read: the tensor table carries every shape. The definition of
  `measured` said "read in full"; since 2026-11-23 it says that the
  part that carries the fact was read in full
  ([../basis.md](../basis.md#values)).

## sbom-tool, detected

The best match in a reference set; the result depends on the tool and its
data.

| # | Element | Input | Value | Today |
| --- | --- | --- | --- | --- |
| ST-1 | `pkg:huggingface/Comfy-Org/MiniMax-H3@5447222` | the card's `license_link` is a `LICENSE` in another repository (`MiniMaxAI/MiniMax-H3`); its text, matched | `APSL-1.0`, score 0.6754 | no: the link is recorded, its text is not fetched |
| ST-2 | a model file (constructed) | the file's bytes, by a content matcher | a media type | yes |

```text
ST-1  Source: LICENSE | Kind: linked-document | Container: MiniMaxAI/MiniMax-H3 | Asserter: sbom-tool | Method: matched | Technique: license-text | Tool: licenseid==0.8.4 | Basis: detected
ST-2  Source: <file> | Kind: artifact-content | Asserter: sbom-tool | Method: matched | Technique: content-type | Tool: magika==<version> | Basis: detected
```

Notes:

- **ST-1**: the text is not a licence file of the element, of its project
  tree or of its hosting repository, so the `matched` exception of
  [../asserter.md](../asserter.md) does not reach it and the match is
  Pitloom's own claim. The file was read (2026-11-16, at `main`, not the
  pinned revision): it is the "MiniMax H3 Community License Agreement",
  a licence of its own, so the best match is a wrong id. The matched id
  and score are LicenseID 0.8.4 output from the benchmark's probe.
  The card's `license_link` is the
  originator pointing at that text; its match is not the originator's
  declared licence for that (ruled 2026-11-23;
  [../asserter-licence.md](../asserter-licence.md), the
  `sbom-tool` row), unlike a file in the repository
  ([originator.md](originator.md#a-licence-file-matched-to-an-id)).
- **ST-1** had no source kind: `repository` is "a file of the hosting
  repository", and this file is in another one. Since 2026-11-23
  its kind is `linked-document`
  ([../source.md](../source.md), rule 9).
- A licence file of the element itself is not in this cell by the ruling
  of 2026-11-16; that leaves few real `sbom-tool`, `detected` inputs
  besides the content type.

## sbom-tool, inferred

Concluded from a proxy: the thing examined stands for the property and is
not it.

| # | Element | Input | Value | Today |
| --- | --- | --- | --- | --- |
| SI-1 | `pkg:pypi/magika@0.6.1`, `models/standard_v3_2/model.onnx` | the header states no graph name; the file name | model name `model` | yes |
| SI-2 | `pkg:pypi/silero-vad@5.1.2`, `silero_vad_half.onnx` | the header states no graph name; the file name | model name `silero_vad_half` | yes |
| SI-3 | a file whose content was not matched (constructed) | the file name's extension | a media type | yes |

```text
SI-1  Source: model.onnx | Kind: artifact-name | Asserter: sbom-tool | Method: synthesized | Technique: file-name-stem | Basis: inferred
SI-2  Source: silero_vad_half.onnx | Kind: artifact-name | Asserter: sbom-tool | Method: synthesized | Technique: file-name-stem | Basis: inferred
SI-3  Source: <file> | Kind: artifact-name | Asserter: sbom-tool | Method: synthesized | Technique: file-extension | Basis: inferred
```

Notes:

- **SI-1** shows what a proxy costs: `model` names nothing. The package
  name (`magika`) would name it better, and is another proxy.
- **SI-2** against OD-8: in one package, `silero_vad.onnx` states a name
  (`spox_graph`, `originator`, `declared`) and `silero_vad_half.onnx`
  states none (`sbom-tool`, `inferred`). A fragment's value replaces the
  second by rule `synthesized-yields`, not the first.

## sbom-tool, lower-bound

No real input, and no writer today.

| # | Element | Input | Today |
| --- | --- | --- | --- |
| SL-1 | `audio-cpp/audio.cpp-gguf`, `ace-step-1.5-base-bf16.gguf` | the header read stopped at 67,108,864 bytes of a file of 10,090,405,184 | error `ModelOverCap`, no fields |

**Q**: SL-1 is not a lower bound of anything: the tensor table was not
read to its end, so no count is known, and the right record is
`not-measured` with `over-cap`. A lower bound needs a fact whose partial
reading is a floor (bytes of an archive member that keeps expanding,
entries of a directory walk that stopped). None was found in the inputs.

## sbom-tool, not-measured

No value: not safe or not possible to read, and no party states it.

| # | Element | Input | Fact not measured | Today |
| --- | --- | --- | --- | --- |
| SN-1 | `AdamCodd/vit-base-nsfw-detector`, `onnx/model.onnx` | 344,569,044 bytes, over the read cap | parameter count | `over-cap` is written for a file hash; for a count, to check |
| SN-2 | `black-forest-labs/FLUX.1-dev`, `ae.safetensors` | gated repository; the fetch is refused, HTTP 401 | parameter count, hash | no: `download-network-failed` has no writer |

```text
SN-1  Source: model.onnx | Kind: artifact-content | Asserter: sbom-tool | Method: derived | Technique: tensor-element-sum | Basis: not-measured | Reason: over-cap
SN-2  Source: ae.safetensors | Kind: artifact-content | Asserter: sbom-tool | Method: derived | Technique: tensor-element-sum | Basis: not-measured | Reason: download-network-failed
```

Notes:

- **SN-1** is the same repository as SM-3: one file measured, its sibling
  not. The claim is per file.
- **SN-2**: `download-network-failed` says "the fetch was refused or
  broke". A gate is neither a fault nor a cap; a reader of the SBOM
  can act on it (ask for access). A code of its own (`access-denied`)
  would say so; ruled 2026-11-23 that the one code stays, as the
  message catalogue has it
  ([../basis.md](../basis.md#reason-codes)).
- **Not in this cell**: the sdist of `pkg:pypi/pyspark@4.3.0`
  (455,910,862 bytes) is over a download cap, so Pitloom computes no hash;
  but PyPI states one, so the claim is PyPI's
  ([other-party.md](other-party.md#other-party-detected), PT-2), not a
  `not-measured`.

## Closed cell

`sbom-tool` never has `declared`: Pitloom states nothing of its own. The
nearest input is any value Pitloom copies out of a manifest (OD-1): the
asserter stays `originator` ([../asserter.md](../asserter.md), rule 5).
