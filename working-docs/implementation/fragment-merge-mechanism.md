---
Created: 2026-09-17
Last-Modified: 2026-10-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Fragment merge mechanism (what actually shipped)

See also: [roadmap.md](../design/roadmap.md) (Near-term -- "SBOM
fragments (merge system)"),
[fragment-merge-design.md](../design/sbom-fragments/fragment-merge-design.md)
(the original, mostly-superseded design this documents the shipped
version of -- read this file, not that one, for current behaviour),
[fragment-merge-unification.md](fragment-merge-unification.md) (references
by id, licence unification, the `loom merge` envelope).

Split out of `roadmap.md` (2026-09-17) once this item's detail grew
past a summary.

## Core merge mechanism

`merge_fragments()` (`src/pitloom/assemble/spdx3/fragments.py`) already
does more than the original design cluster's "Phase 1 item 2"
(`merge_fragments` rewrite) asked for -- that item is substantially
superseded by what's actually here:

- Pre-merge validation and duplicate-ID detection via `_MergeIndex`.
- Dangling-reference detection (`_raise_on_dangling_references()`),
  raising `FragmentMergeError` when the merged graph is left
  referentially broken.
- Unification annotations (`_emit_unification_annotations()`) -- one
  `unification` Annotation per (survivor element, unification
  criterion), recording which fragments were folded into which
  survivor and by what matching rule (same `spdxId`, content hash, or
  structural equality).
- Fragment-import tracking (`_add_fragment_imports()`) -- populates
  `SpdxDocument.import_` with an `ExternalMap` per merged fragment
  document, giving document-level traceability of which fragment files
  contributed.

Also already shipped, matching the original design cluster's Phase 4
item 2 exactly: `loom fragment validate` calls
`spdx3_validate.validate()`'s library API directly
(`cli/commands/fragment.py`), not by shelling out to a CLI and parsing
stdout.

## `FragmentConfig`, `loom fragment list`, `required=True` (PR #217)

Shipped 2026-09-18: `PitloomConfig.fragments` is `list[FragmentConfig]`
(`role`/`description`/`required`/`sha256`/`link-to-main`,
`core/_config_types.py`/`core/_config_parse.py`), backward-compatible
with a plain-string `files` entry; `loom fragment list`
(`cli/commands/fragment.py`) surfaces each configured fragment's
existence, `@graph` element count, and SHA-256 match status on one
`KEY=VALUE` line per fragment (several key-value pairs on one line is
correct here -- they describe one fragment, one data point; see
CLAUDE.md's "CLI output" section); `required=True` now makes
`merge_fragments()` raise `FragmentMergeError` for a missing/unreadable
fragment instead of only warning.

This PR went through five `/code-review` rounds (an unusually long tail
for a small feature) because the new code kept surfacing genuine,
non-obvious bugs -- see
[recurring-bug-patterns.md](recurring-bug-patterns.md) for the detailed
war stories (bare `Path.exists()` crashing on `PermissionError`, a
Windows errno/winerror classification bug introduced by one round's own
fix and only caught by the next, the same UTF-8-BOM `json.loads` bug
shipping twice independently in one PR, an unguarded `len()` on
untrusted JSON). One round also produced a false-positive "fix" --
reformatting `fragment list`'s output to one field per line, misreading
CLAUDE.md's "one data point per line" rule as "one field per line"
rather than "one record per line" -- caught and reverted by the user,
who then had CLAUDE.md's own wording clarified so the same
misreading doesn't recur.

Known, deliberately deferred gaps (not bugs, tracked in
[roadmap.md](../design/roadmap.md#to-design)): the two
per-fragment read/parse paths (`fragment list`'s own vs.
`merge_fragments()`'s own) are independently written and could drift;
`merge_fragments()`'s required-fragment check intentionally short-circuits
before the dangling-reference check (root-cause-first); `FragmentMergeError`
propagates uncaught from the Hatchling build hook (matches existing
precedent there); `KEY=VALUE` CLI output has no quoting for values
containing spaces (pre-existing, shared by every such line in the
codebase, not introduced here).

## Reading the code vs. this doc

This document summarizes shape and intent. For exact current behavior
(which properties are merged vs. skipped, the unification priority
order, error conditions), read `fragments.py` and
`_fragments_unify.py` directly -- this doc is not kept in lockstep with
every subsequent change to those modules.
