---
Created: 2026-09-17
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Auto-sync the Loom ID registry after SBOM generation

See also: [roadmap-completed.md](roadmap-completed.md), the "Loom IDs
across fragments" section of the top-level [README.md](../../README.md#loom-ids-across-fragments-loom-id).

Split out of `roadmap.md` (2026-09-17) once this item's detail grew
past a summary.

This file records registry v2 as built. The planned registry v3
([id-registry-v3.md](../design/id-registry-v3.md), not built) supersedes
parts of it: the two tables (`files`/`entities`) and harvest's
shape-based choice between them, the format version 2, the
`ai_AIPackage`/`dataset_DatasetPackage` auto-harvest exclusion (hashed
AIPackages become harvestable), the `added N new file(s), N new
entit(y/ies)` wording, and the rule that no run writes a model id (loom
will record one). Open items: [id-registry-followups.md](../design/id-registry-followups.md).

## What shipped ([PR #178](https://github.com/bact/pitloom/pull/178))

`loom project`/`wheel`/`env` harvest newly-minted spdxIds back into the
resolved id registry after each run, so a subsequent run against the
same project reuses the same ids for the same elements instead of
minting fresh ones.

`ai_AIPackage`/`dataset_DatasetPackage` elements are deliberately
excluded from auto-harvest -- their identity (`ai_model.name`) is
extraction-dependent, not a stable key the way a file path or a
dependency name/version pair is. Auto-harvesting them risks silently
pinning the wrong element under a name that later re-extracts
differently.

## Id mint-collision fix ([#234](https://github.com/bact/pitloom/pull/234))

Auto-sync mixes registry-supplied ids (via a lookup-then-mint-fallback
pattern) with freshly-minted ones in the same document namespace.
Several distinct ways that can collide, and the fixes for each, below.

### The collision

- **Within one run**: `generate_spdx_id()`'s per-prefix counter didn't
  know about the registry -- a lookup hit never advanced the counter,
  so a later fresh mint (a directory element, or any file whose
  registry entry went stale) could land on the exact number a hit
  already returned.
- **Across runs, via a stale entry**: a fresh mint can coincidentally
  land on an id an *unrelated, still-registered-but-not-looked-up-this-
  run* entry already holds. E.g. wheel run 1 `{a, b}` registers `b` as
  `File-5`; run 2 `{a, c}` never looks `b` up, so nothing reserves
  `File-5`, and `c`'s fresh mint lands on it too; run 3 `{a, b, c}`
  then has both `b` and `c` hitting `File-5`.
- **Simultaneously, within one run**: two elements can legitimately hit
  the same registered id at once -- e.g. two AI models sharing a file
  stem (see [ai-model-id-stability.md](../design/ai-model-id-stability.md)).

### Pre-resolution and hit-only reservation

