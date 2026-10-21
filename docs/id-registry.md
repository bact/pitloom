---
Created: 2026-10-07
Last-Modified: 2026-10-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry

See also: [Keys and content gates](id-registry-keys.md) (what an entry is
keyed by), [SBOM fragments](fragments.md) (how fragments merge),
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
explicit entity id ahead of a run; `TYPE` defaults to `ai_AIPackage`). A
file, model or dataset `NAME` that exists below the project root is stored
under its path key with its content hash, other names by name, each with an
`INFO:` ([`-e` rules](id-registry-keys.md#-e-nametype)).
`--entity NAME:software_Package` pins a dependency's, or the project's own,
package id. The string splits on its last colon: the suffix is a `TYPE` only
when it is a known registry type (`software_File`, `software_Package`,
`ai_AIPackage`, `dataset_DatasetPackage`). A suffix shaped like a type name
(`prefix_ClassName`) or a known type in another case is a usage error (exit
2), not part of `NAME`. Anything else is part of `NAME`, so a URL or a
Windows drive path works, as in
`-e https://huggingface.co/datasets/imdb:dataset_DatasetPackage`. A trailing
`:`, a `TYPE` with white space around it, a control character (a newline) or a
blank `NAME` is a usage error too.
`--namespace IRI` sets a new registry's document namespace (an
absolute IRI without `#`; default: the project name and a random UUID4); an
existing registry with another namespace is one `ERROR:`, exit 1. A
registry whose `namespace` is not a valid namespace IRI, or whose `spdxId`
is not a non-empty string, does not load. `id import` into an empty
registry adopts the SBOM document's namespace only when it is a valid
namespace IRI; otherwise one `WARNING: ID registry: not adopting the
namespace ...` and the registry keeps its own. It keeps the namespace it
adopted unless another run changed the file's namespace meanwhile.
`id import SBOM_FILE` takes only `-o`/`--id-registry FILE`.

A new registry stores its project root (`--project-dir` for `generate`, the
current directory for `import`) relative to its own directory; an existing one
keeps it, and `generate` with another `--project-dir` is one `ERROR:`, exit 1.
The registry also keeps, per id prefix, the highest number it has issued or
read in its namespace (`id_counters`), so an id that has left the registry
(a harvest replaced its entry) is never minted again for another file. An id
handed over by an SBOM, a harvest or `id import` reserves numbers only up to
10**9, and one whose prefix is not a valid IRI segment (it holds `/`, `?`, a
space, `#` or a lowercase `%xx`) reserves nothing. A document also skips
every id the registry holds for a file, package, AI package or dataset package
when it mints one, so a new id never equals a held one; a model card's dataset
keeps the id held under its own name. A file whose `version` is not an
integer (`3.0`) or that repeats a JSON object key (`duplicate key 'X'`) does
not load. For a symlinked registry, `project_root` is relative to
the symlink target's directory.
`generate` records each AI model file's SHA-256 with its entry, so a
retrained file (other bytes) gets a new id on every surface. A registry from an earlier release (format version 2) is
rejected, on every command, with one `ERROR:` and nothing written; delete it
and re-run `loom id generate` or `loom id import`.

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
  JSON, wrong version, a version 2 file) is one `ERROR:` and exit 1, never
  silently replaced.
- Registry keys, and the default `PATH`s (`src`, `data`, `models`), stay
  relative to `--project-dir`; a relative `-o` or `PATH` resolves against the
  current directory.
- `--project-dir` must be an existing directory, else `ERROR: --project-dir <p>
  is not a directory` (exit 1). Each `PATH` must resolve inside it, else
  `ERROR: PATH <p> is outside --project-dir <dir>` (exit 1), whether directly
  or only through a symlink. `..` is collapsed lexically before any symlink
  is followed (`link/..` is the directory above `link` as written). A symlink
  that itself lives inside the project is fine even if it points outside: it
  is indexed under its in-project location, as the default `PATH`s are,
  and a `PATH` naming a symlinked *directory* (`data/models ->
  ../bigdisk/models`) is walked. A symlink to a directory found *below* a
  `PATH` is not followed. A `loom.Run` that names a file below a symlinked
  directory keys it by its path as written, so it finds no entry.
