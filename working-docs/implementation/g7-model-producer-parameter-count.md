---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# G7 #6: model producer and parameter count

See also: [g7-ai-sbom-coverage.md](../design/g7-ai-sbom-coverage.md) (the G7
plan this item came from), [model-metadata-readers.md](../design/model-metadata-readers.md)
(the planned stdlib readers must keep the count),
[model-file-metadata.md](sbom-generator-field-notes/model-file-metadata.md)
(the measured facts), and the user pages
[ai-model-formats.md](../../docs/ai-model-formats.md#producer-and-parameter-count),
[ai-model-scan-limits.md](../../docs/ai-model-scan-limits.md) and
[metadata-provenance.md](../../docs/metadata-provenance.md).

Status: complete, PR #306. What was built, and why. An `ai_AIPackage`
gets the producer names a
structured source states as `originatedBy`, the Hugging Face repository owner
also as `suppliedBy`, and a model's parameter count as an `ai_hyperparameter`
entry. Core fills only structured sources; a name that sits in prose, and the
decision between `Person` and `Organization`, stay with the `sbom-enrich`
Skill (scope split of 2026-09-17).

## What it does

- `AiModelMetadata.originators: list[str]` (names as read, source order) and
  `parameter_count: int | None` (honest fields: `None` when the source does
  not say). Fallbacks and mapping live in the assembler, not the readers.
  `AiModelMetadata.supplier: str | None` is filled by the Hugging Face
  reader only. The provenance keys of an AI model are these field names
  (`originators`, `supplier`, `parameter_count`), not the SPDX names
  (`originatedBy`, `suppliedBy`, `hyperparameters.parameters`); a
  dependency's or the main package's `originatedBy` provenance key is
  unchanged.
- `assemble/spdx3/_ai_originators.py::add_model_originators` mints one
  generic `spdx3.Agent` (name only) per name, finds an existing one through
  `agent_key(spdx3.Agent, name, None)`, sets `originatedBy`, and sets
  `suppliedBy` only from `supplier` (one name; the same `Agent` element as in
  `originatedBy` when the names are equal, not a second one). Both
  orchestrators (`ai.py::_add_single_ai_model` and
  `_document_model.py::build_model`) call it right after the base-model
  lineage, so every surface that builds an `ai_AIPackage` gets it.
- `_ai_package.py::_populate_ai_pkg_hyperparameters` adds the entry
  `parameters` (decimal text), sorted with the other keys, `quantization`
  first. The package `comment` is built once (the count note, then `Known
  biases: ...`), before provenance appends its own. A fragment merge
  derives the note again (below).
- Bounded arithmetic in `core/model_parameters.py`
  (`tensor_elements`, `tensor_element_sum`, `stated_parameter_count`);
  the name list in `core/model_originators.py` (`originator_names`); the
  reader-side warning and provenance in
  `extract/ai_model/parameter_count.py` (`derived_parameter_count`).

## Decisions and evidence

**`originatedBy` for every route; `suppliedBy` for the Hub route only**
(owner decision, review round 3). A producer name a file states is an
originator: the file does not say who ships it, so no file format (ONNX, PT2,
GGUF, Safetensors, `loom`/hand-built models) sets `suppliedBy`. A model read
from the Hugging Face Hub gets the repository owner (`info.author`) as both:
the format reason is that the Hub repository is where the artifact is shipped
from (the distribution source), and the artifact in it is made by that owner.
Spec: `originatedBy` is "from where or whom the Element originally came",
`suppliedBy` the actual distribution source. Evidence: the bact G7 mapping
(`g7ai2026-to-spdx31.sssom.tsv`) maps G7 "model producer" to `originatedBy`
with `skos:exactMatch` and to `suppliedBy` with `skos:closeMatch`, "for a
distributing hub or vendor": a Hub repository is a distributing hub, and its
owner is both. One generic `Agent` carries both properties when the name is
the same, and `suppliedBy` is single-valued, so there is one owner. Provenance
for `supplier` is `Source: Hugging Face Hub | Field: model_info author |
Method: repository_owner`, the same text as the owner's `originators` entry.
This answers the PyThaiNLP follow-up of #292 (its three ONNX models set
`model_author` after release 5.3.9, yet the SBOM showed no supplier): for a
file the author is an originator and the SBOM shows it now; the Hub route
also shows the repository owner as supplier.

