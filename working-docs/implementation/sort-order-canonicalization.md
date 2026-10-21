---
Created: 2026-08-15
Last-Modified: 2026-10-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Sort-order canonicalization

See also: [roadmap.md](../design/roadmap.md) (Near-term -- "Sort-order
canonicalization", follow-up to [PR #178](https://github.com/bact/pitloom/pull/178)).

## Audit where element/entry sort order feeds hash or id construction

Audited every `sorted()`/`.sort()` call in the assemble/id-registry
path. Findings, made explicit in code rather than left as a roadmap
note: `_sorted_by_spdx_id()` (`src/pitloom/id_registry/_harvest.py`) is *not* canonical
-- it only orders `IdRegistry` bookkeeping, never hashed/serialized
SBOM content, and its docstring now says so. The genuinely load-bearing
one, formerly `_stable_key()` in
`src/pitloom/assemble/spdx3/_fragments_unify.py`, was renamed to
`_canonical_merge_key()` with a docstring explaining that its order
decides which duplicate element survives fragment unification --
changing it changes SBOM output content. `provenance.py`'s
`sorted()` calls feeding annotation `statement` arrays, and
`_document_files.py`'s `summary_entries.sort()`, are also canonical
(RFC 8785 canonicalizes JSON object-member order but not array order)
and are now commented as such at each site.

No behavior changed; `_sorted_by_spdx_id` vs `_canonical_merge_key`
intentionally stay separate helpers -- they sort different things for
different reasons and share no key strategy worth unifying.

## `@graph` element order

`Spdx3JsonExporter.to_json()` (`src/pitloom/export/spdx3_json.py`) sorts the
JSON-LD `@graph` after deduplicating CreationInfo blank nodes and named
elements, because `SHACLObjectSet` is unordered and RFC 8785 does not reorder
arrays. The key, `_graph_sort_key()`, has three levels:

1. A type tier (`_GRAPH_TYPE_PRIORITY`): `CreationInfo`, `SpdxDocument`, `Bom`,
   `software_Sbom`, then every other type.
2. The element's `spdxId` (or `@id`), lexicographically.
3. The element's RFC 8785 form, only to order conflicting duplicates that share
   a tier and an id.

The compact output is RFC 8785 canonical; `--pretty` writes the same order with
sorted keys and indentation. The standards analysis behind the choice is in
[architecture-overview-integration.md](../design/architecture-overview-integration.md).
