---
Created: 2026-09-29
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry and id-stability follow-ups

Open items left by the explicit-ID-registry work (PR #235), the earlier
id-stability work (PR #178), and items the registry v3 design leaves
open on purpose. [roadmap.md](roadmap.md) keeps a one-to-two-line bullet
for each and links here.

See also: [id-registry-v3.md](id-registry-v3.md) (the planned redesign;
D-numbers below refer to it),
[id-registry-v3-rollout.md](id-registry-v3-rollout.md),
[ai-model-id-stability.md](ai-model-id-stability.md),
[id-registry-autosync.md](../implementation/id-registry-autosync.md),
[skills-trigger-coverage.md](../implementation/skills-trigger-coverage.md),
[diagnostics-logging-followups.md](diagnostics-logging-followups.md),
[canonical-output-followups.md](canonical-output-followups.md) (name
comparison and normalisation that registry keys depend on).

## Open

### Wheel identity and archive readers

Left open by the wheel-identity work (#266). Reading limits and refusals:

- **A wheel with an unreadable member is refused whole.** The alternative,
  keeping the file without a hash, needs the SBOM builder to emit a hashless
  `software_File`, the registry's (path, sha256) key to accept one, and the
  Merkle root to say what it covers; revisit with v3.
- **`RECORD` and an embedded SBOM are read whole** (no size cap, unlike
  `METADATA`); a zip-bomb member there still exhausts memory.
- **Version parsing past the int-conversion limit.** `extract/lock/_common.py`
  (about lines 276, 321, 411) parses with `Version()`; a lock-file version with
  a component of over 4300 digits raises a plain `ValueError`, not
  `InvalidVersion`. The wheel readers catch `ValueError` since #266.
  `extract/scanner_wheel.py` (about line 286) opens `ZipFile` directly:
  harmless, as `read_wheel` refuses a wheel first.

Selection and naming rules:

- **`.WHL` (upper case)**: fixed by #278
  ([known-bugs.md](known-bugs.md#p0-in-0200)).
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
  ([known-bugs.md](known-bugs.md#p0-in-0200)).
- **The sentinel `unknown` becomes a registry key.** Distinct wheels whose
  identity is unknown share `unknown-...#Package-1`. Skip the registry lookup
  and harvest when the name did not come from `METADATA`.
- **Default SBOM file name:** switch embed, the Hatchling hook and `loom
  project` default output to PEP 427 escaped `<name>-<version>` together, own
  PR after #266 (user 2026-10-02). Include the Windows-invalid characters
  `*?"<>|`, which the default name does not escape yet.
- **The embed copies a non-conforming member name as `info.filename`**, so the
  embedded wheel differs by OS: see
  [archive-member-followups.md](archive-member-followups.md) section 2.

### Wheel/sdist targets and src-layout registry file ids

`loom id generate` keys files by project path (`src/demo/x.py`), while a
wheel's distribution path is `demo/x.py` and an sdist's is
`demo-1.0.0/src/...`. A `loom project` harvest writes a
distribution-path alias (`demo/x.py`) next to the `src/` entry, so a later
`wheel` run does reuse the id. The gap applies to a registry seeded by
`loom id generate` alone, which has no alias, and to an sdist target,
which finds neither key. v3 keeps the alias rule (I4) and does not close
this.

### Harvest rewrites per-document entities; `env` root is never looked up

Found in PR A2 (#235) while making package ids registry-driven:
`SoftwareAgent`/`Tool`/`License` entries carry each document's own uuid,
so alternating `project`/`wheel` runs still change the registry's bytes
(package entries are stable); `env`'s root `deployed-environment` package
is always minted, and a pinned id for it is overwritten on harvest. See
[id-registry-autosync.md](../implementation/id-registry-autosync.md).
Not changed by v3.

### AIPackage lookups outside loom stay ungated until G7 #3

v3 gates loom's model lookup by the `path=` file's sha256 (D13), but the
project, wheel, `loom model` and embed lookups stay ungated (D16): those
surfaces do not hash AIPackages before G7 #3. Until then a project SBOM
reuses a name-matched `ai_AIPackage` id even after the model is
retrained, while loom mints a new one. Gate them when G7 #3 lands, so
every surface agrees.

### Ignored-name quirks in `id generate` indexing

`_types._is_eligible_file` matches `_IGNORED_DIR_NAMES` against every
path part, the file name included, so a *file* literally named `build`
(or `dist`, ...) is never indexed; and an explicit PATH inside an ignored
directory (`loom id generate build/x`) is skipped silently. v3's commit 2
fixes only the absolute-path half of this check (it will match
project-relative parts) and keeps both quirks.

### The in-tree registry exclusion misses build-and-read files

v3 excludes the declared registry file from discovery by path (D7). With
`--allow-build`, a discovered file's path points into a temporary
extraction directory and never matches, so an in-tree registry is still
listed there. Related to the `--allow-build` id-registry gap in
[roadmap.md](roadmap.md).

### Merge by id: same-type coincidences and re-minted ids

v3's D11 stops a fragment element from folding into an element of
another type. Two gaps remain: a fragment-carried id that coincides with
an unrelated main-document element *of the same type* still merges (the
"Found, not fixed" item in
[id-registry-autosync.md](../implementation/id-registry-autosync.md#found-not-fixed));
and a re-minted id can in theory collide with a *later* fragment that
carries the same id. Accepted for now.

### `pitloom.loom` run namespaces

Moved from [canonical-output-followups.md](canonical-output-followups.md)
(an id-scheme question). One run mints ids under several `doc_name`s --
the model name, each dataset name, the script path and `"loom"` -- with a
random `uuid4` document uuid, so one fragment spans several namespaces and
differs every run. Found while fixing the IRI encoding (#253); see
[id-registry-autosync.md](../implementation/id-registry-autosync.md) for
why reservation is a no-op there.

## Resolved by registry v3 (planned, not built)

Kept here so older links still land; each closes when v3 merges.

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

### A declared registry inside the package tree never settles

The registry file is itself a hashed project file, so with
`id-registry = "src/demo/reg.json"` every `project` run changes both the
SBOM and the registry bytes (`INFO: ... updated stale entries` each time;
seen at 6e83f41). v3's D7 (commit 2) excludes the resolved registry path
from file discovery and from `id generate`'s indexing (the latter is the
custom-name gap in
[diagnostics-logging-followups.md](diagnostics-logging-followups.md)),
with one `WARNING:`.

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

See also: [id-registry-v3.md](id-registry-v3.md),
[ai-model-id-stability.md](ai-model-id-stability.md); the name cap, its cut
layout and the open name-normalisation questions are in
[canonical-output-followups.md](canonical-output-followups.md).
