---
Created: 2026-11-19
Last-Modified: 2026-11-19
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Namespace mixing in one SBOM

See also: [roadmap.md](../design/roadmap.md) ("Namespace mixing in one SBOM"),
[id-registry-followups.md](../design/id-registry-followups.md),
[id-registry-v3.md](id-registry-v3.md) (section 9, D8),
[id-registry-autosync.md](id-registry-autosync.md), the user
guide [docs/id-registry.md](../../docs/id-registry.md).

Status: ruled 2026-11-19: **document** (option D),
[PR #504](https://github.com/bact/pitloom/pull/504). Built as the "Namespaces"
section of `docs/id-registry.md` and `tests/id_registry/test_registry_namespaces.py`;
no code change, no change to any SBOM.

## What is seen

With an ID registry loaded, one SBOM holds ids from several namespaces:
`https://ids.example/ns#File-1` beside `https://spdx.org/spdxdocs/demo-<uuid>#Package-1`.

## Reproduction (2026-11-19, tree at #502)

A one-package project (`demo`, one dependency, one file under `src/`),
`--creation-datetime 2026-01-01T00:00:00Z`:

```text
loom id generate src -o reg.json --namespace https://ids.example/ns
loom project --id-registry reg.json -o out.json
```

Namespaces in `out.json` (count, type, namespace):

| ids | type | namespace |
|---|---|---|
| 1 | `software_File` (the one `id generate` registered) | `ids.example/ns` |
| 1 | `software_File`, 2 `software_Package`, `SpdxDocument`, `software_Sbom`, `Person`, `Tool`, `Relationship`, `Annotation`, licences | `spdx.org/spdxdocs/demo-980d...` |

The harvest after the run writes the second group into the registry as
`added 9 new id(s)`. A rerun gives the same mix. After a version bump plus a
new dependency (the document uuid changes), a third namespace appears:

```text
SpdxDocument, software_Sbom, 2 new software_Package   spdxdocs/demo-b51e...
software_Package (pinned by the harvest)              spdxdocs/demo-980d...
software_File    (pinned by id generate)              ids.example/ns
```

Without a registry every id is in the one `spdxdocs/demo-<uuid>` namespace.
`reg.json` itself then holds ids of both namespaces.

## Cause

Two id authorities, never reconciled:

1. `pitloom.core.models.generate_spdx_id(prefix, doc_name, doc_uuid)` mints
   every id the build creates, in `doc_namespace(doc_name, doc_uuid)` =
   `https://spdx.org/spdxdocs/<name>-<uuid>`. `doc_uuid` is content-derived
   (`compute_doc_uuid`: name, version, dependencies, Merkle root of the file
   set), so it changes with the content. ~25 call sites, all through
   `assemble/spdx3/document.py::build()`, so the CLI, the hook and the library
   behave alike.
2. `IdRegistry._mint_id` mints in `IdRegistry.namespace`: a random UUID4
   namespace (`IdRegistry.new`, D8), `--namespace IRI`, or the document id
   adopted by `id import`. It is reached only from `IdRegistry.register`,
   that is `id generate` and `loom` model/dataset registration.

A build asks the registry first (`session.lookup(...)`). A hit returns the held
id as stored; a miss falls back to authority 1, and the harvest stores that
id. So a registry holds, by design, the ids as first minted: its own
namespace for what `register` created, one `spdxdocs/...-<uuid>` per release
for what a build minted. Ids pinned across releases cannot change namespace,
so a registry run mixes them with the current document's.

Three related facts:

- `id import` adopts the SBOM's namespace as the registry's: the two agree
  only while the document uuid stays the same.
- `docs/id-registry.md` calls `--namespace` "a new registry's document
  namespace"; it does not govern the SBOM's document id nor any id a build
  mints. Only ids made by `id generate`/`register` carry it.
- `loom` run ids (`pitloom.loom`) use a fresh UUID4 `doc_uuid` per `doc_name`
  (model, dataset, script), so one fragment already spans several
  namespaces; this is the separate item "`pitloom.loom` run namespaces" in
  [id-registry-followups.md](../design/id-registry-followups.md).

No bug in the SBOM: any IRI is a valid `spdxId`, `spdx3-validate` passes, and
output stays deterministic. The cost is confusion, and `--namespace` not
doing what a user expects.

## Options

**D. Document (ruled).** Ids are opaque IRIs. State in
`docs/id-registry.md`: a registry pins an id as first minted; a new id of a
build is minted in the document's namespace; the registry namespace is the
one `id generate`/`register` mint in (reword `--namespace`: not "document
namespace"). Add a "Namespaces" paragraph to the registry guide and a test
that pins today's behaviour (file in the registry namespace, the rest in the
document's) on CLI, library and hook. No code change, no change to any
SBOM.

**M. Unify mints of registry-tracked types.** With a registry loaded, a
miss for a type the registry holds (file, package, AI package, dataset,
agent, tool, person, licence) mints in the registry's namespace instead of
the document's. One shared mechanism in `generate_spdx_id`, bound per
`doc_uuid` by `build()` (as `reserve_spdx_ids` already is), so the 25 call
sites do not change. Gain: `--namespace https://ids.example/ns` really puts the
project's stable ids there, and the harvest stops accumulating a namespace per
release. Cost: counters of the two authorities share one namespace (the
registry's `id_counters` and `generate_spdx_id`'s per-document counter must
agree, run to run and across fragments); the merge rule "the namespace more
inputs share" reads the registry's; `loom` has its own `doc_uuid`; embed-wheel
and every `id import`ed registry need the same sweep. Document-level ids
(`SpdxDocument`, `software_Sbom`, `Relationship`, `Annotation`) must stay
per-document, since an `SpdxDocument` id is its namespace and two releases
may not share one. So the SBOM still holds two namespaces.

**U. Everything in the registry namespace** (also `SpdxDocument`). Rejected:
two releases' `SpdxDocument` would share an id.

## Ruling

D (2026-11-19). M cannot remove the mix (document-level ids, ids pinned
earlier, ids imported from elsewhere stay), touches the mint, harvest and
merge paths on every surface, and the gain is a project-owned namespace for a
user who asks for one. If a user needs that, build M as its own PR with the
surface x member matrix first.

## Why the registry namespace is a random UUID4

Asked during the ruling: why not a content-derived uuid, as
`compute_doc_uuid` gives the document? (D8 in
[id-registry-v3.md](id-registry-v3.md).)

- A content uuid is a *document* identity: name, version, dependencies, lock
  pins and the file set all move it. The registry namespace is a *project*
  identity: every pinned id carries it, and `id_counters`/`reserve_id` key on
  it, so it must not move between releases.
- The registry exists before any content (`id generate` first), so there is
  nothing to derive it from.
- A name-derived `uuid5(PITLOOM_NS, project_name)` is stable but shared by
  two projects with one name; SPDX ids must be globally unique (rejected in
  D8).
- The random value is drawn once and stored, so the registry is an input and
  a committed registry gives bit-for-bit identical SBOMs. A reproducible
  choice is `--namespace IRI`.

Tests: `test_registry_namespaces.py` runs every registry-reading surface of
the path-key guard (CLI, library, hook, `allow-build`, sdist, wheel,
embed-wheel). It asserts a held id keeps the registry namespace, the
`SpdxDocument` id is never in it, the SBOM holds exactly one other
(document) namespace, and without a registry there is one namespace. It pins
behaviour and passes on the base tree, since nothing changed in code.
