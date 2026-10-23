---
Created: 2026-10-16
Last-Modified: 2026-10-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry: keys and content gates

See also: [Loom ID registry](id-registry.md) (declare, create and harvest a
registry), [Wheel SBOMs](wheel-sbom.md) and
[Python API](python-api.md#tracking-decorator) (`loom.Run`).

A registry entry maps a **key** to an `spdxId`. What a run looks up, and what
`id generate`, `id import` and a harvest write, is the key below. One helper
computes every key, so the surfaces agree.

## What a key is

| Element | Key |
| --- | --- |
| `software_File` | Its path from the registry's project root. A directory is the exception: it is keyed by its distribution path (`demo`, not `src/demo`), and `id generate` does not index directories |
| An AI model that has a file | The same path, the key of the model file's own `software_File` |
| A `loom.Run` dataset package whose path exists below the root when declared | Its path from the root |
| A package (dependency or the project's own), a Hugging Face or other pathless model, a remote, missing or outside-the-root dataset | Its name (PEP 503 for a package) |

A path key is `/`-separated and relative to the project root the registry
stores. It is Unicode NFC and is never case-folded. A path you type (a `loom.Run`
path, the `model` or `enrich` argument, `id generate PATH`, `-e`) keeps the
spelling the file has on disk, so `Data/T.txt` typed for `data/t.txt` finds the
same entry on a case-insensitive file system. Two files whose names differ
only by NFC/NFD are both skipped by `id generate`, with one `WARNING:`; a key
read from a registry in NFD loads as NFC.

**One model file is one id on every surface**: `project`, `--allow-build`,
`wheel`, `embed-wheel`, the Hatchling hook, the library API, `model`,
`enrich`, `loom.Run` (`set_model`/`use_model`), `id generate` and `id import`.
Two models with the same file stem are two models with two keys. A model has
no key of its own beside its file's: a loom name that differs from the file's
stem adds none (the merged `ai_AIPackage` takes the loom name and keeps the
file key's id).

## Content gates

A **model** lookup is gated by content. The `ai_AIPackage` carries the model
file's SHA-256 (and its SHA-512) as `verifiedUsing` (every route that reads the file;
`enrich`, which makes no `ai_AIPackage`, uses only the gate), and the registry
entry records the SHA-256. Retrained bytes at the same path get a new id. `project`, `wheel`, `model` and
the other generating routes say `INFO: ID registry: model <name>: no registry
entry records its SHA-256; a new id is used` when an entry exists under the key
but records no, or another, hash; `id generate` and `loom.Run` say `content
changed` instead ([log lines](#fallbacks-print-info)). An entry with no hash
never matches a model.

A **dataset package** has a hybrid gate:

- An entry with a SHA-256 is content-gated: the file's SHA-256, or a
  directory's Merkle root, the digest the package's `verifiedUsing` holds. A
  refreshed dataset is a new package id, and adding a file to a directory
  dataset changes its root, so it is a new id too.
- An entry with no SHA-256 is a pin made before the data existed (or by an
  older registry) and hits any content, with `INFO: ID registry: dataset <x>
  matched a pin without SHA-256; content not checked`.

Scenario. `loom id generate -e data/train.csv:dataset_DatasetPackage` before
`data/train.csv` exists pins the name with no hash: the first run that writes
the file keeps the pinned id whatever its content. Pinning a file that
already exists gates it: `id generate -e` stores the canonical path key and the
digest, so a later change to the file is a new package. Running the same `-e`
again once the file exists adopts its digest into the hash-less pin and keeps
the id (`INFO: ID registry: dataset <key> pin now gated by its SHA-256`); an
entry that records another digest gets a new id (`content changed`). `id
import` of a `loom.Run` fragment likewise records the dataset package digests
(a run's own harvest never writes a dataset).

One package exists per key and digest in a run when the path exists below the
registry root at declaration: `data/t.txt`, `./data/t.txt`, `../data/t.txt`
from `scripts/`, an absolute path, another case and NFC or NFD spellings are
all one package. A missing, remote or outside-the-root dataset is keyed by the
exact string, so two spellings of it are two packages.

`input_datasets=` is not matched through the key: it matches the spellings the
input was declared under. After `add_input_dataset("../data/t.txt")`,
`input_datasets=["data/t.txt"]` logs a `WARNING:` and skips the link.

## Layout alias

A wheel or built archive names `demo/x.py` where the project holds
`src/demo/x.py`. To reuse one id for both, a lookup may also try the other
layout's key, under these rules:

- Only a leading `src/` or `lib/` part is cut or added, one part, with two parts
  left. `python/`, `packages/` and others get no alias: a wheel-only run mints
  its own ids for those files (two keys).
- The two keys must hold equal SHA-256 digests. A key with no hash never hits
  through an alias.
- The candidate must be unique. A tie is a miss, with one `INFO:`.
- The shorter key must not exist as a real file or directory under the
  registry root: two real files are never aliases.
- `*.data` wheel members are never aliased.

Worked example, wheel first. `loom wheel` of a built wheel mints and records
`demo/x.py`. A later `loom project`, which looks up `src/demo/x.py` by its
canonical key, hits the held `demo/x.py` (same SHA-256), keeps its id and the
harvest replaces the held key with `src/demo/x.py`; one key per id, always.
Reverse: `loom id generate` records `src/demo/x.py`; a later `loom wheel`
looks up `demo/x.py`, hits the held key through the alias and leaves the held
key as it is, with one `INFO: ID registry: N element(s) matched a registry key
through the src/lib layout alias` per document. `id generate` over a
registry that holds an alias key promotes it to the canonical key (`INFO: ID
registry: N key(s) promoted from a layout alias`). It does so too when the
canonical key holds older content and the alias the current one (an edit a
wheel run saw first), as a `loom project` lookup would: the alias's id
replaces the changed key's, so project and wheel keep one id (`INFO: ID
registry: N key(s) of changed content took their layout alias's id`). Typed
paths (`loom.Run`, `model`, `enrich`) look up the canonical key, so they
reuse a wheel-minted id.

## Monorepo

When the registry's root is above the project (`pkgs/demo` below it),
`project` on a directory, the hook, `--allow-build`, and `wheel`,
`project <sdist>` (`generate` on either) and `embed-wheel` given `--project-dir
pkgs/demo` (`project_dir=`) key below the project's prefix
(`pkgs/demo/src/demo/x.py`), and the layout alias applies below it. A member
only the archive holds (`PKG-INFO`, a wheel's `.data` file) is keyed below the
prefix too.

An archive read without `--project-dir` has no project: it keys by the
archive's own paths, which miss a registry rooted above the project, with no
`INFO:` and root-level keys harvested. A registry whose root is the project's
root works on every surface. A file the build force-includes from outside the
project but inside the root is keyed from the root. Under `--allow-build`, a
built file with no source path cannot match its `id generate` key.

When a document's files cannot be keyed from the root, they are keyed by the
path as read, with one `INFO: ID registry: N file(s) keyed by their path as
read: <reason>`; a `--project-dir` outside the registry's root is one such
reason (`the project is outside the registry's root`).

## `-e NAME[:TYPE]`

`NAME` resolves against `--project-dir`, not the directory the script ran in.
For `dataset_DatasetPackage`, `ai_AIPackage` and `software_File`, a `NAME` that
is an existing regular file (a dataset: a file or a directory) below the
project root is stored under its canonical path key, with its digest. When the
key differs from the text typed, `INFO: ID registry: -e <name> stored as <key>`.
Any other `software_File` or `ai_AIPackage` name is stored by name with
`INFO: ID registry: -e <name> stored by name: <reason>` (`not found`, `outside
the project root`, `not a regular file`; an `ai_AIPackage` name applies only to
a model with no file, a Hugging Face id). A dataset that is missing, outside
the root or cannot be hashed is stored by name with no hash, with `INFO: ID
registry: dataset <name> pinned without SHA-256: <reason>`. A
`software_Package` and the other types are stored verbatim. A script that runs
from `scripts/` and declares `../data/t.txt` is looked up as `data/t.txt`:
pin `-e data/t.txt:dataset_DatasetPackage`, the path from the project root.
The script's own string matters only for a dataset with no path below the root.

## `id import`

- The registry's root is `--project-dir` (default: the current directory), as
  for `id generate`, and the SBOM's file names are keys below it. An SBOM does
  not record its project's directory, so import from above the project without
  `--project-dir` gives keys that a run of the project does not look up. An
  existing registry keeps its root: `--project-dir` naming another one is an
  `ERROR:`.
- A model takes the key of the unique `software_File` in the same SBOM with
  the same SHA-256; else the key of the one registry file entry recording that
  SHA-256 (`INFO: ID registry: model <name> keyed by the registry's file with
  its SHA-256: <key>`); otherwise it is imported under its name, with `INFO:
  ID registry: model <name> imported under its name: no unique file with its
  SHA-256`.
- A dataset package is keyed by the path of its one same-hash file in the SBOM,
  else by its name, when that exists below the root or the current directory;
  it gets its digest. When the key differs from the name, one `INFO: ID
  registry: dataset <name> keyed by its path: <key>` says so. A name found
  nowhere stays a name key: `dataset <name> keyed by its name: not found: declare paths
  relative to the registry root (id import --project-dir) or run id import from
  the directory the script ran in`.
- A file whose key is not held with its SHA-256, but whose layout alias is
  (one held key with its SHA-256), is imported under that held key, counted in
  the layout-alias `INFO:`. When its own key holds other content, that key
  keeps its entry and one `INFO: ID registry: N file(s) imported under their
  layout alias: their own key holds other content` says so.
- An element whose id is held under another key of its type, one no other
  element of the SBOM moves, is not imported: `INFO: ID registry: <type>
  '<key>' not imported: its id is held under '<held key>'`. This is decided
  before anything is written, so importing the same SBOM again changes
  nothing.
- A name held by several elements is skipped, as before.

## Fallbacks print `INFO:`

Every deviation from the key rules prints one `INFO: ID registry: ...` per
document, element or pin, never per file in a loop. `grep 'ID registry:'` over
stderr lists them:

| Event | Line (after `INFO: ID registry: `) |
| --- | --- |
| Files not keyable from the root | `N file(s) keyed by their path as read: <why>` |
| Layout alias used | `N element(s) matched a registry key through the src/lib layout alias` |
| `id generate` promotes a held alias | `N key(s) promoted from a layout alias` |
| `id generate` replaces a changed key by its alias | `N key(s) of changed content took their layout alias's id` |
| Model refused by the gate (`project`, `model`, `wheel`, ...) | `model <name>: no registry entry records its SHA-256; a new id is used` |
| Content changed (`id generate`, `loom.Run`) | `content changed for <key>; minting a new spdxId (old: <id>)` |
| `loom.Run` or `model` hashed model keyed by its name | `model <name> keyed by its name: <why>` |
| Dataset by name, or ungated | `dataset <key> keyed by its name: <why>`, `dataset <key> looked up ungated: not hashed` |
| Pin with no hash | `dataset <name> pinned without SHA-256: <why>`, `dataset <key> matched a pin without SHA-256; content not checked` |
| Pin adopts a digest | `dataset <key> pin now gated by its SHA-256` |
| `-e` decisions | `-e <name> stored as <key>`, `-e <name> stored by name: <why>` |
| `id import` decisions | the model and dataset lines above, `<type> '<key>' not imported: its id is held under '<held key>'`, `N file(s) imported under their layout alias: their own key holds other content` |
| Harvest leaves a gated entry | `content gate kept for <type> '<key>': harvested id <id> not recorded over <held>` (or `element id <id> with an older SHA-256 not recorded over <held>`) |
| Hashed model not recorded | `model <name> not recorded: no unique file with its SHA-256` |

A `loom.Run` lookup that finds an entry whose SHA-256 no longer matches says
`WARNING: loom: registry entry for <model|dataset package|file|entity> '<key>'
exists but its SHA-256 no longer matches; minting a new spdxId (content
changed)`, naming the element type because a dataset package and its file
share a key.

## Merged fragments and harvest

A harvest writes each element under the key its lookup used. An element with
no recorded key (a merged loom fragment, `id import`) follows three rules:

- It never moves an id held under another key of its type.
- A stale element, whose SHA-256 is older than the entry's, never rolls the
  newer entry back: the entry stays and the line above says so.
- A hashed model is recorded only under the key of its one same-hash file in
  the document; with none, it is not recorded.

`id import` of a loom fragment keys its datasets and models by their same-hash
file, as above. Each document (`project`, `wheel`, `env`, `model`, `enrich`, the hook and
`embed-wheel`) reserves every id the registry holds for a file, package, AI
package or dataset package, whether it looked it up or not, so an id minted on
a miss is never one another key holds. Not reserved: agents and tools, whose
ids are the same every run; the id held under a model card dataset's name; and,
for `model` and `enrich`, the id held under the model's own name (the key `id
import` writes for a `loom model` SBOM).

## What changed for an existing registry

The file's shape is unchanged (`version: 3`), but these entries stop matching:
a model pinned by its stem or own name (`-e STEM:ai_AIPackage`), a dataset
pinned by a string that differs from the canonical path (`./data/t.txt`),
a wheel-only lookup of a file a hatch `sources` remap moved by more than one
part, and a file named by a raw un-normalised archive member name. A registry
written by a pre-release v3 build is regenerated (`loom id generate`), and ids
may renumber once. A retrained model logs `ID registry: content changed for
...; minting a new spdxId` for the file and for the package.
