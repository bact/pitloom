---
Created: 2026-08-15
Last-Modified: 2026-08-15
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
note: `_sorted_by_spdx_id()` (`src/pitloom/ids.py`) is *not* canonical
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