Counter-example, which is why lineage and the Skill matter: the owner of
`openai-community/gpt2` is not the original producer (OpenAI). The owner is
the supplier and the uploader; `originatedBy` then says the uploader as well,
because the model records no other producer. A re-upload, quantisation or
fine-tune is told apart only by the base model the card names, recorded as a
`descendantOf` edge, which records lineage only (the base-model package has
no `originatedBy`), and by the Skill, which can add the real maker from the
card.

The main package's `suppliedBy` is never inherited by a model: it is only
the first SBOM creator, so inheriting it would assert something nobody
stated (rejected, below).

**A generic `Agent`, not `Person` or `Organization`.** No structured source
says which: ONNX `model_author` is a name list, PT2 `extra/author` a string,
GGUF `general.author` and `general.organization` strings, the Hub `author`
an account that may be a user or an organisation. `Agent` is concrete in
3.0.1 and the output passed `spdx3-validate` (schema and SHACL) in the
probe and again on a built ONNX model with two names. The dedup key
`agent_key(spdx3.Agent, name, None)` and the id prefix `Agent` shift no
existing id (people use `Person`, organisations `Organization`, dataset
creators their own prefix). The Skill may add a `Person` or `Organization`
by fragment; a merge unions lists, so the generic `Agent` stays beside it.

**The Hub owner is originator and supplier.** `info.author` is the
repository owner. Both entries are recorded with `Method: repository_owner`
because "Hugging Face Hub" is a transparent source: provenance with no
`Method` is dropped in `minimal` mode, and the owner must stay visible as an
owner. The re-upload argument: the owner of a repository can be an uploader,
not the maker. That is true, and the method says what it is; see the
counter-example above. No extra network call: the owner is on the default
`model_info`.

**ONNX `model_author` is a comma list.** The IR spec ("Optional Metadata")
defines it as a comma-separated list of names, so the text is split on
commas and `Method: comma_list` is recorded only when the text has a comma.
Known caveat, pinned by a test: `Doe, Jane` and `Foo, Inc.` are split
wrongly. No heuristic repairs it (see rejected paths). PT2, GGUF and the
Hub give one name each, not split. The raw keys stay in `properties`.

**Safetensors `modelspec.author`** is one originator. ModelSpec is a
defined structured key set and the reader already honours its other
`modelspec.*` keys (title, description, version, architecture, precision);
the Safetensors format itself has no author key. The value is one name, not
split on commas (a name may hold one), with provenance `Field:
__metadata__.modelspec.author`. A file without the key has no producer,
silently.

**GGUF `general.organization`** is also an originator (after `general.author`,
the order they are read). A non-string value is silent: it stays in
`properties`.

**The count has no SPDX field.** SPDX 3.0.1 (and 3.1-dev) have no model-size
property. The bact G7 mapping names the `ai_hyperparameter` entry with key
`parameters` as the carrier, so that is what Pitloom writes: key
`parameters`, value `str(n)`. Rejected carriers:

- `ai_metric` is for performance results, not a property of the model.
- `software_artifactSize` is the storage size in bytes (and 3.1-only).
- `ai_typeOfModel` text (`7B`) mixes a rounded label into a type list.
- GGUF `general.size_label` is a rounded string, not a count (and is not
  `general.parameter_count`, which is not a defined GGUF key).

