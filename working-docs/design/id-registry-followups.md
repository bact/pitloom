---
Created: 2026-09-29
Last-Modified: 2026-10-02
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
[diagnostics-logging-followups.md](diagnostics-logging-followups.md).

## Open

### A wheel member that cannot be read

- A wheel with an unreadable member is refused whole (wheel-identity PR). The
  alternative, keeping the file without a hash, needs the SBOM builder to emit
  a hashless `software_File`, the registry's (path, sha256) key to accept one,
  and the Merkle root to say what it covers; revisit with v3.
- `RECORD` and an embedded SBOM are read whole (no size cap), unlike
  `METADATA`; a zip-bomb member there still exhausts memory.
- `.WHL` (upper case) is a wheel to some surfaces and not to others, so the
  same file fails with a different error on each. Pick one rule.
- `core/_models_wheel_types.py` `is_dist_info_path` is a fourth "top-level
  `.dist-info`" predicate, and its docstring says "wheel's own": it matches
  any top-level `*.dist-info`. Fold it into
  `core/wheel_dist_info.top_level_dist_infos` or reword it.
- The `--allow-build` extractor (same module) also keeps its own
  warn-and-keep-last for a duplicate member name and skips any top-level
  `.dist-info`: a fourth selector rule, apart from `wheel_dist_info`'s. Harmless
  for a wheel Pitloom has just built; align it with the fold above.

### Wheel identity and archive reader follow-ups

- **sdist member order leaks into `File-N` ids.** The wheel reader sorts by
  install path; the sdist reader lists tar members in archive order. Confirmed:
  the same five files in reverse order gave `PKG-INFO` `File-2` in one SBOM
  and `File-7` in the other. Sort as `read_wheel` does.
- **The sentinel `unknown` becomes a registry key.** Distinct wheels whose
  identity is unknown share `unknown-...#Package-1`. Skip the registry lookup
  and harvest when the name did not come from `METADATA`.
- **Case-insensitive collisions.** `.DIST-INFO`, `Metadata` and `record`
  variants overwrite the real files on a macOS or Windows install and are
  separate members to Pitloom. The same for a trailing dot, `name::$DATA`
  (NTFS alternate data stream) and reserved device names. Decide one
  portable-name rule for wheel members.
- **Embed copies non-conforming names as `info.filename`.** A member outside
  the own `.dist-info`, such as `pkg\mod.py`, is rewritten under the name
  `zipfile` gives on the running OS, so the embedded wheel differs by OS.
- **Default SBOM file name:** switch embed, the Hatchling hook and `loom
  project` default output to PEP 427 escaped `<name>-<version>` together, own
  PR after #266 (user 2026-10-02). Include the Windows-invalid characters
  `*?"<>|`, which the default name does not escape yet.
- **Version parsing past the int-conversion limit.** `extract/lock/_common.py`
  (about lines 276, 321, 411) parses with `Version()`; a lock-file version with
  a component of over 4300 digits raises a plain `ValueError`, not
  `InvalidVersion`. The wheel readers catch `ValueError` since #266.
  `extract/scanner_wheel.py` (about line 286) opens `ZipFile` directly:
  harmless, as `read_wheel` refuses a wheel first.
- **The `--allow-build` extractor has no duplicate refusal**, and members
  differing only in case overwrite each other in its extraction directory.

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
