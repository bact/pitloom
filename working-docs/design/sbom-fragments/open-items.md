---
Created: 2026-09-28
Last-Modified: 2026-10-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM fragments: current status and open items

See also [README.md](README.md) (index),
[fragment-merge-design.md](fragment-merge-design.md),
[loom-sdk-and-notebooks.md](loom-sdk-and-notebooks.md) (Phase 2),
[extractor-integrations.md](extractor-integrations.md) (Phase 3),
[roadmap-and-resources.md](roadmap-and-resources.md) (Phase 4 and the
original phased plan). Trimmed out of `roadmap.md`'s own "SBOM fragments
(merge system)" bullet (2026-09-28) per that file's own size rule --
re-verified against current code before listing below, since parts of
the original Phase 1/4 plan turned out to already be built.

## Already shipped

- **Core merge mechanism and `loom fragment validate`** -- both already
  ship, substantially superseding the original design cluster's Phase
  1/4 plan. See
  [fragment-merge-mechanism.md](../../implementation/fragment-merge-mechanism.md).
- **`FragmentConfig` dataclass** -- `PitloomConfig.fragments` is
  `list[FragmentConfig]` (`role`/`description`/`required`/`sha256`/
  `link-to-main`), backward-compatible with a plain-string loader
  (`core/_config_types.py`, `core/_config_parse.py`).
- **`loom fragment list`** -- surfaces per-fragment status (existence,
  `@graph` element count, SHA-256 match) to developers
  (`cli/commands/fragment.py`).

## Open

- [ ] **Skill trigger coverage for `loom merge` and `loom fragment
  list`** -- flagged during a 2026-09-18 skills-coverage audit: neither
  has a trigger phrasing or dedicated workflow in any `skills/*/SKILL.md`
  (`loom merge` appears only as one bash example line in
  `sbom-generate`). Needs design: `sbom-enrich` already covers the
  fragment-registration-and-regenerate path end to end, so this is about
  whether standalone `loom merge`/`loom fragment list` requests (outside
  that flow) warrant their own trigger phrasings, and if so, in which
  skill. See
  [skills-trigger-coverage.md](../../implementation/skills-trigger-coverage.md).
- [ ] **`loom fragment sign` + SHA-256 verification in merge** --
  genuinely open; the SHA-256 hashing that already exists in
  `_fragments_unify.py` is for same-identity element dedup, not
  fragment-file integrity/tamper checking. `FragmentConfig.sha256` is
  currently display-only (`fragment list`), not enforced before merge.
- [ ] **Fragment-parse-path consolidation** -- `fragment list`'s
  per-fragment read/parse (`_fragment_read_status` in
  `cli/commands/fragment.py`) and `merge_fragments()`'s own read/parse
  (`assemble/spdx3/fragments.py`) are two independently-written code
  paths doing the same "open, JSON-parse, SPDX3-deserialize" job --
  `fragment list` calls `JSONLDDeserializer().deserialize_data()` on
  pre-parsed JSON (to avoid re-parsing bytes it already parsed for the
  SHA-256/element-count checks), `merge_fragments()` calls
  `JSONLDDeserializer().read()` directly on an open file handle. They
  agree today, but nothing keeps them in sync if either the deserializer
  library or one call site changes independently. A shared
  "read+parse+deserialize a fragment, return raw bytes and the SPDX3
  object set" helper would close this; deferred since it isn't a live
  bug and reworking it risks reintroducing the double-JSON-parse
  inefficiency the current split was built to avoid.
- [ ] **`merge_fragments()`'s required-fragment check short-circuits the
  dangling-reference check** -- a missing/unreadable `required=True`
  fragment raises `FragmentMergeError` before
  `_raise_on_dangling_references()` ever runs, even when other,
  successfully-merged fragments introduced a genuine, independent
  dangling reference. Deliberate today (root-cause-first: a missing
  required fragment is usually the cause of downstream dangling refs,
  per the comment in `merge_fragments()`), but means a build with both
  problems only ever reports one per run -- revisit if that turns out to
  cost real debugging time in practice.
