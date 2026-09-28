---
Created: 2026-09-17
Last-Modified: 2026-09-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Auto-sync the Loom ID registry after SBOM generation

See also: [roadmap.md](../design/roadmap.md) (Completed), the "Loom IDs
across fragments" section of the top-level [README.md](../../README.md#loom-ids-across-fragments-pitloom-ids).

Split out of `roadmap.md` (2026-09-17) once this item's detail grew
past a summary.

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
(one `lookup_entity(dep_name, PACKAGE_ENTITY_TYPE)` per `env_tree` node).

`pitloom.core.models.reserve_spdx_ids(doc_name, doc_uuid, spdx_ids)`
parses each id against the document's own namespace and records its
`(prefix, n)` in a `_RESERVED` map; `generate_spdx_id()` skips any
reserved `n` instead of re-minting it. `_clear_doc_counters()` clears
`_RESERVED` too, so a caller must reserve *after* clearing, never
before. `document.py build()` reserves the union of all three
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

`pitloom.id_registry.claim_registry_hit(key, spdx_id, claimed)` is the one
helper every `_resolve_*_hits` pass calls for each hit it finds: the
first key to claim a given id keeps it, a later key with the *same*
hit id is treated as a miss (falls back to its own fresh mint) and
gets one `WARNING: Registry: <spdxId> is registered for both <first>
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
successful claims. A directory whose hit is rejected by
`claim_registry_hit` (lost the first-claimant race) or whose lookup
misses adds no `dir_hits` entry either way, so memoizing on `dir_hits`
membership alone would re-look-up and, on a rejection, re-log the same
`WARNING: Registry: ... registered for both ...` once per file sharing
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
bumped to 2, no migration. An old-version file is rejected differently
by surface: a build surface consulting an *explicit* registry path
(`resolve_registry`/`resolve_explicit_registry`, used by `build()`/
`build_deployed()`/the Hatchling hook) logs
`WARNING: Registry: could not load ...` and proceeds with no registry;
an *auto-discovered* `loom-ids.json` (`IdRegistry.find()`, no
`--registry`/`ids_file` given) instead logs
`WARNING: Registry: ignoring invalid file ...` -- same outcome,
different wording because a different function logs it. `pitloom ids
generate`/`pitloom ids import` (`_load_or_create_registry`) print
`ERROR: failed to load registry from ...` and exit 1 instead, since
those commands' entire job is to write to that file -- silently
proceeding without one would produce a registry that doesn't build on
the previous run's ids. Both point at the same fix: delete the file
and re-run `pitloom ids generate` or `pitloom ids import`.

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
`"Registry: added %d new file(s), %d new entit(y/ies) to %s"` when the
net counts are nonzero, `"Registry: updated stale entries in %s"` when
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