**The package says so.** On user request while reviewing the plan: a
hyperparameter is not the parameter count in SPDX, so whenever the entry is
written the package `comment` gets one constant ASCII line
(`PARAMETER_COUNT_NOTE`): `Parameter count: ai_hyperparameter "parameters"
holds the number of elements in the model's stored tensors, as its parameter
count, because SPDX 3.0.1 has no model-size property (it is not a
hyperparameter).` It is not provenance and does not depend on the
provenance format. A rejected count adds no note; a colliding valid count
replaces the model's own `parameters` entry and keeps the note. The comment
had two writers (known biases overwrote it, provenance appends with a
newline), hence the single write. The fragment merge derives the note
instead of trusting a fragment's `comment`: after a merge into it, an
`ai_AIPackage` with a `parameters` entry that reads as a count carries the
note as the first comment line and one without has none (a package no
fragment merges into keeps its comment as written), so the `sbom-enrich`
Skill never types it into a fragment (a base `parameters` entry still wins
over a fragment's).

**What is counted.** The sum of tensor element counts, not bytes (`[32, 2]`
adds 64 whatever the type), `Method: tensor_element_sum`. The Hub's stated
count (`safetensors.total`, else `gguf.total`; `safetensors` wins when both
exist) is the same sum computed by the Hub, so it carries the same `Method`
too: it stays visible in the default `minimal` provenance mode, and the method
means the same in every format. Before review round 3 it carried none.

**What the count means** (review round 3; the full statement is in
[ai-model-formats.md](../../docs/ai-model-formats.md#what-the-count-counts)):
the number of elements of all stored tensors, not the "trainable parameters"
of `bom:ai-model-size`. Buffers stored as tensors and tied weights stored twice
are in it (`gpt2-tiny-decoder.onnx` 404256 holds a 262144-element uint8 mask
`transformer.h.0.attn.bias` and a 32000-element transposed copy of
`wte.weight`, so about 110112 are weights of their own; `marian-tiny-random`
174535 holds the 58101-element `final_logits_bias`; `squeezenet1.1-7` 1235498
is 1235496 weights and a 2-element reshape constant; the Hub API gave
137022720 for `gpt2`, 2026-10-15, against about 124.4M weights). Packed
weights count differently: GGUF shapes are logical, but GPTQ, AWQ and
bitsandbytes Safetensors store packed integers (a GPTQ-style 64 x 64 layer
counts 648 against 4096), block-quantised ONNX under-counts, and a Hub total
can cover part of a multi-component repository
(`stabilityai/stable-diffusion-xl-base-1.0`: the UNet). No filter by dtype:
int8 weights are parameters.

- GGUF: `reader.tensors[*].shape`, already in memory; read before the reader
  is released. `n_elements` is never used (`numpy.prod` wraps).
- Safetensors: `get_slice(key).get_shape()` over every key, before the
  1000-entry cap on `inputs`. A shard gives its own file's count: the format
  has no sign of being a shard. Documented, not fixed.
- ONNX: initializers, sparse initializers (dense `dims`) and subgraphs of
  node attributes (`attr.type`, not `HasField`: a mock is truthy), walked
  with a stack. External-data tensors count by declared `dims` (the file is
  not read). `Constant` nodes and `model.functions` are not counted.
  Block-quantised tensors (`MatMulNBits`-style) are counted at stored size:
  an under-estimate.
- GGUF with `split.count` above 1: no count. The file holds a shard of the
  tensors and a per-file sum would understate the model; `split.count` is a
  structured signal, so the omission is exact.
- Hub: `info.safetensors.total`, else `info.gguf.total`, read in
  `_load_model_info`; the failure wording for a lost call names both among
  the skipped fields. Provenance: `Source: Hugging Face Hub | Field:
  model_info safetensors.total | Method: tensor_element_sum` (or
  `gguf.total`).

**Caps.** A count over 10**15 is not recorded: 16 digits, so `str()` is safe
under the 3.11+ integer-digit limit and the outcome is the same on every
Python. The product is cut as soon as it passes the cap, so a huge
dimension is never multiplied out; a later zero dimension still gives 0. A
negative, boolean or non-integer dimension, or a stated count that is not a
non-negative integer, is rejected the same way. A rejection anywhere gives
no count (never a partial sum) and one `WARNING:` ending `parameter count
not recorded`, `FORMAT=<fmt> FILE=<path>:` prefixed (readers pass the model
path; the scanner relays the record). The Hub is not scanned and prefixes
itself. The name list is cut by `cap_entries` at `MAX_MODEL_ENTRIES` (the
provenance keys `originators`, `supplier` and `parameter_count` name no
entry of a cut map, so no cut drops them); each name is cut as a model's own
name is, and all the cuts of one model give one `WARNING:` ending `model
originator name cut` (with `model supplier name` for a supplier that is not
also an originator), not one per name (`add_model_originators`). ONNX
`model_author` is split lazily and examines at most `MAX_ORIGINATOR_PARTS`
non-empty comma-separated parts (16 x (1000 + 1) = 16016; an empty piece
between commas does not count, a whitespace-only one does), so a value of
millions of commas or of one repeated name stays cheap. Names past
the bound are not read, and the reader says so: one `WARNING:` per read
through `ORIGINATOR_PARTS_CAP` (`rest of model_author not read`), the
scanner relaying it with `FORMAT=onnx FILE=`. Decision: silence would have
been a "no silent deviations" breach, and a value that is all padding
(`" ," * 16016 + "Real Author"`) would have lost its author unannounced.
`originator_names_cut()` returns the names and the cut flag (true only when a
part was left unread; a bound met exactly at the end is no cut), and
`originator_names()` wraps it, so the many other callers are unchanged.

**Absent is not zero.** A sum of 0, or no tensor, is no count and says
nothing (the AGENTS.md rule for absent source data): an empty model is not a
model with `"0"` parameters. A stated `0` is the same.

**Collision.** A model-declared hyperparameter `parameters` is replaced by
the count with a `WARNING:`. The Pitloom-derived number outranks a free
hyperparameter; fragments, merged later, lose to the base's entry
(`_merge_dictionary_entries`: canonical wins).

**Registry.** `--update-id-registry` also writes the generic model Agents
into the registry file (an `Agent` table, no counter), as it does for
`Person`, `SoftwareAgent` and `Tool`. Nothing looks the `Agent` type up and
the output is unaffected; no lookup or key changes, but users who commit the
registry will see new rows.

**Formats left silent**, each for a stated reason: PT2 (no weights metadata
read), PyTorch pickle (no shapes without unpickling), Keras and HDF5
(weights not read), NumPy (a bare array is not a model), fastText (matrix
size follows the dictionary stream), CRFsuite (no shapes in the header read).

## Probe matrix

Measured 2026-10-15 on the fixtures under `tests/fixtures/aimodels/`; only
`pytorch_pt2/example-model.pt2` carries an author (`extra/author` is
`Pitloom`, pinned by `test_pytorch_pt2_originators.py`).

| Format | Source key | What is read | Maps to | Status |
| :----- | :--------- | :----------- | :------ | :----- |
| GGUF | `general.author`, `general.organization` | one string each | `originatedBy` | built |
| GGUF | `tensor_infos` | dims, summed (`Field: tensor_infos`) | `parameters` | built: stories260K 292800; mmproj-tinygemma3 844288; two vocab-only files 0 tensors, no count |
| GGUF | `split.count` > 1 | int | no count | built |
| GGUF | `general.parameter_count` | not a defined key | -- | not used |
| GGUF | `general.size_label` | rounded string | -- | not used |
| Safetensors | header shapes | `get_shape()` per key (`Field: tensor shapes (header only)`) | `parameters` | built: marian 174535; phi 80074; speech2text 173968; vits 74142; whisper 216632 |
| Safetensors | `__metadata__` `modelspec.author` | one string | `originatedBy` | built; no fixture has it (the format has no author key of its own) |
| ONNX | `metadata_props.model_author` | comma list | `originatedBy` | built |
| ONNX | `graph.initializer`, `graph.sparse_initializer` (+ subgraphs) | dims, summed (`Field: graph.initializer, graph.sparse_initializer`) | `parameters` | built: encoder-q4f16 4890637; gpt2-tiny-decoder 404256; light-inception-v2 5417; resnet-tiny-beans 189347; squeezenet1.1-7 1235498 |
| PT2 | `extra/author` | one string | `originatedBy` | built |
| PT2 | weights | not read | -- | silent |
| Hugging Face | `info.author` | repository owner | `originatedBy` and `suppliedBy` (one `Agent`), `Method: repository_owner` | built |
| Hugging Face | `info.safetensors.total`, else `info.gguf.total` | stated int | `parameters`, `Method: tensor_element_sum` | built: `openai-community/gpt2` 137022720 from the default `model_info` (Hub API, 2026-10-15) |
| PyTorch classic, Keras, HDF5, NumPy, fastText, CRFsuite | -- | -- | -- | silent, see above |

The probes also found that `safe_open` (0.8.0) checks
shapes against offsets, which bounds a Safetensors count by the file size;
the GGUF reader's `numpy.prod` wrap is caught by its own reshape (`[2**32,
2**32]` is a read failure); ONNX `dims` are signed and unchecked, hence the
cap and the negative-dimension warning. See
[model-file-metadata.md](sbom-generator-field-notes/model-file-metadata.md).

## Rejected paths

- **`ai_metric` for the count**: performance results; a size is not one.
- **`software_artifactSize`**: storage bytes, 3.1-only; not the parameter
  count and not available in 3.0.1.
- **`general.size_label` or a name-embedded `7B`**: a rounded label, text
  parsing.
- **Heuristics to split or repair names** (an organisation suffix list,
  `Lastname, Firstname` detection): every rule has a counter-example, and
  author-entity recognition has its own design
  ([author-entity-recognition.md](../design/author-entity-recognition.md)).
- **Reusing `authors.py`'s 64 KiB pre-cut**: that reader works on project
  metadata fields; the model path has the 1000-entry and 1024-character caps
  and `originator_names` collects lazily (`re.finditer` over the non-empty
  parts) and stops one past the cap so the cut warns.
- **`suppliedBy` inheriting the main package's supplier**: a false claim
  (above).
- **`suppliedBy` for file formats**: a file-declared author is an
  originator; the file says nothing of who ships it. Only the Hub route has a
  distribution source in its data.
- **The Hub owner as `originatedBy` only** (the earlier decision, reversed by
  the owner in review round 3): it left the distributing hub, which the G7
  mapping names for `suppliedBy`, unrecorded.
- **Hub org-versus-user lookups** to choose `Person` or `Organization`: an
  extra request per model for a distinction no other source makes; left to
  the Skill (follow-up).
- **A per-file sum for a split GGUF**: it would understate the model.
- **`"0"` for an empty model**: not a count.

## Review round 3

Findings of the third review and what was decided.

| Finding | Decision |
| :------ | :------- |
| The count was called "parameters" but counts every stored tensor (masks, shape constants, tied weights, packed integers) | Say so, once, in [ai-model-formats.md](../../docs/ai-model-formats.md#what-the-count-counts); skills and this doc summarise in a line or two. The note text now says "the number of elements in the model's stored tensors". No dtype filter |
| Docs said an originator `Agent` has "no registry key" | Wrong: `--update-id-registry` records it by name under an `Agent` table, and nothing looks it up. Docs say "a counter id (recorded by name, never looked up)" |
| The skill told the agent to type the note into a fragment | The merge derives the note (see "The package says so"); the instruction is gone from `minimum-elements.md` |
| `minimum-elements.md` marked the count "covered" | "Covered by convention (SPDX has no parameter-count field)"; a G7 `GAP` in the bact mapping, which gives only `broadMatch` to `ai_hyperparameter` |
| The Hub count had no `Method`, so its provenance was dropped in `minimal` mode, and `gguf.total` was ignored | `gguf.total` read when `safetensors` is absent; both carry `Method: tensor_element_sum` |
| Provenance keys `originatedBy` and `hyperparameters.parameters` named SPDX fields | Keys are the field names, `originators` and `parameter_count`; dependency and main-package keys unchanged |
| `Field:` labels read like code objects ("tensor infos", "graph initializers") | `tensor_infos`; `graph.initializer, graph.sparse_initializer`; `tensor shapes (header only)` |
| "As the G7 mapping does" over-claimed | The G7 mapping names the key `parameters` only; the docs say that |
| GGUF `general.organization` is often a converter guess | Read as stated. Caveat in the format page, the Skill and here: llama.cpp fills it from the base model's `_name_or_path`, so a fine-tune can name the base's organisation, Pitloom cannot tell stated from guessed, and the Hub route names the repository owner, so one file can show two producers by route |
| The `descendantOf` edge was said to carry the maker's line | It records lineage only; the base-model package has no `originatedBy` |
| Should the Hub owner also be `suppliedBy`? (open question) | Yes, on the Hub route only: both properties, one `Agent`, `Method: repository_owner`; new field `supplier`. No file format sets `suppliedBy` |

**Resolved: the Hub owner is `originatedBy` and `suppliedBy`** (owner
decision on the open question of this round; details under "Decisions and
evidence"). A reviewer recommended `suppliedBy` = owner on the Hub route
because the G7 SSSOM row says `suppliedBy` for a distributing hub or vendor;
the counter-example `openai-community/gpt2` (owner not OpenAI) is why
lineage (`descendantOf`) and the Skill stay. File formats keep
`originatedBy` only. Related, not decided:

- `general.quantized_by` as an originator of a post-training or quantisation
  step (the G7 definition of producer names fine-tuning companies).
- Dataset creators map to `publishedBy`, while model producers map to
  `originatedBy`: a divergence that predates this item; a follow-up.
- The G7 mapping also names `context_length`; Pitloom emits source-native
  names (`llama.context_length`).

All three are follow-ups (below).

**SPDX 3.1-dev, forward notes.** `Agent` is still concrete;
`originatedBy` and `ai_hyperparameter` are unchanged; 3.1 has no
parameter-count property either. Storage size is `software_artifactSize` in
the 3.1 binding while the bact mapping 0.4.0 calls it `spdx3-sw:byteSize`:
name whichever ships. `Organization.headquartersLocation` needs a typed
`Organization` (the Skill's upgrade path from a generic `Agent`). The note
says "SPDX 3.0.1" and must be bumped when output moves to 3.1.

**Known caveats, kept.**

- A whitespace-only part counts toward the 16016 bound, so `"A, " * 16015 +
  "Z, "` warns although nothing real is lost (pinned by a test).
- A fragment merge appends a merged `parameters` entry unsorted
  (the keyed-merge behaviour that predates this item); a base entry still
  wins.
- A merge adds the count note whenever a `parameters` entry that reads as a
  count (positive decimal digits within the cap, `is_parameter_count_text`) is
  present, even one a model declared itself with no Pitloom count (the builder
  writes no note there). A free-text value (`7B`, from a `loom` SDK model or a
  Keras `config` scalar) gets none, so the note never sits beside a value it
  does not describe. Kept on purpose: the entry a `sbom-enrich` fragment adds
  from a model card cannot be told from a model's own, and must carry the
  note. A "note was in an input" rule (tried, then reverted) left that
  fragment-added count with no note. The rule lives in
  `_finish_parameter_count_note` in `_fragments_props.py`.

## Follow-ups

Open items live in the design docs, not here:
[g7-ai-sbom-coverage.md](../design/g7-ai-sbom-coverage.md#follow-ups-from-6)
lists them (the `loom` SDK under G7 #7, Hub identifier and PURL, the
`publishedBy` versus `originatedBy` divergence, `general.quantized_by`,
`context_length`, counts for the silent formats, the `Person` or
`Organization` upgrade path, same-name creator and originator Agents, ONNX
subgraph and `training_info` gaps, a non-UTF-8 `model_author`, the display
escape), and
[model-metadata-readers.md](../design/model-metadata-readers.md#parameter-count)
says what the stdlib readers must keep.
