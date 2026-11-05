---
Created: 2026-11-02
Last-Modified: 2026-11-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Known bugs: ID registry and identity

See also: [known-bugs.md](../known-bugs.md) (index, severity scale,
rules for adding an entry), [roadmap.md](../roadmap.md),
[id-registry-followups.md](../id-registry-followups.md),
[id-registry-v3.md](../../implementation/id-registry-v3.md).

Stable ids: ID registry keys, harvest and lookup, document and entity
identity, `Agent` elements. Entries are ranked by priority tier, then by size
tag; see the severity scale in the index. Open entries come first; fixed
entries stay in the last section for history.

## Open

### P1: registry v3 in 0.21.0 (some built, some not)

- [ ] **Remote entries are keyed by bare name, never pinned (M, own PR).** A
  Hugging Face model or dataset and a URL dataset (`loom.use_model`,
  `add_*_dataset`) keep one id whatever the revision. Plan: a remote-shaped
  key (`huggingface.co/<id>@<sha40>`, else the sanitised https URL), entry
  fields `remote` and `iri`, `revision=` on `loom.use_model` and
  `add_*_dataset`; an unpinned one keeps the bare key with one `INFO:`, never
  aliasing a pinned key. Git sources wait for `pkg:git`.
- [ ] **A Hugging Face model is named and keyed by the last segment of its repo
  id (S-M).** `loom model org-a/llama` and `org-b/llama` at one commit get
  identical spdxIds (no registry needed), and `id import` keys such a model
  `llama` while `loom.Run` looks it up as `org-a/llama`.