Each surface pre-resolves its own registry hits before its first mint,
right after `_clear_doc_counters()`, one lookup per candidate element:
`_document_files._resolve_file_and_directory_hits()` (every directory,
via `IdRegistry.lookup_entity(name, DIRECTORY_ENTITY_TYPE)`, and file
in `metadata.files` order), `assemble.spdx3.ai.resolve_ai_model_entity_hits()`
(one call per AI model), `_document_deployed._resolve_deployed_package_hits()`
(one `_package_ids.resolve_package_id()` session lookup per `env_tree`
node),
and, for `project`/`wheel`, `_package_ids.resolve_project_package_ids()`
(main package, dependencies, phantom dependencies -- see "Revised in PR
A2" below).

`pitloom.core.models.reserve_spdx_ids(doc_name, doc_uuid, spdx_ids)`
parses each id against the document's own namespace and records its
`(prefix, n)` in a `_RESERVED` map; `generate_spdx_id()` skips any
reserved `n` instead of re-minting it. `_clear_doc_counters()` clears
`_RESERVED` too, so a caller must reserve *after* clearing, never
before. `document.py build()` reserves the union of all its
resolvers' hits via one `reserve_spdx_ids()` call, then passes the
resolved dicts/lists down instead of the registry itself:
pre-resolution is the single source of truth for what was reserved, so
the build never looks the registry up a second time.
`build_deployed()` does the same for its own resolver's result.

The rule: a collision only happens when a reused id equals a mint the
same document would otherwise hand out, so reserving exactly the ids
this document's own lookups *hit* -- each claimed by exactly one
element, see "First claimant wins" below -- is necessary and, together
with first-claimant-wins, sufficient; output stays independent of any
registry entry nothing here reuses.

**Rejected: a type-wide scan** (`IdRegistry.entity_spdx_ids(type_name)`
for every `software_Package`, or `IdRegistry.spdx_ids()` for the whole
registry, since removed as dead API). Both also reserve ids nothing in
this document ever looks up -- `build_deployed()`'s own main
`deployed-environment` package (always minted, never looked up) and
any dependency whose harvested name doesn't match its lookup key -- so
those numbers drift by one on every rerun without preventing any real
collision, breaking output byte-stability.

`build_model()` (the standalone single-AI-model-file SBOM) consults no
registry beyond its caller-pre-resolved `ai_AIPackage` id, so no
reservation call applies there. `pitloom.loom` (`_loom_active_run.py`)
resolves a registry too, but each `Run` mints under a fresh `uuid4()`
`doc_uuid` that is never revisited, so its own `_ID_COUNTERS`/
`_RESERVED` can never collide with a prior run's -- reservation would
be a structural no-op there, so it was left alone; only its
name-only-entities check uses `IdRegistry.has_entity_named()`.

### First claimant wins

**Pre-A2 mechanism, kept for the rationale.** `claim_registry_hit()` and
the per-call-site shared `claimed` dict this section describes were
removed in PR A2 -- see "Revised in PR A2" below. The *rule*
(first-claimant-wins, one shared claim scope per document) is unchanged;
it is now enforced by `pitloom.id_registry.IdRegistrySession`
(`id_registry/_session.py`)'s `file_id()`/`entity_id()`/internal
`_claim()`, one session per document build, instead of the ad hoc
per-resolver `claimed` dict named below.

`pitloom.id_registry.claim_registry_hit(key, spdx_id, claimed)` is the one
helper every `_resolve_*_hits` pass calls for each hit it finds: the
first key to claim a given id keeps it, a later key with the *same*
hit id is treated as a miss (falls back to its own fresh mint) and
gets one `WARNING: ID registry: <spdxId> is registered for both <first>
and <second>; <second> gets a new id`. Each resolver iterates in a
fixed, deterministic order (files in `metadata.files` order,
directories root-to-leaf, AI models in `ai_models` list order, env
deps in `env_tree` order); `document.py build()` shares one `claimed`
dict across files, directories, and AI models together, so the rule
holds across all three, not just within one resolver.
`build_deployed()` uses its own separate `claimed` scope (a different
document).

This is also what makes the AI-model file-stem-collision case (see
[ai-model-id-stability.md](../design/ai-model-id-stability.md))
recoverable instead of silently dropping the second model: it gets its
own id and a warning instead of reusing the first model's.

`_resolve_directory_hits_for_file()` memoizes every ancestor directory
it has already resolved for the current file pass in a `seen_dirs` set
-- not just the ones recorded in `dir_hits`, which only holds
successful claims. A directory whose hit is rejected by the session's
claim (`IdRegistrySession.entity_id()`, lost the first-claimant race) or
whose lookup
misses adds no `dir_hits` entry either way, so memoizing on `dir_hits`
membership alone would re-look-up and, on a rejection, re-log the same
`WARNING: ID registry: ... registered for both ...` once per file sharing
that directory instead of once per directory.

`pitloom.loom`'s `_ActiveRun` has its own claim state
(`_claim_loom_registry_hit()`), since it isn't a one-pass resolver like
the three above: `set_model()` or an `add_*_dataset()` call can
legitimately repeat for the same name/file within one run (e.g. a model
set once before training and once after, with hyperparameters filled
in). The first call to hit a given registered id claims it; every
repeat is *unconditionally* a miss and mints its own id plus the
warning -- deliberately content-blind, never comparing the repeat's
arguments to the first call's. An earlier revision tried that
comparison (reuse the id silently when the repeat "looks identical"),
but it's a proxy for the actual exported element and drifts from it:
`add_dataset()`'s element also carries a file hash the signature never
covered (`add_input_dataset("x")` then, after the script rewrites `x`,
`add_output_dataset("x")` -- same declared type, different hash), and
`set_model_hyperparameters()` mutates the first `ai_AIPackage` object
*after* its signature was recorded (`set_model("m")` ->
`set_model_hyperparameters(...)` -> `set_model("m")` again wrongly
matches the pre-mutation signature). Either drifts the id-reuse
decision away from the content actually written, so two elements can
still end up sharing an id while differing in content and trip the
duplicate-spdxId safety net at `Run.__exit__`. Never reusing an id past
the first call removes that whole class of drift; the cost is that even
a genuinely identical repeat now gets its own id and a warning (like
the no-registry case, which already mints a fresh id per call -- the
warning is the only difference, and it is truthful about which call got
the registered id).

The generating script's own `software_File`
(`_build_script_file()`'s `_hash_and_registry_lookup()` hit) goes
through the same `_claim_loom_registry_hit()` claim as
`set_model()`/`add_*_dataset()`, not straight to the registry's own id
-- otherwise a registry where the script's key happens to share an id
with a dataset/model key (two independently-registered files that were
never meant to collide) mints two elements with the same id and trips
the duplicate-spdxId safety net at `Run.__exit__` instead of getting
its own fresh id plus the usual warning.

### One key per id in the registry

`pitloom.id_registry._harvest._release_stale_keys_for_id()` runs before
`_import_sbom_element()` writes a harvested id under a key: it drops
any *other* key already holding that exact id, so a stale entry left
behind by an earlier run can't keep re-triggering the same collision
warning on every later run.

Files-table exception: a key is kept only when BOTH its `sha256`
matches the new entry's AND its path is a
`pitloom.id_registry._harvest._is_files_path_alias()` of the new key -- trailing
`PurePosixPath` parts tail-match, one a strict suffix of the other
(e.g. `src/pkg/x.py` vs `pkg/x.py`), the intentional
physical-path/distribution-path dual-keying for one src/-layout file
(see `_add_package_files()`'s two-path lookup). Entities have no such
alias case, so any other entities key sharing the id is always
dropped.

A one-part key (e.g. `x.py`, no directory component) is a suffix-alias
of the *same filename at any depth* (`_is_files_path_alias("x.py",
"a/b/x.py")` is true, since `("x.py",)` tail-matches any path ending in
`x.py`) -- this only matters once two keys already share an id (the
harvest that would let an unrelated `x.py` steal a genuinely different
file's key still requires a real content-hash match first), and its
effect is id churn on the next mismatch, not a duplicate.

**Rejected: sha256-match alone** (drop a files-table key only on a
content mismatch). Two *different* files with identical content (e.g.
two empty `__init__.py` files in unrelated directories) are not the
same file under two names -- sha256 match alone left a stale key alive
indefinitely, stealing an unrelated file's id on a later run. Both
conditions, same hash and suffix-alias shape, are required.

`_release_stale_keys_for_id()` checks `spdx_id` equality before the
more expensive sha256/alias check, against a `pitloom.id_registry._harvest._SpdxIdIndex`
-- a `spdx_id -> keys` reverse index over both the `files` and
`entities` tables, built once per `_harvest_sorted()` pass and kept in
sync (`set_file`/`drop_file`/`set_entity`/`drop_entity`) as entries are
released during it -- instead of scanning the whole table per harvested
element. Without it, harvesting is O(harvested elements * registry
size); with it, each release is O(keys actually sharing that id).

### Entity keys, PEP 503 canonicalization, and registry version 2

`IdRegistry.entities` is keyed by `(type, name)`, not `name` alone -- a
harvested directory and a same-named package (or any two
differently-typed entities sharing a name) no longer overwrite each
other. `pitloom.id_registry._types._entity_key(name, type_name)` is the single place
a `PACKAGE_ENTITY_TYPE` entity's name is PEP 503-canonicalized
(`packaging.utils.canonicalize_name`), used by `register_entity()`,
`lookup_entity()`, and harvest alike -- a caller like
`_resolve_deployed_package_hits()` passes a dependency's declared name
straight through uncanonicalized and lets the registry canonicalize
it, so a purely-cosmetic mismatch (declared `"PyYAML"` vs pipdeptree's
lowercased `"pyyaml"`) no longer leaves a harvested entry permanently
unreachable.

The on-disk `entities` object is nested by type
(`{"<type>": {"<name>": {"spdxId": ...}}}`); `_REGISTRY_VERSION`
bumped to 2, no migration. **As revised in PR A2, see below**: every
surface now raises/exits on a declared-but-broken registry file
(including an old-version one), instead of the split described in the
rest of this paragraph, which describes the pre-A2 behaviour for
context. Before PR A2, an old-version file was rejected differently by
surface: a build surface consulting an *explicit* registry path
(`resolve_registry`/`resolve_explicit_registry`, used by `build()`/
`build_deployed()`/the Hatchling hook) logged
`WARNING: ID registry: could not load ...` and proceeded with no
registry; an *auto-discovered* `loom-id-registry.json`
(`IdRegistry.find()`, no `--id-registry`/`id-registry` given) instead
logged `WARNING: ID registry: ignoring invalid file ...` -- same
outcome, different wording because a different function logged it.
`pitloom id generate`/`pitloom id import` (`_load_or_create_registry`)
printed `ERROR: failed to load registry from ...` and exited 1 instead,
since those commands' entire job is to write to that file -- silently
proceeding without one would produce a registry that doesn't build on
the previous run's ids. All three pointed at the same fix: delete the
file and re-run `pitloom id generate` or `pitloom id import` -- that
fix is unchanged by PR A2.

### Revised in PR A2 (2026-09-28)

`resolve_explicit_registry()` and `IdRegistry.find()` (auto-discovery,
including its `loom.Run` walk-up) are removed. A registry is now used
only when explicitly declared -- `--id-registry`/`id_registry=`, the
target's own `[tool.pitloom] id-registry`, or a `--config` file's
`id-registry` -- on every surface, with no fallback search. A declared
registry that's missing, unreadable, or invalid is fatal everywhere,
collapsing the three-way split above into one `ValueError` raised by
`IdRegistry.load()` (message: `ID registry file <path>: <reason>`): the
CLI prints one `ERROR:` line and exits 1 (`cli_error_handler`), the
library API and `loom.Run` raise it directly (never also logging, to
avoid a double error line), and the Hatchling build hook logs one
`ERROR:` and fails the build. Registry lookups during a single
document's build now go through `IdRegistrySession`
(`id_registry/_session.py`), which replaces the ad hoc first-claimant
bookkeeping each call site used to do (`claim_registry_hit`, removed).

**Why (user decision):** a config file found by walking up from the
current directory, or from the project directory, may belong to an
unrelated project -- silently picking it up (or silently skipping a
broken one) is worse than failing loudly. Being explicit about which
registry is in play, and failing fast when it can't be read, beats a
best-effort fallback that could quietly use the wrong file or none at
all.

**Package ids (2026-09-29, commit 3 of PR A2).** `project`/`wheel` minted the
project's own `software_Package`, its declared and lock-resolved
dependencies and its phantom dependencies without consulting the registry,
though harvest wrote all of them into it -- so a pinned
`id generate -e NAME:software_Package` id was overwritten by the first
project run, alternating project/wheel runs rewrote the package entries
every time, and `env` reused whichever document harvested last.
`spdx3.document.build` now pre-resolves them through the shared session
(`assemble/spdx3/_package_ids.py`), before `reserve_spdx_ids`, in a fixed
order: main package, dependencies (once per PEP 503 name, declared then
lock-resolved), phantom dependencies; `env` uses the same
`resolve_package_id()`. One registry key backs one id, so two distinct
packages sharing a name (two pinned versions, or a declared package and a
bundled binary) cannot both use it: the first takes it, the other mints a
fresh id with the usual claim `WARNING:` (`DependencyIdHits`,
`warn_claim_collision`). Output is byte-identical without a registry.
Out of scope, unchanged: harvest still rewrites per-document entities
(`SoftwareAgent`/`Tool`/`License` ids follow each document's own uuid), so
registry bytes still change across project/wheel runs -- only the package
entries are stable; `env`'s root package is still always minted.

**Ambiguous package names (2026-09-29, commit-3 review).** Lookup gives a
name's registry id to the *first* claimant, while harvest kept the *last*
element per key in `spdxId` order, so a document with two same-name
`software_Package` elements (a self-referencing extra `demo[x]; extra ==
'all'` next to the main package, two pinned versions of one dependency, a
dependency or main package sharing a phantom stem) swapped ids between runs.
Now harvest (`IdRegistry.harvest` and `import_sbom`, via
`_harvest_elements`/`_ambiguous_entity_keys`) never writes a key held by more
than one element of the document and leaves any existing entry untouched;
an existing pin goes to the first claimant with the claim `WARNING:`, the
same on every run; a dependency named like the project (a self-referencing
extra) never looks up, so it mints silently and the main package keeps the
registry id. A phantom dependency named like the project or a dependency
never looks up either (silent, same rule; decided 2026-09-29, or alternating
`project`/`wheel` runs would warn on wheel builds only); two phantoms of one
name still both look up, so the second warns, like two versions of one
dependency.

Run auto-harvest leaves those non-readers out (decided 2026-09-29, commit
3b): they neither count as a holder of their name nor get written, so a
name only one element *reads* is written for it and pinned on the next run
(before this, `demo[x]` next to `demo` meant the main package was never
pinned). Only one element reads the key, so no swap is possible. The
non-reader ids come from the code that decides not to look up:
`_package_ids` records which canonical names/phantom indices skip the lookup
(`DependencyIdHits.looked_up()`, `ProjectPackageIds.phantom_not_looked_up`),
`deps.py`/`deps_phantom.py` add each such package's minted id to
`Spdx3JsonExporter.registry_non_readers`, and `_sync_registry` filters them
out before `IdRegistry.harvest`, so `_ambiguous_entity_keys` stays the one
counter. Rejected: re-deriving non-readers at harvest from names or graph
relationships (a name filter would also drop the main package; a graph
heuristic would drift from the lookup code). `env` records none: its
synthetic root never looks up but is written as before (no dependency can
share its name in practice). `id import` has no such record and still skips
every multi-holder key. Two versions of one dependency both read
(`DependencyIdHits.take`), so they stay ambiguous.

The harvest skip applies to every entity type, not just
`software_Package`: the `ai_AIPackage` `numpy` import test
(`test_generator_registry_sync_ai.py`) had to pin its stale entry by hand,
since ten same-stem models are now one ambiguous key. `loom id import` names
what it skipped in one `INFO: ID registry: not imported (name held by
several elements): <names>` line (sorted); auto-harvest logs each skipped key
once at DEBUG only. A name-keyed registry cannot pin an ambiguous name; the
one-name-per-document caveat is documented for users instead of solved.

**Paths rejected:** keeping the walk-up as a fallback when nothing is
declared (rejected -- reintroduces the unrelated-project risk above);
keeping the old warn-and-continue behaviour for a declared-but-broken
file (rejected -- a registry the user explicitly named should never be
silently ignored, since that risks minting fresh ids that silently
diverge from a previous run's).

`loom id generate`'s relative `-o`/`--id-registry` and PATH arguments
also now resolve against the current directory, not `--project-dir` --
dropping the deliberate exception this doc's own text used to describe,
for consistency with every other command; registry keys and the
implicit default paths are unaffected, staying relative to
`--project-dir`.

**Registry location is required everywhere, never assumed (user
decision, 2026-09-28):** `loom id generate`/`loom id import` no longer
fall back to an implicit `<project-dir>/loom-id-registry.json` /
`./loom-id-registry.json` when neither `-o`/`--id-registry` nor a
declared project `id-registry` key names a target -- they now print one
`ERROR: no ID registry declared: pass --id-registry FILE or set
id-registry in [tool.pitloom]` (`[tool:pitloom]` for a
setup.cfg-configured project) and exit 1, writing nothing. Why: the
implicit default silently pointed both commands at whatever
`loom-id-registry.json` happened to exist relative to the resolution
base, which was rarely the file the caller meant -- `id import` run
from the wrong directory silently merged into and rewrote an unrelated
`./loom-id-registry.json`, and `id generate` created an undeclared file
that the next build (reading `[tool.pitloom]`, which never named it)
silently ignored. `loom-id-registry.json` stays as
`DEFAULT_ID_REGISTRY_FILENAME`, the suggested name in docs/skills, but
is no longer assumed by these two commands. The INFO "add to
`[tool.pitloom]`" hint after a fresh write is unchanged.

### Duplicate-spdxId safety net

`Spdx3JsonExporter.to_json()` runs `_check_no_duplicate_spdx_ids()` on
the serialized `@graph`, *after* both `_deduplicate_creation_infos()`
and `_deduplicate_named_elements()` have run, and raises `RuntimeError`
naming the id and both elements' type/name. Byte-for-byte identical
copies sharing an id (e.g. `pitloom.loom`'s `set_model("m")` called
twice, or the same file added via both `add_input_dataset()` and
`add_dataset()`, both legitimate, common loom patterns) are collapsed
to one by dedup before the check ever sees them; what survives is only
dedup's "conflict, retain all" branch -- two same-id elements that
differ in content. Now that every surface that resolves a registry hit
(`build()`, `build_deployed()`, and `pitloom.loom`'s `_ActiveRun`) routes
it through first-claimant-wins, that branch should never actually be
reached in practice -- this check is an internal-invariant guard against
a future surface skipping that routing, not the primary defense against
a real collision. A last-resort safety net, not a substitute for the
reservation fixes above.

**Rejected: check before dedup, against `object_set` directly.**
Raised on the legitimate identical-copy case too, crashing a real
training script's `Run.__exit__`.

### The `changed` flag and INFO wording

`IdRegistry.harvest()`'s `(new_files, new_entities)` counts are *net*
size deltas, which go to `(0, 0)` when a harvest both adds one key and
releases a different stale one in the same pass (see "One key per id"
above) -- `_sync_registry()` used exactly that to decide whether to
`save()`, so a real content change was silently never persisted.
`harvest()` returns a third value, `changed: bool` (based on actual
dict-content comparison, not size), and `_sync_registry()` gates its
`save()` on that instead. Its INFO log distinguishes the two cases:
`"ID registry: added %d new file(s), %d new entit(y/ies) to %s"` when the
net counts are nonzero, `"ID registry: updated stale entries in %s"` when
`changed` is true but the net counts are zero (a release and an add
cancelling out) -- the latter would otherwise misleadingly read as
"added 0... entit(y/ies)", as if nothing had happened.

## Found, not fixed

- A `pitloom.loom` fragment can carry a registry-supplied file id that
  falls inside the *main* document's own namespace, for a file the main
  document's own build never happened to include. Nothing currently
  checks that a fragment-carried id is actually one *this* document
  minted or reserved -- the merge step looks elements up by id
  (`find_by_id`) and unifies on a match, so that id can merge by
  coincidence into an unrelated, independently-minted element from the
  main document instead of being recognized as foreign. Same behaviour
  as HEAD; not investigated further here.

## Open follow-ups

- [AI model id stability](../design/ai-model-id-stability.md) -- the
  excluded `ai_AIPackage`/`dataset_DatasetPackage` case above; no
  implementation direction chosen yet.
- [Sort-order canonicalization](sort-order-canonicalization.md) -- a
  related audit of whether registry/hash construction depends on
  non-canonical sort order anywhere in the id-registry path.
