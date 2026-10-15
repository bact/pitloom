---
Created: 2026-09-29
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry and id-stability follow-ups

Open items left by the explicit-ID-registry work (PR #235), the earlier
id-stability work (PR #178), and items the registry v3 design leaves
open on purpose. [roadmap.md](roadmap.md) keeps a one-to-two-line bullet
for each and links here.

See also: [id-registry-v3.md](../implementation/id-registry-v3.md) (the built redesign;
D-numbers below refer to it),
[id-registry-v3-rollout.md](../implementation/id-registry-v3-rollout.md),
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
this. The reverse order splits the ids too: `id generate` after a
`project` or `wheel` harvest mints a new id for the `src/` key beside the
distribution-path alias, and the next `project` run rewrites the alias
(found by the order matrix, `O1/src/fresh-cli`; accepted there under this
item).

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

Resolved by registry v3 (checked in `id_registry/_types.py`): the check
now matches the project-relative parent directories only, so a project
under an ancestor `build/` is indexed and a *file* named `build` is
eligible. Still open: an explicit PATH inside an ignored directory
(`loom id generate build/x`) is skipped without a message.

### Merge by id: same-type coincidences and re-minted ids

v3's D11 stops a fragment element from folding into an element of
another type. Two gaps remain: a fragment-carried id that coincides with
an unrelated main-document element *of the same type* still merges (the
"Found, not fixed" item in
[id-registry-autosync.md](../implementation/id-registry-autosync.md#found-not-fixed));
and a re-minted id can in theory collide with a *later* fragment that
carries the same id. Accepted for now.

Resolved by registry v3: the different-type fold (D11, in
`assemble/spdx3/_fragments_unify.py`). The same-type and later-fragment
gaps stay open; see "Registry v3: follow-ups" below.

### `pitloom.loom` run namespaces

Moved from [canonical-output-followups.md](canonical-output-followups.md)
(an id-scheme question). One run mints ids under several `doc_name`s --
the model name, each dataset name, the script path and `"loom"` -- with a
random `uuid4` document uuid, so one fragment spans several namespaces and
differs every run. Found while fixing the IRI encoding (#253); see
[id-registry-autosync.md](../implementation/id-registry-autosync.md) for
why reservation is a no-op there.

## Registry v3: follow-ups (2026-10-15)

Found while building and reviewing v3 (commits 0b to 7b). Facts were checked
by the implementers against the tree; code locations are given where an item
is easy to lose. D-numbers refer to [id-registry-v3.md](../implementation/id-registry-v3.md).

### G7 blockers (Day 2)

- **Retrains laundered into old ids (D15 against D16).** Once G7 #3 hashes
  the AIPackages of the project, wheel and embed surfaces, their ungated name
  lookups (D16) still return the old id after a retrain. Harvest then writes
  `(name, new sha)` under the OLD id, and a later gated `loom` lookup of the
  new bytes hits the old id. G7 #3 must gate those lookups in the same change,
  or D15 must be limited to elements that did a gated lookup.
- **Harvest keys a model by its extracted `.name`, `id generate` by the file
  stem.** When they differ, `_release_stale_keys_for_id` drops the stem key,
  because the src-layout alias rule (`_is_alias`) only accepts names that are
  path suffixes of each other. Extend the alias rule, or key the harvest by
  the lookup key, before G7 #3 makes names diverge more often.
- **Revisit `id import` sha drop after G7 #3** (project SBOMs will carry the
  AIPackage hash, so the imported element has its own sha). Ruling of
  2026-10-15, under "Found by the order matrix" below.

### Security and edge cases

Dataset hashing and paths:

- **Directory-dataset hashing has no file-count cap.** Millions of tiny files
  stay under the byte ceiling (`max-dataset-hash-bytes`) while the walk and
  the member list grow without bound: measured 88.8 MB peak for 200,000
  files, about 440 bytes per file. Add a count cap beside the byte one.
- **An output dataset is hashed when declared** (`add_output_dataset`), so
  one declared before the step wrote the file carries the hash of the file it
  replaces. Defer output-dataset hashing to run exit, as models are.
- **The same dataset declared twice is hashed twice.** Cache the digest per
  run, keyed on the real path.
- **`id generate` does not index files below a symlinked directory** (a file
  symlink is indexed), so a `loom.Run` keys such a path lexically and finds no
  entry. Documented in `docs/id-registry.md`; decide whether it is a gap.
- **A dataset member that vanishes between listing and hashing** warns
  `could not read`; a single vanished file is silent. Align the two.
- **Symlinked subdirectories of a directory dataset are not followed.**
  Documented in `docs/python-api.md`; decide whether it is a gap.
- **Case-insensitive file system.** A path matched by identity (`st_dev`,
  `st_ino`) keeps the caller's casing below the root, so the registry lookup
  misses. Normalise the tail to the on-disk case, or look up by identity.
- **`registry_key_for_path` is documented as never raising**
  (`id_registry/resolve.py`) but calls `os.getcwd()`, which raises
  `FileNotFoundError` when the current directory was deleted. Catch it.

Registry file I/O:

- **Windows: `os.replace` fails while another process has the registry
  open.** The save logs the failed-to-save `WARNING:` and the update is lost.
- **A killed process can leave `.<registry>.<hex>.tmp`** beside an in-tree
  registry, and a later scan would list it: D7 excludes by exact path only.
- **A registry replaced mid-run by a file with another namespace.**
  `rebase()` adopts the new namespace; ids already replayed keep the old one.

Loom:

- **`loom` never configured logging before 7b.** `loom.Run` now calls
  `configure_logging()`, which replaces handlers a user had set on the
  `pitloom` logger. Documented in `docs/python-api.md`; or add to the
  handlers instead.
- **A model declared twice under one name with different files:** the last
  declaration owns the entry.
- **`run.model` is `None` inside the `with` block** (resolved at exit, D13),
  so user code reading it there breaks. Document it or expose a provisional
  value.
- **Two truly simultaneous loom exits can write the same id for different
  models into their fragments.** The registry stays one key per id (the later
  save is refused, `WARNING: another run saved ... first`), but the fragment
  is already written, so the claim "a lost update is never a wrong id" was
  false for it (corrected in
  [id-registry-v3.md](../implementation/id-registry-v3.md) 8.4; documented in
  `docs/id-registry.md`). Fix idea: claim ids by rebase-and-save before
  writing the fragment.
- **Two model files with the same stem** (`a/m.gguf`, `b/m.gguf`) are
  registered name-only, with one `INFO:` per run.
- **A local dataset package is keyed by the caller's string**, as passed, by
  decision (2026-10-15): `../data/t.txt` from a subdirectory misses the
  package pin while its `software_File` hits. Documented.
- **A hashless `-e path:software_File` pin, then a regeneration,** logs
  `content changed` and mints a new id (the D12 trade-off). Consider adopting
  the hash on first sight for file pins.
- **Bootstrap from an empty registry** logs two `untracked file` `WARNING:`s,
  for the `data/processed/` files the pipeline creates later.
- **`IdRegistry.load` type handling:** it takes a `Path`; check that other
  argument types fail with one clear error (raised in the 2026-10-15 review;
  details not recorded).

Merge and warnings:

- **A later fragment re-declaring a main-namespace id** (for example
  `<ns>#DatasetPackage-1`) that is not in the base can collide with an id
  minted earlier in the same merge. Needs a pre-scan of all fragments.
- **`loom fragment list` now computes the registry exclusion**, so an invalid
  declared registry reports `SAME_DOCUMENT` unknown instead of an id.
- **`load_config_file` says "--config file"** (`core/config_cascade.py`) even
  when loom is the caller.
- **Merge hash-survivor policy.** When two fragments carry the same bytes the
  survivor is the first indexed, so a minted fragment-local id can beat a
  registry-pinned one: the sentimentdemo bootstrap loses `#File-8`/`#File-9`
  in the merged wheel SBOM. Prefer the registry-pinned id as survivor.
- **`id import` of an SBOM whose `ai_AIPackage` name differs from the file
  stem** releases the stem key `id generate` made, and its hash gate (a
  pre-existing behaviour). It matters more now that hashes gate ids: see the
  G7 blocker on harvest keys above.
- **A loom retrain logs `added 1 new id(s)`** for the replacement id of the
  retrained model, although the key already existed; the count is by ids
  under keys the registry did not hold elsewhere. Align the wording or count.
- **Two alias rules for one fact.** `_harvest._is_files_path_alias` and the
  one-direction tail check in `core/_models_wheel.py` (`_DeclaredRegistry`)
  both decide whether a `src/`-layout path and a distribution path are one
  file. Unify them in one helper.
- **Harvest churn.** Harvest now never erases a recorded sha (ruling
  2026-10-14); a package whose lock sha changes replaces it, so alternating
  runs with and without the lock can still rewrite the registry.

### Found by the order matrix (manual checks `O*`, 2026-10-15)

Each failed its `O*` check until decided; repro scripts are in the
runner's `ord-repro-*` directories (manual-cli-checks.md, "Order
matrix").

- ~~**A registry id is minted again for another file** once it has left
  the registry.~~ `_mint_id` took one more than the highest number the
  registry held; when a harvest replaced the highest-numbered entry's id
  (a `project` run after that file changed mints a document id), the
  next mint reused the number: `id generate`, edit `b.py`, `project`,
  edit `a.py`, `id generate` gave `a.py` the id `b.py` had in the first
  run (`O5/flat`, `O5/stems`, deep `O2/*`). Resolved 2026-10-15: the
  file keeps a per-prefix `id_counters` table, never lowered, and a mint
  takes one above it (I8 in
  [id-registry-v3.md](../implementation/id-registry-v3.md); ruling in
  [id-registry-v3-build-notes.md](../implementation/id-registry-v3-build-notes.md)).
- ~~**`id generate` erases the sha256 loom recorded for a shared-stem
  model**~~ (`_register_ungated`, on purpose: "the result does not depend on
  the registry's history"). D12 says an ungated registration never erases
  a recorded sha, and the effect is churn: loom's next gated lookup misses
  and re-mints the model id after every `id generate` (`O2/stems/*`,
  `O1/stems/fresh-loom`). Resolved 2026-10-15 (user ruling): a shared stem's
  entry is left as is, its sha256 included (D12); a stem with no entry gets
  a sha-less one. A fresh registry and one with history can differ for that
  stem; its id stays stable (D3 in
  [id-registry-v3.md](../implementation/id-registry-v3.md)).
- ~~**`loom wheel --id-registry R` lists and harvests the copy of R that a
  wheel built from an in-tree registry carries.**~~ The D7 exclusion
  (`_DeclaredRegistry`) ran only in `get_wheel_files`; build-then-`wheel`
  never settled (`updated stale entries` every run, the wheel's document
  uuid and its per-document ids changed each time) (`O3/intree`,
  `O1/intree/surfaces`). Resolved 2026-10-15: every reader of wheel or
  sdist members (`wheel`, `wheel --embed`, `embed-wheel` with or without
  `--project-dir`, `project <sdist>`, their library functions) leaves out
  a member whose path is the registry's path below `--project-dir`, else
  below the registry's stored `project_root`, or (a wheel only) a tail of
  it; no hash, as the copy is the registry at build time
  (`walk_rules.RegistryCopy`, shared with `_DeclaredRegistry`). The copy
  is out of the Merkle root; one `WARNING:` per run, an `embed-wheel`
  batch included. A registry rooted at its own directory does not match
  a copy under a package directory, so that copy stays.
- ~~**`id import` of an unhashed `ai_AIPackage` whose id differs from a
  hashed entry drops the entry's sha256**~~ (the harvested id wins). So the
  order of `id generate` and `id import` decides whether the model entry
  stays gated, and importing a pre-retrain SBOM reverts the model to its
  pre-retrain id. The ruling "harvest never erases a recorded sha256"
  says to keep it, which would bind the imported id to bytes it never
  described (`O1/flat/fresh-cli`). Decided 2026-10-15 (user ruling): the
  imported id wins and the sha256 goes, with one `INFO: ID registry: content
  gate dropped for <type> '<name>': imported id <new> replaces <old>` per
  key; a run's harvest never erases one (it leaves such an entry as is,
  `content gate kept`). The order matrix counts the resulting difference
  as order-dependent, not a violation. Revisit after G7 #3 (below).
- ~~**A read-only registry on `id generate`/`id import`**~~ gives `ERROR:
  [Errno 13] Permission denied: '<path>'`, without the `ID registry:
  failed to save <path>` wording every other surface uses (`O4/*`).
  Resolved 2026-10-15: one helper (`failed_to_save_message`) words it on
  every surface; `id generate`/`id import` print it as the one `ERROR:`
  and exit 1, the file untouched.

### Found by the review rounds (PR #305, 2026-10-15)

Resolved:

- ~~**Registry writes took several paths**~~ (`id generate`/`id import`
  rewrote an unchanged file; `id import` could overwrite a namespace changed
  meanwhile). Resolved: one `save_registry` (rebase, save only when the file
  differs); `Rebase.added` counts the ids a save adds, for the `INFO:`.
- ~~**Hostile or huge ids reserved counter numbers**~~ (and `register("")`,
  a non-integer `version`, a repeated JSON key, a `project_root` through a
  symlink). Resolved: reservation stops at 10**9 and skips a prefix that is
  not an IRI segment; `register("")` raises; `load()` rejects `3.0` and
  `duplicate key`; the root is relative to the symlink target's directory.
- ~~**An unreadable file below an `id generate` PATH aborted with
  `ID registry: could not read <abs>`**~~. Resolved: the shared `FILE=`/
  `DIR=` `WARNING:`, project-relative; a root PATH stays an `ERROR:`.
- ~~**A registry copy in a wheel was matched by any tail**~~ (`reg.json`
  dropped beside `src/demo/data/reg.json`), and a monorepo registry missed
  an sdist. Resolved: path, or path less one leading part with a directory
  and the file left; one member (the longest) per archive; no project
  directory: nearest project directory up to the stored root. Build-and-read
  copies are recognised by origin and keep an absolute `physical_path`.
- ~~**The loom registry-in-dataset warning needed a Merkle root**~~. Resolved:
  it also fires when the directory gets none.

Open:

- `cli/_id_target.py` repeats the three project-marker list of
  `registry_copy` (`pyproject.toml`, `setup.cfg`, `setup.py`); share one
  constant.
- `IdRegistry.save()` called directly by a library user is still a plain
  write; only the CLI, harvest and loom use rebase and replay.
- A retired id above the 10**9 reservation ceiling could in theory be minted
  again after a billion mints.
- The in-place write for a writable registry in a read-only directory is not
  atomic.
- Windows `os.replace` while another process holds the registry open has no
  retry.

### Design questions for the user

1. ~~Should a local dataset's package be keyed by its D9 path too?~~ Decided
   2026-10-15: no, the caller's string as passed.
2. ~~"Harvest never erases a sha" for every type.~~ Decided 2026-10-15:
   harvest records a sha256 only for `software_File` and `ai_AIPackage` (the
   two content-gated types) and never erases a recorded one.
3. **Default `project_root` when none is set is the registry file's
   directory** (commit 3). Confirm.

### Tooling

- **pyrefly cannot resolve the sibling imports in `scripts/manual_cli_checks`**
  (about 30 baseline errors, plus 2 from `_checks_loom`). Adding that
  directory to pyrefly's `search-path` would clear them.
- **`core/model_extract_limit.py` no longer fits its name:** it now also holds
  the dataset ceiling validator `require_positive_ceiling`. Rename (for
  example `core/ceilings.py`) in a small PR.
- **`_embed_build_sbom.py` and `EmbedFileCache`** are over the soft limit; the
  split is blocked by 12 test patch targets. `_embed_overlay.py` took the
  overlay helpers.
- **Local command traps:** `pytest -p no:xdist` fails because the config
  passes `-n` (use `-n0`); a bare `.venv/bin/mypy` exits 2 here, as no
  targets are configured (use `mypy src tests`); a bare `flake8` crashes on
  `.venv` (scope it to `examples src tests`).

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
sha256 and never erases a recorded one (`id_registry/_harvest.py`), so
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
