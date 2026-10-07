---
Created: 2026-10-07
Last-Modified: 2026-10-07
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry

See also: [SBOM fragments](fragments.md) (how fragments merge),
[Configuration](configuration.md) (`id-registry`, `update-id-registry`) and
[GitHub Action](github-action.md#persisting-the-loom-id-registry-in-ci)
(keeping a registry current in CI).

Fragments come from independent runs, so the same dataset or model would
normally get a different `spdxId` in each, leaving the merged SBOM as
disconnected islands. A **Loom ID registry** pins ids so every run, on every
surface, agrees.

## Declare a registry

A registry is used only when declared. Nothing is searched for or
auto-discovered on any surface: every CLI subcommand, the Hatchling build
hook, the library API (including `loom.Run`) and the GitHub Action.

```toml
[tool.pitloom]
id-registry = "loom-id-registry.json"
```

Precedence: `--id-registry FILE` (`id_registry=` in the API, `id-registry`
input in the Action), then the applicable config's `id-registry` key (the
project's own `[tool.pitloom]`, or a `--config` file), then no registry,
silently. A relative `--id-registry` resolves against the current directory
on every command.

A declared registry that is missing, unreadable or invalid is fatal: the CLI
prints one `ERROR:` line and exits 1; the library API and `loom.Run` raise
`ValueError`; the Hatchling hook logs one `ERROR:` and fails the build.

## Create a registry

```bash
loom id generate data src --entity model -o loom-id-registry.json   # pin ids before a run
loom id import existing-sbom.spdx3.json -o loom-id-registry.json    # or reuse ids from an SBOM
loom project                                                        # uses the declared registry
```

`id generate [PATH...]` takes `-o`/`--id-registry FILE` (registry to create or
update), `--project-dir DIR` and repeatable `-e`/`--entity NAME[:TYPE]` (an
explicit entity id ahead of a run; `TYPE` defaults to `ai_AIPackage`).
`--entity NAME:software_Package` pins a dependency's, or the project's own,
package id. `id import SBOM_FILE` takes only `-o`/`--id-registry FILE`.

**Target file.** `-o`/`--id-registry` if given, else the config's
`id-registry` key (`generate`: read from `--project-dir`; `import`: from the
current directory; `pyproject.toml`'s `[tool.pitloom]` or `setup.cfg`'s
`[tool:pitloom]`). The location is required, never assumed: with neither,
both commands print `ERROR: no ID registry declared: pass --id-registry FILE
or set id-registry in [tool.pitloom]` (`[tool:pitloom]` for `setup.cfg`),
exit 1 and write nothing. `loom-id-registry.json` is only the suggested name.
A broken `pyproject.toml`/`setup.cfg` is one `ERROR:` line, never a
traceback, and takes precedence over that error.

- A missing target is created. An existing target that cannot be loaded (not
  JSON, wrong version) is one `ERROR:` and exit 1, never silently replaced.
- Registry keys, and the default `PATH`s (`src`, `data`, `models`), stay
  relative to `--project-dir`; a relative `-o` or `PATH` resolves against the
  current directory.
- Each `PATH` must resolve inside `--project-dir`, else `ERROR: PATH <p> is
  outside --project-dir <dir>` (exit 1), whether directly or only through a
  symlink. `..` is collapsed lexically before any symlink is followed. A
  symlink that itself lives inside the project is fine even if it points
  outside (`data/models -> ../bigdisk/models`): it is indexed under its
  in-project location, as the default `PATH`s are.
- After a write that *created* the registry (never one that updated an
  existing file), and unless the target is already the project's declared
  `id-registry`, both commands log `INFO: ID registry: to use this registry,
  add to [tool.pitloom] in pyproject.toml: id-registry = "<path>"`. If the
  table declares a different `id-registry`, the line reads `change
  id-registry in [tool.pitloom] ... to:` instead (replace the key; a repeated
  key is invalid TOML). For `setup.cfg` it names `[tool:pitloom] in
  setup.cfg` and the path is unquoted, as INI values are not unquoted on
  read. Paste the `id-registry = ...` part verbatim.

## What a registry pins

Given the same registry, a file, directory, dependency package, the
project's own package (`project`, `wheel`, `embed-wheel`, the Hatchling hook)
or an AI model carries the same id everywhere. `env` reuses a dependency's
id only.

Exceptions:

- A `src/`-layout project's files are not found by `wheel` or sdist targets
  (their paths differ from the project's).
- A `loom.Run` dataset is looked up by file path and hash. Datasets found at
  build time and `env`'s root package are not looked up, so a registry entry
  does not pin them.
- Regeneration is stable: an unchanged file keeps its id; changed content
  gets a fresh one (different bytes are different provenance).
- A package name held by two elements of one document that both read the
  registry (two versions of a dependency behind different markers) cannot be
  pinned automatically: runs do not record it, and a pinned id goes to the
  first of them, with a `WARNING:`. `loom id import` skips every name held by
  several elements, with one `INFO:` line.
- A self-referencing extra, or a bundled library named like the project or a
  dependency, never reads the registry and silently gets its own id; runs
  still record the name for the project or dependency.

## Harvesting new ids

`loom project`/`wheel`/`env` also write newly minted ids back into a
*declared* registry after each run (`--update-id-registry`, on by default;
`--no-update-id-registry` to stop; never creates a registry). Running `loom
project`, then `loom wheel --id-registry loom-id-registry.json` and `loom env
--id-registry loom-id-registry.json`, keeps the same spdxIds with no manual
`id generate`/`import` between them. A name held by several elements of one
document is not written.

`ai_AIPackage` and `dataset_DatasetPackage` are the exceptions. Register AI
models with `loom id generate`: their stable key, the model file's stem,
cannot safely come from auto-harvest. Datasets found at build time are not
registry-consulted, so harvesting them would only write dead entries.
