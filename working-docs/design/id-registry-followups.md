---
Created: 2026-09-29
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry and id-stability follow-ups

Open items left by the explicit-ID-registry work (PR #235), the earlier
id-stability work (PR #178), and items the registry v3 design leaves
open on purpose. The roadmap
([roadmap-backlog.md](roadmap-backlog.md)) keeps a one-to-two-line bullet
for each and links here.

See also: [id-registry-v3.md](../implementation/id-registry-v3.md) (the built redesign;
D-numbers below refer to it),
[id-registry-v3-rollout.md](../implementation/id-registry-v3-rollout.md),
[ai-model-id-stability.md](ai-model-id-stability.md),
[id-registry-autosync.md](../implementation/id-registry-autosync.md),
[skills-trigger-coverage.md](../implementation/skills-trigger-coverage.md),
[diagnostics-logging-followups.md](diagnostics-logging-followups.md),
[canonical-output-followups.md](canonical-output-followups.md) (name
comparison and normalisation that registry keys depend on),
[id-registry-path-keys.md](../implementation/id-registry-path-keys.md) (the
built path-key redesign; K-numbers refer to it),
[id-registry-followups-v3-review.md](id-registry-followups-v3-review.md),
[id-registry-followups-path-keys.md](id-registry-followups-path-keys.md).

## Open

### Wheel identity and archive readers

Left open by the wheel-identity work (#266). Reading limits and refusals:

- **A wheel with an unreadable member is refused whole.** The alternative,
  keeping the file without a hash, needs the SBOM builder to emit a hashless
  `software_File`, the registry's (path, sha256) key to accept one, and the
  Merkle root to say what it covers; revisit with v3.
- **`RECORD` and an embedded SBOM are read whole** (no size cap, unlike
  `METADATA`); a zip-bomb member there still exhausts memory.
- **Version parsing past the int-conversion limit.** `extract/lock/common.py`
   parses with `Version()`; a lock-file version with
  a component of over 4300 digits raises a plain `ValueError`, not
  `InvalidVersion`. The wheel readers catch `ValueError` since #266.
  `extract/scanner_wheel.py`  opens `ZipFile` directly:
  harmless, as `read_wheel` refuses a wheel first.

Selection and naming rules:

- **`.WHL` (upper case)**: fixed by #278
  ([known-bugs.md](../implementation/roadmap-completed.md#bugs-fixed-in-0200)).
- **`core/_models_wheel_types.py` `is_dist_info_path`** is one more
  "top-level `.dist-info`" predicate beside those of `core/wheel_dist_info`,
  and its docstring says "wheel's own": it matches any top-level
  `*.dist-info`. Fold it into `wheel_dist_info.top_level_dist_infos` or
  reword it.
- **The `--allow-build` extractor (same module) has its own selection
  rules**: warn-and-keep-last for a duplicate member name instead of a
  refusal, any top-level `.dist-info` skipped, and members differing only in
  case overwrite each other in its extraction directory. Harmless for a wheel
  Pitloom has just built; align it with `wheel_dist_info` and the fold above.
- **Case-insensitive collisions.** `.DIST-INFO`, `Metadata` and `record`
  variants overwrite the real files on a macOS or Windows install and are
  separate members to Pitloom. The same for a trailing dot, `name::$DATA`
  (NTFS alternate data stream) and reserved device names. Decide one
  portable-name rule for wheel members.

Ids, names and output:

- **sdist member order leaked into `File-N` ids**: fixed by #272
  ([known-bugs.md](../implementation/roadmap-completed.md#bugs-fixed-in-0200)).
- ~~**The sentinel `unknown` becomes a registry key.**~~ Resolved
  2026-10-15 for wheels: `identity_known` is `False`, the package is not looked
  up or recorded, one `INFO:`, and the base file name seeds the document uuid.
  Embed routes (standalone, `--project-dir`) share the helper
  `wheel_document_identity()`, the `INFO:` once per batch. Still open: the
  sdist placeholders (two sdists with PKG-INFO lacking `Name` share a doc uuid
  and reuse a pinned `unknown` id)
  (`extract/project/sdist.py` `Name` default `unknown`, `_sdist_pyproject.py`;
  `_parse_pkg_info` sets `provenance['name']` even when absent) are unfixed.
- **Default SBOM file name:** switch embed, the Hatchling hook and `loom
  project` default output to PEP 427 escaped `<name>-<version>` together, own
  PR after #266 (user 2026-10-02). Include the Windows-invalid characters
  `*?"<>|`, which the default name does not escape yet.
- **The embed copies a non-conforming member name as `info.filename`**, so the
  embedded wheel differs by OS: see
  [archive-member-followups.md](archive-member-followups.md) section 2.

### Wheel/sdist targets and src-layout registry file ids

Closed by the path-key work (K1-K3, K15): see
[id-registry-path-keys.md](../implementation/id-registry-path-keys.md).
Layouts other than `src/` and `lib/` and a plain `wheel` in a monorepo are
open ([id-registry-followups-path-keys.md](id-registry-followups-path-keys.md)).

### Harvest rewrites per-document entities; `env` root is never looked up

Found in PR A2 (#235) while making package ids registry-driven:
`SoftwareAgent`/`Tool`/`License` entries carry each document's own uuid,
so alternating `project`/`wheel` runs still change the registry's bytes
(package entries are stable); `env`'s root `deployed-environment` package
is always minted, and a pinned id for it is overwritten on harvest. See
[id-registry-autosync.md](../implementation/id-registry-autosync.md).
Not changed by v3. Auto-harvest also records the `SoftwareAgent`/`Tool`
'Pitloom' under per-document ids, so project/wheel alternation in the
`src/` layout still rewrites the registry (`updated stale entries`). Fix
idea: limit `_harvestable` in `assemble/_generators_shared.py` to the four
registry types, or mark agents and tools as non-readers.

### AIPackage lookups outside loom stay ungated until G7 #3

Closed by the path-key work: every model lookup is gated by the model file's
SHA-256 and `ai_AIPackage.verifiedUsing` is emitted (G7 #3 part 1).

### Ignored-name quirks in `id generate` indexing

Resolved by registry v3 (checked in `id_registry/_types.py`): the check
matches the project-relative parent directories only, so a project under an
ancestor `build/` is indexed and a *file* named `build` is eligible. An
explicit PATH inside an ignored directory (`loom id generate build/x`) indexes
nothing and warns once (`path has a skipped directory name`; 2026-10-15).

### Message codes after catalogue PR 5 (#485)

- A missing explicit `loom id generate` PATH is an `ERROR:`
  (`input-not-found`, kind `PATH`), exit 1, nothing written; a default root
  that is absent stays quiet; a file gone below a listed PATH is left out.
- ~~`registry-unusable` (a project root the file cannot record) is not
  printed on the CLI: `failed_to_save_message` relays the inner text without
  its code.~~ Catalogue PR 7: the wrapper is gone; a failed save says its
  own coded line (`say_save_failure`).
- ~~The skipped-directory `WARNING:` stays uncoded until PR 6.~~ Coded
  `index-path-no-effect` in #486.
- A partly indexed registry on a library raise: a missing or unreadable
  PATH raises during the walk, before anything is registered, so the
  `IdRegistry` object is unchanged (pinned by
  `test_generate_raises_for_a_path_that_is_not_there`, a good PATH first).
  A raise from `register()` inside the later loop would leave the files
  before it registered; names are checked during the walk, so none is known
  to reach it. Open: make the loop all-or-nothing, or document it.
- `FILE=` after `ID registry: ` names an indexed file, not the registry
  file, in two lines (`not inside the project root`, option-invalid; the
  file name that cannot be encoded, `text-malformed/registry`): a grep for
  `ID registry: FILE=` cannot tell them from the registry file's own lines.
  Resolved in #486 (ruling Q2): an indexed file is `PATH '<p>'`; `FILE=`
  after the prefix is only the registry file.
- The build hook never saves the registry (`plugins/hatch.py` calls
  `resolve_registry` and `assemble_spdx3`, never `persist_registry`), yet
  PR 5's `_DID` and `REGISTRY_UNUSABLE.did` say it re-reads the file to
  save. Rewritten in catalogue PR 7.
- A mint refusal on a registry with no file names it `FILE=(no file)`
  (`registry-malformed`, #486): a sentinel, not a path. Open: a line
  without the subject for an in-memory registry.
- `loom id generate ""` (an empty PATH) is the project directory itself and
  indexes the whole project, silently. Open: refuse it, or say so.
- `loom id generate -e ...` logs the `INFO:` that an entity is stored by name
  before an `ERROR:` that then writes nothing (as on `main`). Catalogue PR 7
  moved `-e NAME stored as KEY` after the save; the coded decisions (`stored
  by name`, `pinned without SHA-256`, `stored without a version`) are still
  said before it. Open: hold those too.
- ~~`VERSION_LINE` says "delete it and re-run" for every version, a newer one
  included.~~ Catalogue PR 7 dropped the bracket; the advice is the entry's.
- ~~A save failure whose inner line has no `WARNING` twin prints uncoded.~~
  `credentials-unsafe/registry`'s "is not loaded" line (a run refusing
  credentials meets an entry another run saved with one) has its twin, and
  `say_save_failure` raises `InternalError` for any coded failure without
  one, so a future gap fails loudly instead of printing uncoded.
- `option-invalid` exits 2 for argparse's lines and 1 for the PATH-outside
  line: one code, two exit statuses, chosen by line. Open: document per line
  in the reference, or align.
- `shown_key` in `scripts/manual_cli_checks/_order_capture.py` reads a key
  that is literally a backslash and `n` as a newline: `loggable()` writes a
  real newline as that same text, so the printed line itself is ambiguous.
  Harness only (it may pair the wrong key in an order check); the output
  cannot tell the two apart either. Open: a distinct escape for a literal
  backslash in a key, or accept and document.
- Credentials in a URL that is otherwise valid are still accepted and baked
  into ids: a namespace (a document id adopted on import, `loom id generate
  --namespace`) into every minted `spdxId`, a `-e NAME` key (a dataset URL)
  into the registry and the id minted from it. #486 only masks them in
  messages. Owned by the credential-leaks PR: refuse them.

### Merge by id: same-type coincidences and re-minted ids

v3's D11 stops a fragment element from folding into an element of
another type. Resolved 2026-10-15: the same id and type with a conflicting
SHA-256 (same algorithm, disjoint digests) also stays apart, the later element
getting a new id and a `WARNING:` (`assemble/spdx3/_fragments_ids.py`). Still
open: a same-type id coincidence with no digest on either side still merges
(the "Found, not fixed" item in
[id-registry-autosync.md](../implementation/id-registry-autosync.md#found-not-fixed)),
and a re-minted id can in theory collide with a *later* fragment that carries
the same id (for example `<ns>#DatasetPackage-1` re-declared by a later
fragment and not in the base; all fragments load before the first merge, so a
pre-scan is possible). Accepted for now.

### Dataset identity: name and version

Ruled 2026-11-23 (option B of the #509 question): make `(name, version)`
the identity of a dataset everywhere, not yet built; the registry key
change needs the user's go-ahead first. Today only the GGUF reader keys a
dataset by name and version (`core.dataset_names.dataset_identity`,
`distinct_datasets`, #509). Everything after it keys by name alone
(`dataset_key`), so two releases of one dataset become one package:

- `core.dataset_merge.merge_dataset_references` folds every reference by
  name; a second version is dropped with `WARNING: FIELD=version ...`.
- ID registry keys: `(dataset_DatasetPackage, name)` in
  `_loom_dataset.py`, `id_registry/import_keys.py` and
  `assemble/spdx3/_reserved_ids.model_dataset_keys`; two packages of one
  name would share one key, so one id. A registry key change.
- The README enricher (`enrich/readme.py`) and the Hub card route
  (`extract/remote/huggingface_field.py`, `huggingface_dataset.py`) dedupe
  by `dataset_key`; a card states no version, so only the rule below
  matters there.
- `dataset_creation_info` in `assemble/spdx3/dataset.py` maps a name to
  its enrichment `CreationInfo`.

Open question: does a reference with no version join a versioned one (the
card's `allenai/c4` and a GGUF's `allenai/c4` 2.0)? Joining is not
transitive (`d`, `d` 1, `d` 2: which does `d` join?). The GGUF reader's
answer, for its own array only: an element is another spelling of the first
numbered entry of its name.

### `pitloom.loom` run namespaces

Moved from [canonical-output-followups.md](canonical-output-followups.md)
(an id-scheme question). One run mints ids under several `doc_name`s --
the model name, each dataset name, the script path and `"loom"` -- with a
random `uuid4` document uuid, so one fragment spans several namespaces and
differs every run. Found while fixing the IRI encoding (#253); see
[id-registry-autosync.md](../implementation/id-registry-autosync.md) for
why reservation is a no-op there.

Items found by the last three reviewers of the registry v3 round are in
[id-registry-followups-v3-review.md](id-registry-followups-v3-review.md).

## Registry v3: follow-ups (2026-10-15)

Moved to [id-registry-followups-v3-review.md](id-registry-followups-v3-review.md#registry-v3-follow-ups-2026-10-15):
security and edge cases, order-matrix findings, PR #305 review findings,
design questions, tooling.

## Resolved by registry v3

Kept here so older links still land. Each item below was checked against
the v3 code on 2026-10-15.

### The in-tree registry exclusion covers build-and-read files

Found in v3 (D7), fixed in the finalisation round: a `--allow-build`
discovered file's path points into a temporary extraction directory, so the
exclusion also matches a build-and-read copy by the registry's
project-relative path (or a tail of it, for a `src/` layout) plus an equal
sha256 (`_DeclaredRegistry` in `core/_models_wheel.py`). The `--allow-build`
id-registry gap in [roadmap.md](roadmap.md) is a separate item.

### A write-protected registry is not overwritten

The atomic temp-file write would replace a read-only (`chmod 444`) registry
on POSIX, where the old in-place save failed. Decided 2026-10-15: it is not
overwritten on any platform; the save fails with the failed-to-save
`WARNING:`/`ERROR:` as before.

### Skill trigger coverage for `loom id generate`/`loom id import`

Flagged in the 2026-09-18 skills-coverage audit: no skill `description`
triggered on the two commands. v3's commit 9 decides it: the agent runs
`loom id generate`/`import` itself when the user asks to pin ids, and
`sbom-generate`'s description gains id-management triggers. See
[skills-trigger-coverage.md](../implementation/skills-trigger-coverage.md).

### Deterministic same-model identification for auto-harvest

Decided in v3: a model's sha256 is a gate once recorded (D3), a retrained
model is a new model, and hashed `ai_AIPackage` elements are
auto-harvested (D15); unhashed ones stay excluded. See
[ai-model-id-stability.md](ai-model-id-stability.md).
Resolved by registry v3: harvest records a hashed `ai_AIPackage` with its
sha256 and never erases a recorded one (`id_registry/_harvest/`), so
`id import` no longer loses the hash. The ungated lookups elsewhere are a
separate, open hazard (below).

### A declared registry inside the package tree never settles

The registry file is itself a hashed project file, so with
`id-registry = "src/demo/reg.json"` every `project` run changes both the
SBOM and the registry bytes (`INFO: ... updated stale entries` each time;
seen at 6e83f41). v3's D7 (commit 2) excludes the resolved registry path
from file discovery and from `id generate`'s indexing (the latter is the
custom-name gap in
[diagnostics-logging-followups.md](diagnostics-logging-followups.md)),
with one `WARNING:`.
Resolved by registry v3: the declared registry is left out of project and
wheel discovery with one `WARNING:` (`core/walk_rules.py`,
`core/_models_wheel.py`) and out of `id generate` indexing
(`_iter_files(exclude=...)`); the latter skips it without a message (see
"Registry v3: follow-ups").

### Bounded `spdxId` minting for long or hostile names

Raised 2026-10-08 in #294 (model name cap). An `spdxId` embeds the element
name (`AIPackage-<name>-N`), so id size follows name size: a 1 MB model
name gave a 2 MB id. #294 caps a model name at 1024 characters with a
digest of the full name in the cut name, which keeps ids bounded (at most
about 12 KB per occurrence when percent-encoded) and keeps two distinct long names apart.
Fixed there, not here: that is the minimum that makes every identity path
(document uuid, minting prefix, enrich identity, registry key) agree.

Considered for the id scheme, not done in #294:

- An id segment that is a short slug (about 48 characters) plus a digest of
  the verbatim name, so id size no longer depends on the name and the
  display name can be a clean cut. The user's view: an `spdxId` need not
  contain the original name or id.
- It changes every existing id, so apply it to all name-based prefixes
  (`Package-`, `File-`, `Agent-`, `AIPackage-`), not to AI packages alone,
  and settle it with the v3 id design in one go.
- The registry harvest and the enrich identity read the SBOM's `name`, not
  the model file. Without the digest in the visible name, two names that
  cut to the same text still collide ("name held by several elements").
  Any new scheme must carry the identity in something the harvest can read
  (the id itself, or an identifier or property on the element).
- Identity comes from the verbatim name and the display form is derived
  (escaped, cut); the bidi lookup bug in #294 (registry stored the escaped
  name, minting looked up the raw one) is the same split.

See also: [id-registry-v3.md](../implementation/id-registry-v3.md),
[ai-model-id-stability.md](ai-model-id-stability.md); the name cap, its cut
layout and the open name-normalisation questions are in
[canonical-output-followups.md](canonical-output-followups.md).
