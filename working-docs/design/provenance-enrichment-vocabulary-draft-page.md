---
Created: 2026-10-04
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Draft: provenance and enrichment vocabulary page content

See also: [provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md)
-- the research, open questions and full inventory this page draws on.

The following is the full content that was published to
`docs/vocabulary.md` and then removed pending review. Kept verbatim so
resuming this doesn't require re-writing from scratch -- re-check it
against the code before re-publishing, since the code may have moved on
by the time this is picked up.

<!-- markdownlint-disable MD001 MD024 -->

### Provenance and enrichment vocabulary

> **Note:** Reference documentation for auditing or debugging a generated
> SBOM -- not needed to just generate one. This vocabulary is still in
> beta and can change without notice between releases.

Pitloom uses a small set of controlled string values to describe *how* it
determined an SBOM field's value and *what kind* of annotation it
produced. This page is the single place they're all defined -- several
of them share a field name (`role`, `method`) across otherwise unrelated
parts of the schema, which makes them easy to conflate if you've only
seen one corner of the codebase. Where a value isn't wired into Pitloom's
own code yet, that's called out explicitly.

#### Provenance method values

The `method` field in a provenance entry says *how* Pitloom arrived at a
value, not just where it read it from -- emitted inside the `fields`
provenance Annotation (see Annotation kinds below) and the legacy
`comment` string alike. A field with **no** `method` -- just a `source`
-- was read verbatim from the named file with no interpretation
involved.

