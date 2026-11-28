---
Created: 2026-11-14
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Method: what was done to get a value

See also: [README.md](README.md) (the claim model),
[basis.md](basis.md), [change.md](change.md),
[renames-and-migration.md](renames-and-migration.md) (every old `Method`
value), [resweep-rulings.md](resweep-rulings.md) (rulings C4 and C7 of
2026-11-28, written in here). Replaces section 1 of
[provenance-enrichment-vocabulary.md](../provenance-enrichment-vocabulary.md).

**Status:** draft. Two levels, as ruled 2026-11-14. Five classes: the
class `inferred` was dropped 2026-11-16 (it is an
[basis](basis.md) value). Re-based on `main` dfa11c14 on 2026-11-28;
nothing here is built.

## Definition

The **method** of a claim is what Pitloom did to turn the source into the
value. How the value came to exist is another question, answered by
[Basis](basis.md); what an AI agent or the SBOM author did is not
Pitloom's method, so their claims have none. It has two levels:

- a **class** (`Method`), one of five, closed: enough for code to branch on;
- a **technique** (`Technique`), a registered name inside one class: enough
  to reproduce the step. Optional: many claims need only the class.

The tool and its version go in `Tool`, never in either name.

Today's 31 `Method` values (29 at the base 257b7260; 31 on `main`
dfa11c14, by grep, each with a row in the tables below;
[renames-and-migration.md](renames-and-migration.md), the sweep) are
flat and mix four things: how a value was
read, what it is (`repository_owner`), how sure it is (`lfs_pointer`) and
which candidate was picked (`latest-release`). Only the first is a method.

## Classes

| Class | Definition | Default asserter | Default basis |
| --- | --- | --- | --- |
| `read` | The source states a value for this field, and the value is that statement: one key, field, tag or attribute of the source. | the source's | the asserter's default ([basis.md](basis.md), rule 5) |
| `parsed` | The source states a value for this field inside a larger text; the value is a part picked out or split off, nothing added. | the source's | the asserter's default |
| `matched` | The source holds a text or content; the value names its best match in a reference set. | `sbom-tool`; `originator` for the element's own licence text ([asserter.md](asserter.md), rule 5) | `detected`; for the originator's own licence text, `declared` (ruled 2026-11-21; [asserter-licence.md](asserter-licence.md), "The form of a text match") |
| `derived` | The source states no value for this field; the value is counted, measured or decoded from the thing itself by a documented rule with one right answer. | `sbom-tool` | `measured` |
| `synthesized` | The source states no value for this field; Pitloom concludes one from a proxy (something that stands for the property and is not it) or composes one, and another tool could give a different one. | `sbom-tool` | `inferred` |

`read` is the default and is not written. A claim by `sbom-author` or
`ai-agent` has no method; a `Tool` on one names the agent that made the
reading ([asserter.md](asserter.md), rule 8). `Asserter` is always written, so a missing
`Method` reads as `read` on an `originator` or `other-party` claim and as
"none" on those two. A `lower-bound` or `not-measured` claim is an
`sbom-tool` claim and carries the class and technique of the read that was
tried (`derived`, `content-hash`).

## Choosing the class

Ask in this order; stop at the first yes.

1. Did a matcher pick the value from a reference set by similarity?
   `matched`.
2. Does the source state a value **for this field**?
   - It is one key, field, tag or attribute of a structured format (TOML,
     JSON, YAML, Core Metadata, front matter, a model header): `read`.
   - It is inside free text, or one value split into several: `parsed`.
3. The source states none. Did the procedure examine the thing itself, and
   is there one right answer by a documented rule (a count, a size, a
   digest, a decoding, a lookup of a code the content holds)? `derived`.
4. Otherwise (a proxy was examined, or the value is composed):
   `synthesized`.

