---
Created: 2026-09-30
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Names in SPDX identifiers: IRI segment encoding

See also: [canonical-output-followups.md](../design/canonical-output-followups.md)
(open name comparison and normalisation questions), `src/pitloom/core/iri.py`.

## Defect

A name went into an identifier unchanged: `AIPackage-{name}` in
`_ai_package.py`/`_document_model.py`, `Agent-{creator}` in `dataset.py`,
the `pitloom.loom` run's `doc_name` (model, dataset or script path), the
document namespace `spdxdocs/{doc_name}-{uuid}`, and `IdRegistry.new()`'s
namespace. A Safetensors `modelspec.title = "Stable Diffusion XL"` (or the
file name `my model.npy` of a model with no name, which becomes `doc_name`) gave
an IRI with a space, which fails SHACL (`sh:nodeKind sh:IRI`) in
`spdx3-validate`.

## Fix: one helper, applied where every id is built

`pitloom.core.iri.iri_segment(name)` and `doc_namespace(doc_name, uuid)`.
`generate_spdx_id()` passes both its `prefix` and `doc_name` through them,
so every one of its ~37 call sites inherits the rule without an edit;
`reserve_spdx_ids()` and `IdRegistry.new()` build their namespace with the
same `doc_namespace()`. No call site encodes by itself. The element `name`
keeps the source text.

## Rule: percent-encode what is not RFC 3987 `ipchar`, and `%`

Kept as is: ASCII letters and digits, `-._~`, sub-delims `!$&'()*+,;=`,
`:` and `@`, and every RFC 3987 `ucschar` (non-ASCII letters included; note
plane 14 starts at U+E1000, so tag characters and variation selectors
supplement are encoded) except the bidi formatting characters (U+200E, U+200F, U+202A to U+202E), which
section 4.1 forbids in an IRI. Everything else becomes its UTF-8 bytes,
percent-encoded in upper case (`%20`); a lone surrogate is encoded via
`surrogatepass`.

Why this rule:

- **Byte-identical for valid names.** A name made only of kept characters
  -- every PEP 503 package name, `llama-3.1_8B`, `Модель` -- gives the same
  id as before, so existing SBOMs and registries keep their ids.
- **Lossless, so no collisions.** `%` is always encoded (`a%20b` ->
  `a%2520b`), so decoding is the exact inverse and two different names never
  share an id segment. A slug (`a b` -> `a-b`) would merge `a b` with `a-b`
  and need a tie-break rule; this needs none.
- **One rule for both positions.** `/` and `?` are legal in an IRI fragment
  but split a path segment and start a query in the namespace; encoding them
  in both keeps one helper and one mental model. Consequence: a name with
  `/` (a GGUF `general.name` of `org/model`) now gets a different id than
  before. Accepted in private alpha.
- **Unicode kept, not NFC-normalised.** IRIs allow `ucschar`, and
  `spdx3-validate` accepts it. Normalising would break the lossless property
  (two source strings, one id) and change bytes of names that were valid.
- **No length cap.** Truncation would be lossy.

Not idempotent: the helper takes the raw name. `generate_spdx_id()` is the
only caller that applies it to a prefix, and every caller passes a raw name.

## ID registry interaction

- Entity keys stay names (`"Stable Diffusion XL"`); the stored `spdxId` is
  the encoded one. A lookup by name returns it as stored
  (`test_registry_round_trips_an_encoded_id`, via `pitloom.loom.run()`, whose
  fresh random document uuid means only a lookup can return the stored id).
- `loom model` looks its model up by file stem, not name, so an id imported
  from a titled model's SBOM is not reused there. Not caused by the encoding
  (same on the pre-fix code); tracked in
  [known-bugs.md](../design/known-bugs.md#p0-in-0210).
- `reserve_spdx_ids()` parses `<prefix>-<n>` out of a stored id, so its
  prefix is the encoded one. `generate_spdx_id()` keys its counter on the
  encoded prefix too, so a reservation and the next mint meet on the same
  key. Keying on the raw prefix would mint a duplicate `-1`.
- `IdRegistry._mint_id()` encodes its prefix too: it is a type name, but
  `loom id generate -e NAME:TYPE` accepts any TYPE (e.g. `My Type#1`).
- A registry written before this change with an unencoded namespace is not
  migrated (no backward compatibility yet); regenerate it.

## Tests

- `tests/core/test_iri.py`: the rule (space, `#`, `/`, `?`, `%`, control,
  bidi, surrogate), each `ucschar` range edge, valid names unchanged,
  injectivity, both namespace builders.
- `tests/core/test_models.py`: encoded prefix and namespace, and a reserved
  encoded id skipped by the next mint.
- `tests/assemble/test_name_iri_surfaces.py`: `loom model`, `loom project`
  and `pitloom.loom.run()` each emit valid IRIs and keep `name`; the
  registry round trip; and, marked `network`, `spdx3-validate` on each
  surface's output. All fail on the pre-fix code.

Mutation-tested: each range bound (plane 14's U+E1000 start included), the
bidi check, the registry lookup in the round trip, the `%` exclusion, the
upper-case hex, the namespace encoding, the prefix encoding and the registry
namespace -- every mutant killed.