- [ ] **`FragmentMergeError` propagates uncaught from the Hatchling build
  hook** -- `required=True` enforcement makes this reachable far more
  often than before (previously only the dangling-reference check could
  raise it from `plugins/hatch.py`'s `initialize()`, which has no
  `try/except` around `merge_fragments()`). A user hits a raw Python
  traceback through Hatchling's hook machinery instead of a clean
  message, unlike the CLI (`cli_error_handler`-wrapped `ERROR:` line).
  Matches existing precedent (`ValueError`/`RuntimeError` from config
  validation already propagate uncaught there the same way), so not a
  regression, but worth a dedicated `try/except FragmentMergeError` with
  a clean message if it turns out to bite users in practice.
- [ ] **`KEY=VALUE` CLI output has no quoting/escaping for values
  containing spaces** -- `pitloom fragment list`'s one-line-per-fragment
  output (`PATH=... ROLE=... REQUIRED=...`) space-separates its fields,
  so a fragment `path` containing a space (legal on all three supported
  platforms) breaks naive whitespace-based field splitting downstream
  (`awk '{print $1}'`-style consumers). Pre-existing risk, not introduced
  by this PR -- shared by every other space-separated `KEY=VALUE` line in
  the codebase (e.g. `scanner.py`'s `FORMAT=%s FILE=%s`). No quoting
  convention defined yet; pick one (shell-style quoting, JSON Lines
  output mode, etc.) if/when a real path-with-spaces bug report lands.
- [ ] **SDK ergonomics (Phase 2)** -- `log_param`/`log_metric`/`log_tag`
  on `_ActiveRun`, a fluent `add_dataset` builder, `log_evaluation`,
  persistent `loom.start_session()`/`end_session()`, an optional
  `%%pitloom_record` IPython cell magic. See
  [loom-sdk-and-notebooks.md](loom-sdk-and-notebooks.md).
- [ ] **New extractors (Phase 3)** -- W&B Weave and DVC extractors, plus
  an MLflow dataset-input addition once the base MLflow extractor (see
  `roadmap.md`'s "Extractors" bullet) exists. See
  [extractor-integrations.md](extractor-integrations.md).
- [ ] **Compliance/interop (Phase 4)** -- CycloneDX BOM-Link emission
  (blocked on the CycloneDX assembler under `roadmap.md`'s Medium-term
  section) and a fragment `completeness` field
  (`complete`/`incomplete`/`unknown`) mapped to an SPDX `Annotation`.
  See [roadmap-and-resources.md](roadmap-and-resources.md).
- [ ] **Element-level fragment-merge traceability** -- document-level
  traceability (which fragment *files* contributed) shipped in
  [PR #108](https://github.com/bact/pitloom/pull/108); which
  *unification criterion* matched (same `spdxId` vs. content hash vs.
  structural equality) and which fragments a merged element's
  properties came from is not recorded in the output, only in a
  `log.warning`. Not planned to change without a native SPDX
  field-provenance construct -- see
  [roadmap-and-resources.md](roadmap-and-resources.md) for the full note.

### Found in the PR #276 review (own PR before 0.20.0)

- Licences are not unified across a fragment merge or `loom merge`: a
  fragment's `MIT` and the project's `MIT` stay two elements
  (`_MergeIndex` in `_fragments_unify.py` unifies by id, sha256 or
  structure, never by licence (kind, value)).
- `loom merge` output has no `SpdxDocument`, so no `profileConformance`.
- A project's own earlier SBOM registered as a fragment crashes the run
  (`Duplicate spdxId ...#File-2`).
- Merge warnings print object reprs (`<...software_Package object at
  0x...>`), so stderr differs between runs.
- `scripts/check_sbom_license.py` expects exactly one `software_Sbom`; a
  project SBOM with an AI model has two.
