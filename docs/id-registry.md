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
[GitHub Action](github-action.md) (the `id-registry` and
`update-id-registry` inputs).

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

## From Python

The `id_registry=` argument (a path, or an already-loaded `IdRegistry`) is the
library equivalent of `--id-registry`, taken by the generator functions,
`embed_wheel_sbom()`, `enrich_model()` and `loom.run`. Precedence:
`id_registry=` wins over the applicable config's `id-registry` key, which
wins over no registry at all (silently). A relative `id_registry=` path
resolves against the project directory for a project directory target
(and `embed_wheel_sbom(project_dir=...)`, and `enrich_model(project_target=dir)`
-- the project the enrichment fragment will merge into), and against the
current directory for any other target, an sdist included. The CLI makes
`--id-registry` absolute against the current directory first, so there
it always means the file under the current directory. A declared
registry file that's missing, unreadable or invalid raises `ValueError`
(`"ID registry file <path>: <reason>"`) rather than being silently
skipped or replaced. `loom.run` never reads a `[tool.pitloom]`, so it takes only
its own `id_registry=`, resolved against the current directory.

## In CI

A registry is used only when declared: via the Action's `id-registry` input, or
via `[tool.pitloom] id-registry` in the project's own config. Nothing is
auto-discovered. Once declared, `loom project`/`wheel`/`env` (and this
Action, which wraps them) harvest newly-minted ids back into it by
default -- see `update-id-registry` in [Configuration](configuration.md).
That write only ever touches the runner's local checkout; it never needs
elevated permissions itself
(that's a `git push`, which Pitloom never does). But the write is
ephemeral unless a workflow step commits it back, so a release/publish
job that intentionally runs with `permissions: contents: read` (common
for trusted PyPI publishing -- see this repo's own
[`pypi-publish.yml`](https://github.com/bact/pitloom/blob/main/.github/workflows/pypi-publish.yml))
can update `loom-id-registry.json` locally but shouldn't have its permissions
relaxed just to push that one file.

Instead, run registry maintenance in a separate, appropriately-scoped
workflow -- the same shape this repo already uses to commit a generated
`CITATION.cff` back to the repo
([`codemeta2cff.yml`](https://github.com/bact/pitloom/blob/main/.github/workflows/codemeta2cff.yml)).

A declared `id-registry` that does not exist yet is an `ERROR:`, not
silently skipped, so the registry file must exist before the build
step below runs. Either commit one made by `loom id generate`
(recommended, so every build reads the same committed file) or keep the
seed step in the snippet below (it also creates the file on its first
run, so the very first workflow run still succeeds):

```yaml
name: Update Loom ID registry

on:
  push:
    branches: [main]
    paths:
      - "src/**"
      - "data/**"
      - "models/**"

permissions: read-all

concurrency:
  group: update-loom-id-registry-${{ github.ref }}
  cancel-in-progress: false

jobs:
  update-id-registry:
    runs-on: ubuntu-latest
    permissions:
      contents: write  # EndBug/add-and-commit needs write to push loom-id-registry.json
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.x"
      # Same release as the action below, which installs its own pinned version.
      - run: pip install pitloom==0.20.1

      # Extras-free, stem-keyed -- the only path that keeps ai_AIPackage
      # spdxIds stable regardless of whether "ai" extras are installed
      # (auto-harvest excludes AI packages -- see below). Creates
      # loom-id-registry.json on first run. Only omit this step if a
      # loom-id-registry.json is already committed to the repo -- a
      # declared-but-missing registry now fails the step below.
      - name: Seed/refresh AI model registry entries
        run: loom id generate --id-registry loom-id-registry.json

      - uses: bact/pitloom@v0.20.1
        with:
          project-path: .
          # Required: nothing auto-discovers a registry -- declare it.
          # Must already exist by this point (the seed step above
          # creates it on first run) -- a declared-but-missing registry
          # is an ERROR:, not silently skipped.
          id-registry: loom-id-registry.json
          # Optional: richer ai_AIPackage metadata (architecture,
          # hyperparameters, etc.) -- NOT what keeps spdxIds stable, that's
          # the step above. Omit if there are no AI models, or if sparse
          # metadata is acceptable.
          extras: "ai"

      - name: Commit and push updated loom-id-registry.json
        uses: EndBug/add-and-commit@v11.0.0
        with:
          message: "Update loom-id-registry.json"
          add: "loom-id-registry.json"
```

Two things worth calling out about that snippet:

- **AI model id stability doesn't come from `extras: "ai"` or from
  auto-harvest at all.** `ai_AIPackage` elements are deliberately excluded
  from auto-harvest, because their correct registry key is the model
  file's stem -- which only ever comes from the extras-free
  `loom id generate` step above. `extras: "ai"` only affects metadata
  richness (architecture, hyperparameters, etc.), not which spdxId a model
  gets.
- **Race conditions**: this workflow never competes with the publish
  workflow to push (the publish job doesn't commit, per the guidance
  above). It can race with *itself*, though -- two pushes to `main` close
  together could trigger two concurrent runs both trying to commit and
  push. The `concurrency:` group above queues same-branch runs instead of
  racing them. One sequencing caveat remains, shared by any
  generated-and-committed file (this repo's own `CITATION.cff` included):
  cutting a release at the exact moment a registry-update commit is in
  flight could still pick up a slightly-stale `loom-id-registry.json`.