| `method` | Meaning |
| --- | --- |
| `dynamic_extraction` | Read from a Python file at build time (e.g. a `__version__` or `__about__.py` variable), not from `pyproject.toml` directly. |
| `licenseid_detection` | License text matched against a known SPDX license using the [`licenseid`](https://pypi.org/project/licenseid/) library. Says how the value was read; the package's own `LICENSE` file is still declared unless the manifest states a license. |
| `inferred_from_authors` | Derived from the `authors` list (e.g. a copyright statement), not read verbatim from any single field. |
| `parsed_author_list` | Extracted multiple individual entities by splitting a single, comma-separated author string. |
| `file_directive` | A `pyproject.toml` dynamic field pointed at a file (`{file = "..."}`); the value was read from that file. |
| `attr_directive` | A `pyproject.toml` dynamic field pointed at a Python attribute (`{attr = "..."}`); the value was imported and read from code. |
| `inspect_caller` | Recorded automatically by the `pitloom.loom` tracking SDK via Python stack inspection -- identifies which script/function called the SDK. |
| `synthetic environment root` | The element is Pitloom's own synthesized placeholder root package for an installed environment (`loom env`), not extracted from any source file. |
| `yaml_frontmatter` | Read from a local README/model card's YAML frontmatter block during enrichment. |
| `magika_content_detection` | Per-file content type resolved by the [`magika`](https://pypi.org/project/magika/) content-detection library. |
| `extension_guess` | Per-file content type resolved by a filename-extension fallback (no `magika`, or no confident result). |

`magika_content_detection` and `extension_guess` are **not** the same
vocabulary as `[tool.pitloom.content-type] method` /
`--content-type-method` on Configuration -- that setting *chooses* the
detector; these two values are what the chosen detector *reports back*
as provenance once it runs.

`sbomAuthorSupplied` is **not** a `method` value -- it's a `role`; see
below. (An earlier draft of this page had it in both tables, matching a
code bug where it was wrongly emitted via the `method` slot; fixed
2026-08-13, see the `role` table.)

#### Provenance role values (epistemic)

`role` on a provenance candidate (e.g. in a `conflict` Annotation, an
enrichment's `changes[]` entry, or a per-field provenance entry) says
*whose* determination a value is, independent of *how* it was obtained.

| `role` | Meaning | Status |
| --- | --- | --- |
| `declared` | The subject's own stated claim, however observed. | Implemented |
| `detected` | Pitloom's own independent-verification procedure's result. | Implemented |
| `sbomAuthorSupplied` | Asserted directly by the human operating Pitloom (or an agent relaying their direct statement). | Implemented -- emitted for a per-file content type set via `[[tool.pitloom.content-type.override]]`, and by the `sbom-enrich` Skill's hand-authored fragments for a value the SBOM author stated directly in an interactive session. |
| `externalReported` | Some other party's own determination, relayed without Pitloom re-deriving it (e.g. a future linked GitHub/Hugging Face Hub API). | Reserved for future use |
| `inferred` | An AI agent's non-deterministic reasoning/judgment. | Not emitted by Pitloom's own deterministic code; emitted by the `sbom-enrich` Skill's hand-authored fragments for a value the agent derived itself, not stated by the SBOM author |

#### Dataset relationship roles

A **separate, unrelated** controlled vocabulary that happens to share the
name `role` -- this one labels *why* a dataset relates to an AI model,
not who determined a value. Set via `[tool.pitloom.enrich]`-driven
enrichment or read natively from a model source (e.g. a Hugging Face
model card).

| `role` | Meaning | Native SPDX 3 `RelationshipType`? |
| --- | --- | --- |
| `trainedOn` | Primary dataset used to train the model. | Yes -- `trainedOn` |
| `testedOn` | Dataset(s) used to evaluate the trained model. | Yes -- `testedOn` |
| `finetunedOn` | Dataset used for fine-tuning a pre-trained model. | No -- falls back to `other` plus an explanatory comment |
| `validatedOn` | Dataset used for validation during training. | No -- same fallback |
| `pretrainedOn` | Dataset used to pre-train a foundation model. | No -- same fallback |

Only `trainedOn` and `testedOn` are emitted by any extractor or enricher
today; the other three are defined vocabulary with a working fallback
path, ready for a future emitter.

#### Annotation kinds and schema envelopes

Every Annotation Pitloom builds uses SPDX 3's own `annotationType: other`
-- SPDX has no finer-grained type that fits, so the JSON `statement`
field's own `"kind"` key is what actually distinguishes one from
another. Each kind has its own schema URL, embedded in the statement:

| `kind` | Schema URL | Purpose |
| --- | --- | --- |
| `fields` | `https://pitloom.dev/provenance/fields/1` | Per-field `{source, method, ...}` map -- the default provenance Annotation described above. |
| `unification` | `https://pitloom.dev/provenance/unification/1` | Why two fragment elements were merged into one (matching SHA-256 content). |
| `conflict` | `https://pitloom.dev/provenance/conflict/1` | Multi-source field-value disagreement, e.g. declared vs. detected license. |
| `enrichment` | `https://pitloom.dev/provenance/enrichment/1` | What an enrichment run changed on an element; each entry in `changes[]` carries a `role` from the epistemic vocabulary above. |
| `artifact-metadata` | `https://pitloom.dev/provenance/artifact-metadata/2` | Verbatim preserved original AI-model metadata, gated by `[tool.pitloom.provenance] preserve-source-metadata`. |

This schema URL is a different thing from `[tool.pitloom.provenance]
schema` in `pyproject.toml` (default `"pitloom/1"`): the config value
picks the *encoder version* Pitloom writes with; the URL above says
*which kind* of Annotation a given statement is.

#### Minimum-elements gap status

The `sbom-enrich` Skill's minimum-elements workflow (NTIA 2021, CISA
2026, G7 SBOM for AI 2026) uses a small status vocabulary of its own when
reporting what's missing, distinct from the provenance vocabulary above:

| Status | Meaning |
| --- | --- |
| `covered` | Pitloom emits this deterministically; nothing to do. |
| `conditional` | Emitted only when a dependency resolves against PyPI/installed metadata or similar -- verify per run. |
| `gap` | Missing; filling it in is this workflow's actual job. |
| `not automatable` | No file or answer this workflow can gather will satisfy this element. |

The full standard-by-standard field mapping lives in the Skill's own
minimum-elements reference
(`skills/sbom-enrich/references/minimum-elements.md`).

<!-- markdownlint-enable MD001 MD024 -->