Steps 2 and 3 decide the hard cases. A model's name made from its file name
is `synthesized`: the file name is not a statement of the model's name, and
stands for it only. A content type from a file extension is `synthesized`
too: the extension stands for the content and can be wrong, where a matcher
on the bytes is `matched`. A domain a format implies is `synthesized`: the
format fixes that the model handles text, the wording is Pitloom's.

**A split by a rule that can be wrong stays `parsed`** (ruled
2026-11-28, C4 of [resweep-rulings.md](resweep-rulings.md)). An author
field split into several authors by a rule that cannot tell `Doe, Jane`
from a list is still the originator's statement, cut up; nothing is
added, and the value does not move to `synthesized`. The doubt is shown
in two places: the technique names the rule (`list-split`, or a name of
its own: open), and a [Change](change.md) step says the value was
divided. What the code does today (read at dfa11c14, not built to this
rule):

- The rule: an address field (`Author-email`) is split on `,` and
  `;`; a name field (`Author`) is one author, cut only next to the
  complete mailboxes it holds (`field_parts`,
  `extract/_author_parts.py:213-224`; `_field_entries`,
  `extract/authors.py:256-275`, which notes each split field).
- The warning: `author-ambiguous`, whose summary calls the read "a
  guess" (`messages/_authors.py:73-101`), said through
  `warn_author_splits` (`extract/_author_warnings.py:80-98`), called from
  `extract/authors.py:381`, `_embed_build_sbom.py:419` and
  `_embed_generate.py:342`. Stderr only: nothing in the SBOM says a
  project's authors were split; a wheel's `authors` entry is its plain
  `Source` (`extract/wheel.py:150`).
- A dependency's originators, when its fields name more than one, get
  `Method: parsed_author_list` (`assemble/spdx3/deps_originator.py:304-308`);
  an ONNX `model_author` split on commas gets `comma_list`
  (`core/model_originators.py:31`). Both become `list-split` (the
  mapping of 2026-11-14 to 2026-11-23; the technique names are open
  again under C4).

Rules that hang on the class:

- A fragment's value replaces a `synthesized` value (today:
  `GENERATED_METHODS`, and the separate file-name-stem rule for a model's
  name).
- `matched` always carries `Tool`: the result depends on the tool's version
  and data.
- The class gives the default [basis](basis.md) of an `sbom-tool`
  claim (table above), so the two cannot disagree. `placeholder-root` is
  the exception: a structural stand-in is no claim about the world and has
  no basis.

## Techniques

Registered names, kebab-case, a noun phrase for the operation. No tool,
format or product name; no basis word (`detected`, `declared`,
`inferred`).