- A file or directory below a `PATH` that cannot be read or listed gets the
  shared `WARNING: FILE=<path>: ...` or `WARNING: DIR=<path>: ...` line (the
  path project-relative, `/`-separated) and the run continues; a partial tree
  is never indexed silently. So does a file whose name a registry cannot hold
  (not UTF-8 encodable). A `PATH` argument itself that cannot be read or
  listed is `ERROR: PATH <path>: could not be read: <reason>` (exit 1, nothing
  written) on every Python version; an unreadable default directory (`src`,
  `data`, `models`) is the `DIR=` warning instead.
- Build, virtual-environment, VCS and cache directories are not indexed; see
  [Directories that are skipped](#directories-that-are-skipped). A `PATH`
  that is, or lies below, one of them indexes nothing and gets one
  `WARNING:`.
- `-o -` is a usage error (exit 2): a registry is never written to stdout.
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

Given the same registry, a file, dependency package, the project's own
package (`project`, `wheel`, `embed-wheel`, the Hatchling hook) or an AI model
carries the same id everywhere. `env` reuses a dependency's id only. A file, a
model that has a file and a dataset package that exists below the root are
keyed by their path from the registry's project root, everything else by name;
a file's or model's entry holds its SHA-256, so changed content gets a new id;
one model file is one id on every surface. A directory is the exception: it is
keyed by its distribution path (`demo`, not `src/demo`) and `id generate` does
not index it. Details: [Keys and content gates](id-registry-keys.md).

Exceptions:

- A wheel whose name did not come from its `METADATA` (called `unknown`) is
  neither looked up nor recorded; its package gets a per-document id, with
  one `INFO:` when a registry is declared. Its ids depend on its file name, so
  a renamed copy gets new ids: see [Wheel SBOMs](wheel-sbom.md#what-an-sbom-lists).
- A `src/`- or `lib/`-layout project's files are found by `wheel` and sdist
  targets through a [layout alias](id-registry-keys.md#layout-alias); other
  layouts get their own ids from a wheel-only run. With the registry's root
  above the project, `wheel`, `project <sdist>` and `embed-wheel` need
  `--project-dir` to find it: see [Monorepo](id-registry-keys.md#monorepo).
- A `loom.Run` dataset package whose path exists below the registry's root is
  keyed by that path, whatever way the script spells it (`../data/t.txt` from a
  subdirectory is `data/t.txt`); a remote, missing or outside-the-root dataset
  by its name. A dataset that is one file also gets a `software_File` under
  the same path key. Datasets found at build time and `env`'s root package are
  not looked up, so a registry entry does not pin them.
- Regeneration is stable: an unchanged file keeps its id; changed content
  gets a fresh one (different bytes are different provenance). That holds for
  an AI model on every surface: the model's file is its key and its SHA-256
  gates the lookup, so a retrained file is a new id. Two model files with one
  stem are two models with two ids. A dataset pin with no recorded SHA-256
  hits any content: see [Content gates](id-registry-keys.md#content-gates).
- A registry inside the project tree is left out of the SBOM's file set
  (and of a wheel's Merkle root), with one `WARNING: ID registry: <path> is
  inside the project's file set; left out of it` per run when the file set
  actually contains it; `id generate` does not index it either. With
  `--allow-build`, the copy found in the build-and-read extraction is left
  out too (recognised as a file the build extracted, wherever `TMPDIR` is,
  with an equal SHA-256). The copy a built wheel or sdist carries is left out
  by `wheel`, `embed-wheel` and `project <sdist>`, whatever its bytes. A wheel
  member is the copy only when its path equals the registry's path below the
  project, or that path less exactly one leading part (a `src/` layout), with
  a directory and the file left; of several such members only the longest is
  left out, and a file with a shorter tail (`reg.json`, `data/reg.json`) is
  kept. An sdist member must match the whole path below `name-version/`. The
  path is taken below `--project-dir`; without one (`wheel`, `embed-wheel`,
  `project <sdist>`) below the nearest directory that holds
  the registry and a `pyproject.toml`, `setup.cfg` or `setup.py`, no higher
  than the project root the registry stores, else below that root. Keep the
  registry outside the package directory (the project root is fine).
- A package name held by two elements of one document that both read the
  registry (two versions of a dependency behind different markers) cannot be
  pinned automatically: runs do not record it, and a pinned id goes to the
  first of them, with a `WARNING:`. `loom id import` skips every name held by
  several elements, with one `INFO: ID registry: not imported (name held by
  several elements): <type> '<name>', ...` line.
- A self-referencing extra, or a bundled library named like the project or a
  dependency, never reads the registry and silently gets its own id; runs
  still record the name for the project or dependency.

## Directories that are skipped

`id generate` (below the project root) and a `loom.Run` dataset directory
(below the dataset's own directory) skip any directory named `.git`,
`__pycache__`, `.mypy_cache`, `.pytest_cache`, `.pyrefly_cache`,
`.ruff_cache`, `.venv`, `venv`, `node_modules`, `dist`, `build`, `.tox`,
`.hatch` or `fragments`, and everything below it. Only the names of
directories below the root count: a project that itself lives under a
directory called `build` is indexed. A dataset directory also leaves out
symbolic links to directories and the declared registry file. `id generate`
also leaves out the declared registry, matched by identity and never by name:
a stray `loom-id-registry.json` that is not the declared file is indexed. The
set is
`IGNORED_DIR_NAMES` in `src/pitloom/core/walk_rules.py`.

## Harvesting new ids

`loom project`/`wheel`/`env` also write newly minted ids back into a
*declared* registry after each run (`--update-id-registry`, on by default;
`--no-update-id-registry` to stop; never creates a registry). Running `loom
project`, then `loom wheel --id-registry loom-id-registry.json` and `loom env
--id-registry loom-id-registry.json`, keeps the same spdxIds with no manual
`id generate`/`import` between them. A name held by several elements of one
document is not written.

A harvest records a SHA-256 only for `software_File` and `ai_AIPackage`
entries (the two content-gated types) and never erases one already recorded:
an element with no hash and another id leaves such an entry as is, with one
`INFO: ID registry: content gate kept for <type> '<key>': harvested id <id>
not recorded over <id>`. `loom id import` is the exception: there the
imported id wins and the hash goes, with one `INFO: ID registry: content gate
dropped for <type> '<key>': imported id <id> replaces <id>` per entry, so
importing an older SBOM of a model gives it that SBOM's id back.
`dataset_DatasetPackage` elements are the exception: a dataset id is pinned
deliberately (`-e NAME:dataset_DatasetPackage` or `id import`), never from a
run's fallback id. A model is harvested under its file's key with its SHA-256,
so its entry only matches the same bytes. A harvest writes each element under
the key its lookup used, not its name, and an element with no recorded key (a
merged loom fragment, an `id import`) never moves an id held under another key
of the same type, and a fragment's stale element (an older SHA-256) never rolls
a newer entry back: see [Merged fragments and
harvest](id-registry-keys.md#merged-fragments-and-harvest).

`loom.Run` writes one kind of entry itself: a model declared with `path=`
whose file the registry does not know, saved after the fragment when the
run ends without an exception (`update-id-registry = false` in
`pitloom_config` stops it). A training and an evaluation script declaring
the same model and file share its id; a retrained file gets a new one.

Registry writes go through one routine: it re-reads the file, re-applies only
the run's own changes and replaces the file atomically, so runs sharing a
registry keep each other's entries. `id generate`, `id import`, a harvest and
`loom.Run` all use it, and an unchanged file is not rewritten. A writable
registry in a read-only directory is written in place, which is not atomic. A
`loom.Run` given an `IdRegistry` object that was never loaded, for a file that
exists, merges into that file and never overwrites it. There is no lock.

A read-only registry file is never overwritten, on any platform. A failed save
logs `WARNING: ID registry: failed to save <path>: <reason>` (the registry's
path, never a temporary file's) and the run's output is already written;
`loom id generate` and `loom id import` print the same line as their one
`ERROR:` and exit 1.

Two `loom.Run` blocks that exit at the very same moment against one registry
can each write the same id for a different model into their fragments: the
registry keeps one key per id, and the run that saves second logs `another run
saved ... first`, but its fragment is already written. Run scripts that share
a registry one after another, not at once.

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
skipped or replaced. `loom.run` reads no `[tool.pitloom]` unless given one
as `pitloom_config=`; its own `id_registry=` resolves against the current
directory, a `pitloom_config=` file's `id-registry` against that file's
directory.

`IdRegistry.load()` takes a `str` or path-like (else `TypeError`). `register()`
and the loader reject a name that UTF-8 cannot hold (a lone surrogate) with
`ValueError`; `generate()` skips such a file with the `FILE=` `WARNING:`, and
harvest and `id import` skip such an element with a `WARNING:`. `generate()`
raises `ID registry: <path> is outside the project root <root>` for a path
outside the root; a symlink inside the project that points outside is keyed
by its project path. `id import` of an SBOM whose `@graph` is not a list is
`ERROR: failed to import SBOM <path>: @graph is not a list`.

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
silently skipped, so the registry file must exist before the build step
below runs. Either commit one made by `loom id generate` (recommended, so
every build reads the same committed file) or keep the seed step in the
snippet below (it also creates the file on its first run, so the very first
workflow run still succeeds).

A committed registry from an earlier Pitloom release (format version 2) is an
`ERROR:`: regenerate it with `loom id generate` or `loom id import` and
commit the result. A registry in format version 3, which that command
writes, can be read only by the first release with registry format 3. The
snippet below pins `pitloom==0.20.2`, which writes and reads version 2: use
a release with registry format 3 for both pins before committing a version 3
file.

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
      # Use the first release with registry format 3 (0.20.2 reads version 2).
      - run: pip install pitloom==0.20.2

      # Extras-free: keys each model by its file path, with the file's
      # SHA-256, whether or not "ai" extras are installed. Creates
      # loom-id-registry.json on first run. Only omit this step if a
      # loom-id-registry.json is already committed to the repo -- a
      # declared-but-missing registry fails the step below.
      - name: Seed/refresh AI model registry entries
        run: loom id generate --id-registry loom-id-registry.json

      # Pin the first release with registry format 3 (v0.20.2 reads version 2).
      - uses: bact/pitloom@v0.20.2
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

- **AI model id stability doesn't come from `extras: "ai"`.** A model's
  registry key is its file's path, with the file's SHA-256 as the gate, on
  every surface: `loom id generate` and a run agree whether or not the extras
  are installed. `extras: "ai"` only affects metadata richness
  (architecture, hyperparameters, etc.), not which spdxId a model gets.
- **Race conditions**: this workflow never competes with the publish
  workflow to push (the publish job doesn't commit, per the guidance
  above). It can race with *itself*, though -- two pushes to `main` close
  together could trigger two concurrent runs both trying to commit and
  push. The `concurrency:` group above queues same-branch runs instead of
  racing them. One sequencing caveat remains, shared by any
  generated-and-committed file (this repo's own `CITATION.cff` included):
  cutting a release at the exact moment a registry-update commit is in
  flight could still pick up a slightly-stale `loom-id-registry.json`.
