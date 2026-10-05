---
Created: 2026-10-04
Last-Modified: 2026-10-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Fragment merge: references by id, licence unification, the merge envelope

See also: [fragment-merge-mechanism.md](fragment-merge-mechanism.md) (the
merge as first shipped),
[open-items.md](../design/sbom-fragments/open-items.md) (what is still
open), [license-typing.md](license-typing.md) (the licence key a build
dedupes by).

Five bugs found in the PR #276 review, fixed in one PR before 0.20.0. The
bar: the same value on every surface that merges (a project build with
`[tool.pitloom.fragment]` through the library, `loom project`, `loom
embed-wheel --project-dir` and the Hatchling hook; `loom merge`), no
crash, valid deterministic output.

## References compare by id (`_fragments_unify.py`)

A deserialised fragment links its own references as objects; the base
document holds id strings. The old merge compared the two forms and lost:
`_merge_list` appended a fragment's `software_File` object to a base
`Relationship.to` that already held its id, the serialiser wrote that
object again, and `_check_no_duplicate_spdx_ids` raised
(`Duplicate spdxId ...#File-2`) on the first rebuild with an earlier SBOM
of the same project as a fragment. The same mismatch printed false
`conflicting` warnings and doubled `Hash` entries.

`_merge_fragment_set` now runs in two passes. First every element gets a
survivor (by id, licence key, SHA-256, then structure). Then every element
reference of every fragment element, nested blank nodes (`CreationInfo`,
`DictionaryEntry`) included, becomes the survivor's id string
(`_to_id_refs`), before any fields are folded. `_normalize_value` keys an
element by its id whichever form it has, so `_merge_list` and
`_merge_scalar` compare one key per item: id for an element or a string,
content for an object with no id, the value otherwise.

Rejected: rewriting only top-level properties of the kept elements (the
old `_remap_object_refs`, keyed by object): it misses the duplicates
being folded and the nested `CreationInfo.createdBy`, which kept stray
copies of dropped agents.

## A fragment that is the document itself (`fragments.py`)

Its `SpdxDocument` id equals the document being merged into: skipped with
one `WARNING:` naming it, as a missing or unreadable fragment is, and a
`FragmentMergeError` when `required`. `_load_fragment` holds the three
skip reasons; the message is `_same_document_message`. Rejected: refusing
always (a stale entry in `[tool.pitloom.fragment]` would break every
build), and unifying by id with the base winning (works after the fix
above, but warns on every Annotation `statement` and imports the
document into itself).

`loom fragment list` applies the same rule with the same message: a
fragment whose `SpdxDocument` id is `project_document_id()` (the id a
`loom project` build would mint, via `_doc_identity_of`) prints
`SAME_DOCUMENT=true` and fails the listing when required. The id is
resolved lazily, once, only for a fragment that has an `SpdxDocument`:
it reads the project's metadata and walks its files. A Hatchling-hook
build can mint a different id; the listing predicts `loom project`.

## Licence unification (`_fragments_licenses.py`)

Key: `license_key()` in `_license_elements.py`, the `(kind, value)` a
build indexes by -- an expression in canonical form (`classify_license`,
`warn=False`), a classifier `AND` as written, a text stripped. A drift
test checks it against every key a build writes. The base wins (the
exporter's own index is the seed), then configuration order (`loom
merge`: file name), then id order within a fragment (a per-fragment
pending map). Kept fragment licences go into the same index through
`add_license(key=)`. References, `customIdToUri` values included, follow
the id map, so a classifier `AND` points at the surviving texts. A
`license` unification Annotation records each drop.

Decided: the dropped element's `name`/`comment` are not folded into the
kept one. A licence element is shared by everything that uses it, and the
`sbom-enrich` override example would otherwise put "Overrides: ..." on a
shared `MIT`. Rejected: an exact-string key (`mit` and `MIT` stay two,
unlike a build).

## `loom merge` envelope (`_fragments_envelope.py`, `_generators_merge.py`)

`loom merge` started from an empty exporter, so the post-merge steps
(`profileConformance`, imports, unification Annotations, the model
`Sbom`) never ran. `generate_merged_sbom()` (public, `configure_logging`
first, called by the CLI) now builds the envelope before merging:

- id `generate_spdx_id("SpdxDocument", "merged", uuid5(PITLOOM_NS,
  each fragment's relative POSIX name with its SHA-256, sorted by
  name))`: independent of the directory and of the order the files were
  written; the names count because they decide which equal element
  survives, and so the roots and `locationHint`s; counters cleared first;
- creation info from `build_creation_info` (the Pitloom agent and tool);
- `created`: `SOURCE_DATE_EPOCH`, else the latest `created` among the
  merged elements' creation infos, else 1970-01-01 with one `WARNING:` --
  never the current time;
- `rootElement`: what the fragments' own `SpdxDocument`/`Sbom` envelopes
  rooted (through the id map, envelopes left out), plus the model `Sbom`,
  sorted. `merge_fragments(adopt_fragment_roots=True)` sets them before
  its dangling-reference check, which covers every collection's
  `rootElement`: a root outside the output (also one the fragment only
  imported; its imports are not carried over) fails as any dangling
  reference does. A project keeps its own roots, checked the same way;
- `profileConformance`: the profiles the graph uses plus every merged
  fragment envelope's declared ones, in `_profile_rank` order -- the same
  post-merge step for a project.

Fragment files are read in file-name order (`fragment_files()`, sorted by
name string, not by `Path`, which folds case on Windows). Rejected:
staying envelope-free and documenting it -- imports and annotations would
silently differ from a project build.

## Messages name elements by id (`export/spdx3_describe.py`)

One formatter: `Type <spdxId> 'name'`; an object with no id as its type
and sorted non-empty values; a string as its repr. Used by the merge
warnings, `require_spdx_id` and the duplicate-id error. In a module of its
own because `spdx3_json.py` is near the size limit.

## `scripts/check_sbom_license.py`

The root package is the root of the one `software_Sbom` whose single
`rootElement` is a `software_Package`; an `Sbom` rooted at an AI model
(every project with a model has one) is ignored, and zero or two such
`Sbom`s is an error. Rejected: a `--name` flag (changes two workflows),
and checking every `Sbom` (a model's licence may differ).