| Class | Technique | What it does | Was |
| --- | --- | --- | --- |
| `read` | `file-directive` | content of the file a `file:` directive names | `file_directive` |
| `parsed` | `assignment-scan` | the string assigned to a named attribute, found in module source without running it | `attr_directive`, `dynamic_extraction` |
| `parsed` | `list-split` | one text split into several values | `comma_list`, `parsed_author_list` |
| `parsed` | `copyright-lines` | copyright-shaped lines of a licence file | `copyright_notice_lines` |
| `parsed` | `url-path` | an identifier picked out of the path of a URL the source states (added 2026-11-23: a dataset's id in the `repo_url` of a GGUF entry) | on `main`: `hub_dataset_id`, for a name |
| `matched` | `license-text` | a licence text matched to an SPDX id | `licenseid_detection` |
| `matched` | `content-type` | file content matched to a media type | `magika_content_detection` |
| `derived` | `content-hash` | digest of the bytes read | (no entry today) |
| `derived` | `file-stat` | a size from the file system, content not read | `Evidence: measured_stat` |
| `derived` | `tensor-element-sum` | the sum, over every tensor the file lists (a safetensors header, GGUF `tensor_infos`, ONNX initializers; on `main` also PT2 `model_weights_config.json`) and of every data type, of the product of its shape; a file that is one part of a split model gives no count | `tensor_element_sum` (file route) |
| `derived` | `element-count` | count of array elements, archive members, layers or labels, as the part that holds them gives it; for a CRFsuite model's parameter count, the feature count of the `FEAT` chunk (`FEAT.num`), each feature storing one weight (ruled 2026-11-23) | `array_length`, `member_count`; on `main` also `one_weight_per_feature` |
| `derived` | `packed-version` | integer decoded as a packed version | `semver_bit_packed` |
| `derived` | `code-lookup` | a header code mapped to its documented meaning | `crfsuite_model_type` |
| `derived` | `caller-frame` | the calling script found by stack inspection | `inspect_caller (tool: ..., function: ...)` |
| `synthesized` | `file-name-stem` | a name made from the file name | `file_name_stem` |
| `synthesized` | `file-extension` | content type looked up from the file name's extension | `extension_guess` |
| `synthesized` | `format-implied` | a value the format implies and the file does not state | `derived_from_format` |
| `synthesized` | `label-summary` | a description written from a label list | `generated_from_labels` |
| `synthesized` | `placeholder-root` | a root package standing for an environment | `synthetic environment root` |

Old values that need no technique, because another facet already says it:

| Was | Becomes |
| --- | --- |
| `yaml_frontmatter` | `read`; `Kind: card` says where |
| `resolved_lockfile`, `pinned_requirements` | `read`; `Kind: lock-file` or `pin-file` says which |
| `flit_dynamic_metadata`, `pdm_dynamic_version(<source>)` | `read` from `Kind: build-backend`, with `Tool` naming the backend; the configured PDM source goes in `Location` |
| `lfs_pointer` | `read` from `Kind: pointer`, `Location: oid`, `Asserter: originator` |
| `repository_owner` | `read`, `Location: repository owner`, on a `registry` source |
| `tensor_element_sum` on the Hub route | `read`: the Hub states the total (`Asserter: other-party`, `Basis: detected`) |
| `licenseid_resolution` | `Written` and `Change` ([change.md](change.md)), with `Tool` |
| `hub_dataset_id` for a location (on `main`) | `read`, with `Written` and `Change: respelled` ([change.md](change.md), ruled 2026-11-23) |
| `latest-release`, `running-environment` | `Rule` ([conflict.md](conflict.md)) |

`caller-frame` drops the embedded tool and function: `Tool: pitloom.loom`,
`Location: <function>`.

## Stand-ins

Ruled 2026-11-28 (C7 of [resweep-rulings.md](resweep-rulings.md)): **a
stand-in is no claim.** Where a format requires a value that no source
gives, Pitloom writes a stand-in; it says nothing about the world, so it
has no asserter's statement behind it and no basis, as `placeholder-root`
already has none (above, "Rules that hang on the class"). The stand-ins
form one small closed list, marked as such in the output; the members
are open. A default source label (`Unknown source`, rule 5 of
[source.md](source.md)) is not a stand-in: it is a missing source, a
fault to fix at the reader.

Stand-ins in the code at dfa11c14 (read; none is marked as a stand-in
today):

| Stand-in | Where | What the code does |
| --- | --- | --- |
| the root of an environment | `extract/env.py:125-133` | name `deployed-environment`, version `0.0.0`, provenance `Source: Pitloom generator \| Method: synthetic environment root`: today's `placeholder-root` |
| the name `unknown` of a wheel | `extract/wheel.py:254` | `ProjectMetadata(name="unknown")` before the `.dist-info` is chosen; it stays when there is no own `.dist-info` or `METADATA` (`dist-info-missing`, `dist-info-ambiguous`, as a `WARNING:`: the `did` text, `messages/_wheels.py:180-186`; that the name survives into the SBOM was taken from that text, not traced) |
| the name `unknown` of an sdist | `extract/project/sdist.py:383`; `extract/project/_sdist_pyproject.py:106` | no `PKG-INFO` and no `pyproject.toml`; or a `pyproject.toml` with no `name`. The `config-malformed` `did` text says an sdist whose `pyproject.toml` does not parse and that has no `PKG-INFO` "is named unknown" (`messages/_config.py:192-215`) |
| the version `unknown` | `assemble/spdx3/_document_main_package.py:90` | `metadata.version or "unknown"` (and the same at other call sites, grep) |
| a creation time of 1970 | `assemble/spdx3/_fragments_envelope.py:45,118-119` | `_NO_CREATED`, the start of 1970, when neither `SOURCE_DATE_EPOCH` nor a fragment gives one, with the `WARNING:` `datetime-missing` |

Not a stand-in: `Source: unknown | Method: inspect_caller (tool:
pitloom.loom)` (`_loom_caller.py:138`, read), written when the call stack
cannot be read (`caller-info-unreadable`). The value is real (a caller
exists); its source label is a default, so rule 5 of
[source.md](source.md) applies.

## Adding a technique

A code change that adds a reader adds a row here and in the user docs, in
the same change; a drift test holds the code's registry equal to the docs
table (today: `tests/test_provenance_method_rows.py`, which a regex feeds
and which misses constants). The registry is one table in
`core/provenance.py`; `provenance_segment` refuses an unregistered
technique, and a technique in the wrong class.

Before adding one, ask: is it the same operation as an existing technique on
another format? Then reuse it (`element-count` serves GGUF arrays and ZIP
members). Does the name say who, how sure or which candidate? Then it is not
a technique.

## Open points (2026-11-28)

1. Ruling C4: the technique name of a split by a rule that can be
   wrong (`list-split` for every one, or one per rule), and whether its
   step is a new kind of [Change](change.md) or an existing one.
2. Ruling C7: the members of the list of stand-ins, and how a stand-in
   is marked (a technique of its own beside `placeholder-root`, or one
   name for all).

## Mappings (loose)

| Class | PAV | SEMAPV | CycloneDX `technique` | Wikidata | ECO |
| --- | --- | --- | --- | --- | --- |
| `read` | `pav:retrievedFrom` | - | `manifest-analysis` | P248 stated in | `ECO:0000204` author statement |
| `parsed` | `pav:importedFrom` | `semapv:RegexReplacement` (nearest) | `manifest-analysis`, `source-code-analysis` | P248 stated in | `ECO:0000311` imported information |
| `matched` | `pav:derivedFrom` | `semapv:LexicalSimilarityThresholdMatching` | `other` | P887 based on heuristic | `ECO:0000041` similarity evidence |
| `derived` | `pav:derivedFrom` | `semapv:LogicalReasoning` | `binary-analysis`, `hash-comparison`, `filename` | P459 determination method or standard | `ECO:0007669` computational evidence used in automatic assertion |
| `synthesized` | `pav:createdBy` | - | `other` | P887 based on heuristic | - |

PAV's line between imported and derived (was knowledge contributed, or the
content refined or modified) is the line between `parsed` and `derived`.

In SSN/SOSA terms a class with its technique is a `sosa:Procedure` ("a
workflow, protocol, plan, algorithm, or computational method"), `Tool` is
the `sosa:Sensor` that implements it, and Pitloom is the `sosa:Platform`
that hosts the sensors. The released key stays `Method`.

In PROV-O the first two are a `prov:Plan` and a `prov:SoftwareAgent`
associated with Pitloom's act (`prov:wasAssociatedWith`); the recorded
value is `prov:wasGeneratedBy` that act. PROV-O has no platform. SOSA's
alignment, which is not normative, makes `sosa:Procedure` a subclass of
`prov:Plan` and `sosa:Sensor` of `prov:Agent`, so the two readings agree.
SIO's nearest term is `plan` ("a set of intended actions, through which
one expects to achieve a goal"), a kind of its `action specification`.
The pattern: [alignment.md](alignment.md).
