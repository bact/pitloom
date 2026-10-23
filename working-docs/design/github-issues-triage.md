---
Created: 2026-10-23
Last-Modified: 2026-10-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Open GitHub issues: triage

See also: [roadmap.md](roadmap.md#open-github-issues),
[external-references-to-review.md](external-references-to-review.md) (the
research notes).

The 26 open issues of `bact/pitloom`, checked on 2026-10-23 against the code
on `release-prep` (main merged at `dbbd7113`), the CHANGELOGs and the
roadmap. *Closable*: what the issue asks is built; the owner closes it.
*Open*: something remains, named here, with the roadmap item that holds it.
*Research*: a note to read, not work. Rerun this triage before acting on an
old row.

| Issue | Verdict | Evidence, or what remains | Roadmap item |
| :-- | :-- | :-- | :-- |
| [#30] PURL as `spdxId` | Open, needs decision | Ids are UUIDv5 or registry ids; a PURL is only `software_packageUrl` | To design: Package-URL as `spdxId` |
| [#41] Reuse an existing SBOM | Open | An earlier SBOM merges as a configured fragment (a same-document one is skipped); no auto-detection at the root, no reuse of its creation info; another version still gives two root packages | To design: Fragments |
| [#46] orjson | Research | `rfc8785` package used today | [External work](external-references-to-review.md#orjson) |
| [#48] SBOM-QA benchmark | Research | - | [External work](external-references-to-review.md#sbom-qa-nokia) |
| [#51] Serialiser as a library | Open, needs decision | Serialisation lives in `pitloom.export.spdx3_json` and `pitloom.core.canonical_json`, not a separate package | Needs systematic rules: Canonical output |
| [#52] Mappings outside code | Open | The intermediate `DocumentModel` is built; mappings are Python code, not data | To design: Format-neutral representation |
| [#53] Signposting | Research | - | [External work](external-references-to-review.md#signposting) |
| [#55] ETSI EN 304 223 | Research | - | [External work](external-references-to-review.md#etsi-en-304-223-cyber-security-requirements-for-ai) |
| [#61] scikit-build-core | Open | `--allow-build` (#215, #216) builds any PEP 517 backend; without it a heuristic and a `WARNING:` (`docs/cli.md`); never tried on a real scikit-build-core project | Open follow-ups: File discovery |
| [#62] Test with Mistral 7B | Closable | Poetry (#67, 0.6.0), a model file (#69, 0.6.1), the Hub with `config.json`, `tokenizer_config.json`, `generation_config.json` (#71, 0.7.0); `tests/extract/remote/test_huggingface_metadata.py` reads `mistralai/Mistral-7B-v0.1` | - |
| [#65] Test with Qwen | Open (or close as part of #66) | Hub Qwen3 models tested (`test_huggingface_text_generation_pretrained.py`, `test_huggingface_license_models.py`); `loom project https://github.com/QwenLM/Qwen3` (and `QwenLM/Qwen`) finds no Python project, so the rest is code inference | Backlog: ML framework and `transformers` use |
| [#66] `transformers` | Open | Hub configs read (#71); a `from_pretrained()` use in code is not read (`--scan-model-usage` matches file names, `extract/scanner.py`) | Backlog: ML framework and `transformers` use |
| [#68] ML framework detection | Open | Not built; only a Hub card's `library_name` is read | Backlog: ML framework and `transformers` use |
| [#77] G7 SBOM for AI | Open | Fields (#306, #309), checker-based G7 tests (#309), the `sbom-enrich` gap analysis are built; generation does not report missing elements | 0.22.0 headline; Backlog: SARIF output |
| [#79] model-provenance-kit | Research | Already named in [scitt-integration.md](scitt-integration.md) | Long-term: SCITT |
| [#81] CSVW round trip | Open, needs decision | Not built | To design: CSVW round trip |
| [#97] Provenance as `Annotation` | Closable | #102 (0.13.0); `format` `annotation`/`comment`/`both`, default `both`; a probe with `detail = "full"` gave an `Annotation` with schema `https://pitloom.dev/provenance/fields/1` beside the comment | - |
| [#103] Extension vs content | Open | Content type by magika (#138); model format from the header; no warning when a file's extension disagrees with its content | Open follow-ups: AI model scanning |
| [#110] Provenance profile | Open | Provenance is an `Annotation` with Pitloom's JSON schema, not an SPDX 3 extension | To design: Provenance vocabulary |
| [#122] Owners per surface | Not planned | A process decision, no code | - |
| [#129] OpenRouter | Research | - | [External work](external-references-to-review.md#openrouter-model-metadata) |
| [#147] SPDX 3.0 and 3.1 | Open | `specVersion` fixed at `3.0.1` (`assemble/spdx3/creation_info.py`) | To design: SPDX 3.1 output |
| [#150] Merge policy | Open | Documented in `docs/fragments.md` (the earlier element is kept, the project's own first); fragment over generated values is PR #349 (open); not configurable | 0.21.0: Fragment value beats an extracted one; To design: Fragments |
| [#154] Provenance vocabularies | Open | Parked draft | To design: Provenance vocabulary |
| [#170] Known organisations | Open | Not built: a project author is a `Person` unless its source types it; a warning, no guess | To design: Author strings |
| [#186] Sigstore model signing | Open | Not built; Sigstore signs only Pitloom's own release files (#180) | Long-term: PEP 740 |

[#30]: https://github.com/bact/pitloom/issues/30
[#41]: https://github.com/bact/pitloom/issues/41
[#46]: https://github.com/bact/pitloom/issues/46
[#48]: https://github.com/bact/pitloom/issues/48
[#51]: https://github.com/bact/pitloom/issues/51
[#52]: https://github.com/bact/pitloom/issues/52
[#53]: https://github.com/bact/pitloom/issues/53
[#55]: https://github.com/bact/pitloom/issues/55
[#61]: https://github.com/bact/pitloom/issues/61
[#62]: https://github.com/bact/pitloom/issues/62
[#65]: https://github.com/bact/pitloom/issues/65
[#66]: https://github.com/bact/pitloom/issues/66
[#68]: https://github.com/bact/pitloom/issues/68
[#77]: https://github.com/bact/pitloom/issues/77
[#79]: https://github.com/bact/pitloom/issues/79
[#81]: https://github.com/bact/pitloom/issues/81
[#97]: https://github.com/bact/pitloom/issues/97
[#103]: https://github.com/bact/pitloom/issues/103
[#110]: https://github.com/bact/pitloom/issues/110
[#122]: https://github.com/bact/pitloom/issues/122
[#129]: https://github.com/bact/pitloom/issues/129
[#147]: https://github.com/bact/pitloom/issues/147
[#150]: https://github.com/bact/pitloom/issues/150
[#154]: https://github.com/bact/pitloom/issues/154
[#170]: https://github.com/bact/pitloom/issues/170
[#186]: https://github.com/bact/pitloom/issues/186