- [ ] **sdist placeholder names.** An sdist with no `Name` is `unknown` and is
  still looked up and harvested; two sdists whose PKG-INFO lacks `Name` share one
  doc uuid and reuse a pinned `unknown` id. (Wheels: fixed in PR #305 with
  `identity_known` and a file-name uuid seed.) See
  [id-registry-followups.md](../id-registry-followups.md#wheel-identity-and-archive-readers).

### Found in review rounds, not yet prioritised

- [ ] **A loom fragment's pointer does not unify with the hook's or an
  `--allow-build` run's (S-M).** The fragment's element states the `oid`,
  the archive's the text's digest: the merge keeps two `software_File`
  elements for one path. Harvest no longer loses the id over it (#378: the
  fragment's element is the pointer's twin, never written; before, the key
  was ambiguous, nothing was recorded, and the next checkout minted).
  Long-term fix: fold the two in the merge by the registry hash
  (`_MergeIndex` indexing a document file under its `registry_hashes`
  entry). Not done: it changes SBOM output, and the survivor's hash list
  must not take the `oid`, which is not the digest of the shipped bytes
  (`RECORD`), nor drop the fragment's provenance.
  *Found 2026-10-29, Git LFS pointer work.*
- [ ] **A dynamic-version `project` run and a wheel or hook run give two
  main-package ids (S-M, decided: kept).** The first states `unknown` and keys
  the package bare; the second states the real version (D3 in
  [id-registry-v3.md](../../implementation/id-registry-v3.md)).
  *Found 2026-10-30, from #407 (registry package key).*
- [ ] **Refusing a registry version 3 file discards every file, model and
  dataset id (S-M, design).** Version 4 (#407) differs from version 3 only in
  the `software_Package` keys, but the refusal tells the user to delete the
  file and regenerate, which throws away all the stable non-package ids.
  `project`, `generate`, `id generate`, `id import`, `id generate -e
  <x>:software_Package` and `env` all refuse it with `ERROR: ... version 3,
  expected 4 (no migration support ...)` and leave the file unchanged. This
  reverses #407's choice that a version 3 file is never migrated. Option:
  accept version 3, drop its `software_Package` section (a bare version 3 key
  now means "states no version"), emit one `WARNING:` with the count dropped
  and save as version 4. Suggested for 0.23.0; not done in it.
  *Found 2026-11-02, cold review of the merges since 0.22.0.*
- [ ] **`id import` of a wheel or sdist SBOM holds the text's digest (S,
  decided: kept).** `id import` records what an SBOM states; the next run
  misses once for each pointer (a new id), then holds.
  *Found 2026-10-29, Git LFS pointer work.*
- [ ] **The `Tool`/`SoftwareAgent` "Pitloom" registry entries churn (S).**
  Their id's document-uuid part flips on each project-then-wheel
  alternation, so the registry is rewritten each run (not pointer-specific;
  tracked in
  [id-registry-followups.md](../id-registry-followups.md#harvest-rewrites-per-document-entities-env-root-is-never-looked-up),
  allow-listed in the order checks).
  *Found 2026-10-29, Git LFS pointer work.*
- [ ] **A loom fragment's document namespace is a random `uuid4` per run (S).**
  `_ActiveRun` sets `doc_uuid = str(uuid4())` (`_loom_active_run.py`), so the
  same script gives different `spdxId`s each run unless an ID registry pins
  them; the idempotence rule (no random UUIDs) holds only with a registry.
  Found while testing the dataset-size fix: the determinism test sits on
  `build_model`, not on `loom.run`.
  *Found 2026-10-29, Git LFS pointer work.*
- [ ] **The example registry holds this Linux platform's fastText model hash
  (S).** On another platform the model gets a new id once, unless the registry
  is regenerated there.
  *Found 2026-10-30, from #407 (registry package key).*
- [ ] **The ID registry `PATH` error is uncoded (S).** It waits for registry
  PRs 5 to 7.
  *Found 2026-10-30, from #408 (unreadable files, catalogue 2a; 2b and later).*
- [ ] **The registry key and the dependency grouping disagree on a
  placeholder version's spelling (S).** `package_version_key` treats blank,
  `unknown` and `NOASSERTION` as "no version", but `is_same_version`
  compares unparsable text exactly. `group_dependencies(['foo>=1',
  'foo===UNKNOWN', 'foo===unknown'], 'demo')` gives two `foo` groups
  (`unknown` and `UNKNOWN`) with one key `foo`: the second package gets the
  claim `WARNING:`, and harvest treats the key as ambiguous and never writes
  it. Share one placeholder predicate between the key and the grouping.
  `none` and `n/a` stay real versions (decided 2026-11-02, under Fixed).
  Suggested for 0.23.0; not done in it.
  *Found 2026-11-02, cold review of the merges since 0.22.0.*
- [ ] **`package_key` is not idempotent (low).** `package_key('x', '4+K')`
  (Kelvin sign) returns `x@4+K`; keying that again gives `x@4+k`, because NFC
  turns the sign into ASCII `K` after the version is parsed (200,000-case
  fuzz; the only failure). Masked today, as `_element_key` normalises again on
  every store and lookup, and an end-to-end run with `qux===4+K` was stable
  under `qux@4+k`; but the `_element_key` docstring claims idempotence.
  Apply NFC before `parse_version` in `package_version_key`. Suggested for
  0.23.0; not done in it.
  *Found 2026-11-02, cold review of the merges since 0.22.0.*

### Leads to verify

Seen in a review, not reproduced on current `main`:

- A phantom dependency that is another release of a declared dependency never
  looks up (S-M, from reading the code only). `_resolve_phantom_ids` skips
  any phantom whose name is in `seen`, which holds the dependency groups'
  canonical names. Keys now include versions, so phantom `foo 2.0` and
  dependency `foo 1.0` no longer share a key; yet the phantom mints a fresh
  id, counts as a non-reader and is left out of harvest, so it never gets a
  stable id. Fix: skip a phantom only when its claimed `package_key` is
  already taken, and keep the by-name rule for the project's non-PEP 508
  fallback only; a characterisation test first. Suggested for 0.23.0; not done
  in it.

## Fixed

Kept for history, with the PR. A fixed entry moves to
[roadmap-completed.md](../../implementation/roadmap-completed.md) once its
release ships.

### Fixed, P0: in 0.21.0

- [x] **Same AI model gets different ids per surface; enrichment can hit
  the wrong model (S-M).** Found in the #292 review (`loom model` looked a
  model up by file stem only, a project scan by name, path, then stem). Fixed
  by the path-key redesign on registry v3 (PR #305; K9, K10, K17 in
  [id-registry-path-keys.md](../../implementation/id-registry-path-keys.md)): one
  model rule on every surface, a model keyed by its file's path and gated by
  its SHA-256.

### Fixed, P1: registry v3 in 0.21.0 (some built, some not)

- [x] **A registry inside the scanned tree never settles.** Fixed by
  registry v3 (PR #305, D7): the declared registry is left out of the file
  set, with one `WARNING:` per run. (Was: each run hashed the registry as a
  project file, then rewrote it: 4 runs, 4 different SBOMs and registries.)
- [x] **A project under any `build/` directory indexes nothing.** Fixed
  by registry v3 (PR #305): the walk prunes ignored directory names below
  the scan root and `_skipped_name_in` checks an explicit PATH's
  project-relative parts. (Was: a check on the absolute path, so
  `loom id generate` wrote 0 files, silently.)
- [x] **Same-stem model files share one entity.** `a/model.gguf` and
  `b/model.gguf` got one `ai_AIPackage` key (Q-A: key by project path). Fixed
  by the path-key redesign (PR #305; K9 in
  [id-registry-path-keys.md](../../implementation/id-registry-path-keys.md)): a
  model is keyed by its file's path, two models with one stem have two ids.
- [x] **A package key without a version gives every release one id**
  (Q-D: PEP 503 name plus PEP 440 version). Fixed by #407: registry version 4
  keys a package `name@version` (a range by its resolved version); a version 3
  file is refused, never migrated.
- [x] **`normcase` does not fold case on macOS**, so a `same_path`
  helper built on it misses case variants. Fixed by registry v3 (PR #305):
  `core/walk_rules.same_path` falls back to `(st_dev, st_ino)`.

### Fixed, P3: after 0.20.0

- [x] **One person, two `Agent` elements (S, found in the 2026-10-23 release
  review; fixed in #353).** A model's `originatedBy` and a
  dataset's `publishedBy` naming the same person ("Alice" in the `library`
  conformance scenario) gave two `Agent` elements (`Agent-1`, `Agent-Alice-1`).
  Now one generic `Agent` per name, found through the exporter's agent index
  (`assemble/spdx3/_agents.py`, used by the model originators, the supplier and
  the dataset creator, on the assembler and `loom.run` routes). Every generic
  Agent's id carries its name (`Agent-<name>-1`; before, originators were
  `Agent-<n>`), so the id depends on neither the order the elements are built
  in (another model's dataset creator is built before this model's originators)
  nor on the Agents around it. A dataset creator is stripped, and a blank one
  names no one, as for an originator. Kept apart on purpose: the SBOM's own
  creators of type `agent` (never keyed), a main-package author and a
  dependency's author (a `Person` or `Organization`; the key includes the
  class).
- [x] **The registry harvest `INFO:` can print a negative count (S).** Fixed
  by registry v3 (PR #305): `added N new id(s)` counts distinct new ids.
  (Original report:)
  `_sync_registry()` (`assemble/_generators_shared.py`) logs `added %d
  new file(s), %d new entit(y/ies)` from the net counts of `harvest()`.
  Two library calls on the example project in a row printed `added 0 new
  file(s), -1 new entit(y/ies)`: a stale key released in the same pass
  makes the net count negative. Log gross additions, or the "updated stale
  entries" line when any count is not positive. Found while checking doc
  examples.

### Fixed, Found in review rounds, not yet prioritised

- [x] **A pointer's registry entry flipped between routes (M), fixed in
  #378.** Each harvest wrote its SBOM's hash, the `oid` (checkout) or the
  pointer text's digest (wheel, sdist, `--allow-build`), so alternating runs
  rewrote the entry and `id generate` after a wheel run minted. Now the
  registry holds the `oid` on every route and every lookup uses it.
  *Found 2026-10-29, Git LFS pointer work.*
- [x] **`none` and `n/a` do not count as "no version" (S).** Decided: no
  change (2026-11-02). `_NO_VERSION` in `id_registry/_types.py` holds only
  blank, `unknown` and `noassertion`; a package stating `none` or `n/a` is
  keyed as a release and stays so.
  *Found 2026-10-30, from #407 (registry package key).*
- [x] **`loom id generate -e %40scope/pkg@1.0` (an npm-style name) is
  refused (S), decided/changed in #429.** A `software_Package` NAME that is no
  PEP 508 name (a specifier, a space, `@scope/pkg`) exits 2 with the usage
  error `invalid package NAME`, since no lookup reads such a key; a NAME typed
  with `==` is told to write `NAME@VERSION`. Not a bug: an npm-style package
  has no PEP 508 name, so it cannot carry a package key until a non-PyPI
  ecosystem is decided.
  *Found 2026-11-03, review of the merges #426 to #429.*
