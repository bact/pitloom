---
Created: 2026-11-14
Last-Modified: 2026-11-14
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry: log lines that are not a broken registry

See also: [id-registry.md](id-registry.md) (what a registry pins, how to
create and choose one), [messages.md](messages.md) (every line's code).

- `INFO: ID registry: added N new id(s) to <path>` (N counts ids under keys
  the registry did not hold) or `INFO: ID registry: updated stale entries
  in <path>` (keys moved or ids were replaced) -- a run wrote into the declared
  registry.
- `INFO: ID registry: holds N id(s)` -- `id generate`/`id import` finished;
  the data line `PITLOOM_ID_REGISTRY_PATH=<path>` is on stdout.
- `INFO: ID registry: not imported (name held by several elements): <type>
  'NAME', ...` --
  `id import` only; the SBOM holds several elements under that name, so no
  single id can be pinned for it.
- `INFO: ID registry: content changed for <key>; minting a new spdxId
  (old: <id>).` -- a file, model or dataset pin whose content differs from
  its entry gets a new id (`id generate` re-indexing or `-e`, a `loom.Run`
  model with `path=`, a model file in a project run); normal after an edit or
  a retrain (a `project` run reports a changed file as `updated stale
  entries` above).
- `INFO: ID registry: model X: no registry entry records its SHA-256; a new
  id is used` -- `project`, `model`, `wheel` and the like: the model's entry
  has no hash (an old or imported one) or another; it never hits and the run
  records the hashed entry.
- `INFO: ID registry: dataset X matched a pin without SHA-256; content not
  checked` / `... pinned without SHA-256: <why>` / `... looked up ungated:
  not hashed` -- a dataset pin made before the data existed (or one that
  cannot be hashed) hits any content. Re-run `id generate -e` once the data
  exists: `... pin now gated by its SHA-256` (same id, digest adopted).
- `INFO: ID registry: N file(s) keyed by their path as read: <why>` -- the
  document's files could not be keyed from the registry's root (project
  outside the root, including a `--project-dir` outside it, or an archive
  path); they only match a registry made the same way. An archive read
  without `--project-dir` (`wheel`, `project <sdist>`, `generate` on either,
  `embed-wheel`) keys by its own paths, so with a registry root **above** the
  project (a monorepo) it misses, with no `INFO:` and root-level keys
  harvested. In a monorepo pass `--project-dir <the project's directory>`
  (`loom wheel dist/x.whl --project-dir pkgs/demo --id-registry
  loom-id-registry.json`): the archive's files are then keyed below the
  project's prefix, as `project` on a directory, `--allow-build` and the hook
  key them. Nothing else is read from that directory; without a registry it
  only warns that it has no effect.
- `INFO: ID registry: N element(s) matched a registry key through the
  src/lib layout alias` / `N key(s) promoted from a layout alias` -- a built
  file or model `demo/x.py` reused the id held for `src/demo/x.py` (only a
  leading `src/` or `lib/`, equal SHA-256, unique candidate); `id generate`
  moves such a key to its on-disk path, also over that path's entry for older
  content (`N key(s) of changed content took their layout alias's id`), and
  `id import` writes such a file under the alias (`N file(s) imported under
  their layout alias: their own key holds other content`). Other layouts
  (`python/`, `packages/`) get no alias: a wheel-only run mints its own ids
  for them.
- `INFO: ID registry: -e NAME stored as KEY` / `stored by name: <why>` /
  `stored without a version: holds only a package that states none` --
  `id generate -e` (see above). `INFO: ID registry: dataset|model X keyed by
  its name: <why>` -- `id import`/`loom` kept a name key because no file
  below the root matched (`dataset X keyed by its path: KEY` only when `id
  import` found a path other than the name); `model X imported under its
  name: no unique file with its SHA-256`, `model X keyed by the registry's
  file with its SHA-256: KEY` -- `id import` of a model.
- `INFO: ID registry: <type> 'KEY' not imported: its id is held under 'KEY2'`
  -- `id import` leaves an id held under another key of its type where it is.
  `INFO: ID registry: model X not recorded: no unique file with its SHA-256`
  -- a run's harvest does not record a hashed fragment model with no file of
  that hash (nothing is rolled back).
- `INFO: ID registry: content gate dropped for <type> 'X': imported id <id>
  replaces <id>` -- `id import` only; the SBOM's element has no hash and
  another id, which wins, so the entry is no longer checked against content
  (an older SBOM brings its older id back).
- `INFO: ID registry: content gate kept for <type> 'KEY': harvested id <id>
  not recorded over <id>` (or `element id <id> with an older SHA-256 not
  recorded over <id>`) -- a run met such an element, or a merged fragment's
  stale one; the entry is kept, never rolled back.
- An `ERROR:` with `ID registry:` is a real failure: see `messages.md`;
  `failed to save <path>: <reason>` has no code yet, `<reason>` says why.
- `WARNING: ID registry: failed to save <path>: <reason>` -- a run could
  not write the registry (read-only file, full disk); its SBOM is written.
  The path is the registry's, never a temporary file's.
  `id generate`/`id import` print the same text as their one `ERROR:`, exit
  1, the file left as it was.
- `WARNING: ID registry: <id> is registered for both X and Y; Y gets a new
  id` -- two elements matched entries carrying one id. The first claimant
  keeps the pinned id and the second mints a fresh one; it does not fail the
  run. Expected on every run when the pin was made for an ambiguous name
  (above); otherwise two registry entries share one id, usually a stale one
  -- mention it to the user.
- `WARNING: loom: ... not found in registry; minting a new spdxId (untracked
  entity|file)` -- a `loom.Run` dataset, file or model with no entry yet:
  expected on a first run. `... registry entry for <model|dataset
  package|file|entity> 'X' exists but its SHA-256 no longer matches ...` means
  the file changed since it was pinned. Either way a fresh id is used.
- `WARNING: loom: file X is outside the ID registry's project root ...;
  minting a new spdxId` -- the script passed a path outside the project;
  its file is not looked up.
- `WARNING: loom: registry entry for entity 'X' exists but under a different
  type; minting a new spdxId.` -- a key the registry holds only as another
  type; the element gets a fresh id.
- `WARNING: loom: ID registry <path> is inside dataset directory 'X'; left
  out of its Merkle root` -- the registry file sits in a dataset directory;
  move it outside (once per directory per run).
- `WARNING: loom: model X has no path=; not hashed, looked up by name only`
  (or `... is not a file at exit ...`) -- the model is matched by name and
  gets no hash; add `path=` to the `set_model()`/`use_model()` call.
- `WARNING: Merge: <Type> '<name>' shares spdxId <id> with a <Type> of a
  different SHA256 hash; keeping both, it gets new id <id>.` -- a merged
  fragment reused an id for other content; both elements stay. For equal
  content under two ids the one more sources share (the registry-pinned
  id) survives the merge.
- `INFO: Merge: 'name' on ai_AIPackage <id>: keeping the fragment's 'X',
  dropping the project's 'Y'.` -- a project build merged a fragment whose
  `set_model()`/`use_model()` named the model file otherwise: the model
  takes the loom name and keeps the file key's id; expected on every run.
  Two runs naming one file two ways keep the project's name, with a
  `WARNING: Merge: conflicting 'name' ...` per other name.
- `INFO: ID registry: package identity unknown; not looked up or recorded` --
  a wheel with no usable `.dist-info` or `METADATA` name; the registry is not
  touched for its package.
- `WARNING: ID registry: not adopting the namespace ...` -- `id import` met
  an SBOM whose document id is not a valid namespace IRI; the registry keeps
  its own namespace.
- `WARNING: DIR=<dir>: could not list for ID registry indexing; <failure>
  [dir-unlistable]` -- `id generate` left out the files of a directory it
  could not list; if you see it, relay the advice of
  [messages-files.md](messages-files.md#dir-unlistable).
- `WARNING: ID registry: <path> is inside the project's file set; left out
  of it` -- keep the registry outside the
  package tree ([id-registry.md](id-registry.md)).

A declared registry that is missing or invalid (a version 3 file included)
is different: one `ERROR:`, exit 1, nothing written.
