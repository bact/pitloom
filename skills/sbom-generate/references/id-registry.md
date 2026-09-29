---
Created: 2026-09-29
Last-Modified: 2026-09-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry: what it pins, how to create one, what its log lines mean

Companion to `../SKILL.md`'s "Pinning element ids" section, which holds the
rule that matters most: a registry is used **only when declared**. This
file is the detail behind it. Full command reference:
[docs/cli.md's "Pin ids across fragments"](https://bact.github.io/pitloom/cli/#pin-ids-across-fragments).

## What a registry pins

- **Files and directories**, keyed by path and content hash.
- **Packages** (`software_Package`, keyed by PEP 503 name): dependencies,
  and the project's own package for `project`, `wheel`, `embed-wheel` and
  the Hatchling hook. `env` pins dependency packages only; its root
  package is minted on every run.
- **AI models** (`ai_AIPackage`), keyed by name.
- **Per-document entities**: a harvest also writes the creator (`Person`
  or `SoftwareAgent`), `Tool` and licence-text entries. They carry that
  document's own ids, so a run into another document rewrites them; they
  are not something to pin.
- **Datasets** only through the Python SDK
  (`pitloom.loom.Run(..., id_registry=...)`, which ignores
  `[tool.pitloom]`), by path and content hash; index a dataset directory
  with `loom id generate <dataset-dir> -o <registry>`.

A package name held by several registry-reading elements of one document
(e.g. one dependency at two versions) is never written by a run, and `id
import` skips it. A name-keyed registry holds one id per name, so it can pin
only one holder: `loom id generate <PATH> -e NAME:software_Package -o
<registry>` pins the first claimant (order: main package, dependencies,
phantom dependencies). Every later run then logs the `registered for both`
`WARNING:` below for the other holder -- expected here, not a stale entry.
The pin goes into the **declared** registry; if none is declared, do not
create one -- tell the user. A self-referencing extra (`demo[x]`) and a
phantom dependency named like the project or another dependency never read
the registry, so they do not count as holders: the project's own package is
still pinned by a run.

## Create one

Only `loom id generate` and `loom id import` create or index a registry;
never hand-edit one. Run from the project directory (`PATH` and `-o`
resolve against the current directory; a `PATH` outside the project is an
`ERROR:`):

```bash
loom id generate <PATH...> -o loom-id-registry.json   # index files and AI models
loom id import <sbom> -o loom-id-registry.json        # reuse an SBOM's ids
```

- `-o`/`--id-registry` is required unless the project config already
  declares `id-registry`; without either, one `ERROR:`, exit 1.
- `PATH` is `src` (src layout) or the package directory (flat layout).
  With no `PATH`, whichever of `src`/`data`/`models` exist are used
  (`ERROR:` if none), so `-e` alone needs one of them or an explicit `PATH`.
- **Models**: `id generate` registers each AI model file under `PATH` by
  file stem, and `id import` registers each `ai_AIPackage` by its model
  name. A run never adds a model id. For one outside `PATH`, add
  `--entity <stem>` (no `:TYPE` means `ai_AIPackage`).
- **Packages**: `id generate` registers none. Seed them with one `project`
  run into a declared registry, with `id import <sbom>`, or by hand:
  `loom id generate <PATH> -e NAME:software_Package -o <registry>` pins a
  dependency's or the project's own package id (the `:software_Package`
  suffix is required).

A newly created, undeclared registry prints one of these lines -- relay it
verbatim (the second when the project already declares a different
`id-registry`: change that key, never add a second one):

```text
INFO: ID registry: to use this registry, add to [tool.pitloom] in pyproject.toml: id-registry = "<path>"
INFO: ID registry: to use this registry, change id-registry in [tool.pitloom] in pyproject.toml to: id-registry = "<path>"
```

For a `setup.cfg` project the table is `[tool:pitloom] in setup.cfg` and the
path is unquoted (`id-registry = <path>`): `setup.cfg` values are plain INI
strings. Relay that line verbatim too, quotes and all. Until the key is
added or changed, pass `--id-registry <file>` on each run.

Keep the registry file outside any directory the package build includes
(the project root, not `src/<package>/`): a registry inside it is itself a
hashed project file, so every run rewrites both the registry and the SBOM.

## Harvest: what writes to a registry

Only a **declared** registry is ever written; nothing creates one but `id
generate`/`id import` (below).

- **Writes back** newly minted ids: `project` (a directory or an sdist),
  `wheel`, `env` and `generate` (which dispatches to those). Stop it with
  `--no-update-id-registry` or `update-id-registry = false`.
- **Writes** by design: `id generate` and `id import`.
- **Reads, never writes**: `model`, `enrich`, `embed-wheel`, `wheel
  --embed` and the Hatchling build hook. `--update-id-registry` on a CLI
  command among them logs a `WARNING: Options: ...`.
- **Ignored**: Hugging Face targets ignore `--id-registry` (also a
  `WARNING:` if passed).

`ai_AIPackage` and `dataset_DatasetPackage` ids are never harvested.

## Log lines that are not a broken registry

- `INFO: ID registry: added N new file(s), M new entit(y/ies) to <path>` or
  `INFO: ID registry: updated stale entries in <path>` -- a run wrote into
  the declared registry.
- `INFO: ID registry: not imported (name held by several elements): NAME` --
  `id import` only; the SBOM holds several elements under that name, so no
  single id can be pinned for it.
- `INFO: ID registry: content changed for <path>; minting a new spdxId (old:
  <id>).` -- `id generate` re-indexed a file whose content differs from its
  entry, so it gets a new id; normal after an edit (a `project` run reports
  this as `updated stale entries` above).
- `WARNING: ID registry: <id> is registered for both X and Y; Y gets a new
  id` -- two elements matched entries carrying one id. The first claimant
  keeps the pinned id and the second mints a fresh one; it does not fail the
  run. Expected on every run when the pin was made for an ambiguous name
  (above); otherwise two registry entries share one id, usually a stale one
  -- mention it to the user.

A declared registry that is missing or invalid is different: one `ERROR:`,
exit 1, nothing written.
