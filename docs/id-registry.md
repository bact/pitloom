---
Created: 2026-10-07
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry

See also: [Loom ID registry, creating one](id-registry-create.md) (the
`id generate` and `id import` commands),
[Keys and content gates](id-registry-keys.md) (what an entry is
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
`FileNotFoundError` (missing, or not a file) or `ValueError`; the Hatchling hook logs one `ERROR:` and fails the build.

## Create a registry

Moved to [Loom ID registry, creating one](id-registry-create.md#create-a-registry).

## What a registry pins

Given the same registry, a file, dependency package, the project's own
package (`project`, `wheel`, `embed-wheel`, the Hatchling hook) or an AI model
carries the same id everywhere. A package is keyed by its name and version, so
each release has its own id. `env` reuses a dependency's id only. A file, a
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
  (and of a wheel's Merkle root), with one `WARNING: ID registry:
  FILE=<path>: inside the project's file set; left out of it
  [registry-conflict/file-set]` per run when the file set
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
- Two versions of a dependency in one document (behind different markers)
  are two keys, each pinned and recorded on its own. A key held by two
  elements of one document that both read the registry (two bundled
  libraries of one name and version) cannot be pinned automatically: runs do
  not record it, and a pinned id goes to the first of them, with a
  `WARNING:`. `loom id import` skips every key held by several elements, with
  one `INFO: ID registry: not imported (name held by several elements): <type>
  '<key>', ... [registry-key-ambiguous]` line.
- A `project` run of a project with a dynamic version states `unknown` and so
  keys its own package by name alone; a wheel or hook run of it states the
  version: the two give that package two ids.
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
set is `IGNORED_DIR_NAMES` in `src/pitloom/core/walk_rules.py`.

## Namespaces

An `spdxId` is an opaque IRI; the SBOM is valid whatever namespaces its ids
use. With a registry, one SBOM can hold ids of several, because an id is
pinned as it was first minted:

- **The registry's namespace** is the one `id generate`, `-e` and `loom`
  register ids in. It is a random UUID4 stored in the file when the registry
  is created, the SBOM document's id after `id import` into an empty
  registry, or `--namespace IRI`. It never changes for the registry.
- **The document's namespace**, `https://spdx.org/spdxdocs/<name>-<uuid>`, is
  the one a build mints every other id in: the `SpdxDocument` and its
  `software_Sbom`, relationships, annotations, and an element the registry
  does not hold yet. Its `<uuid>` is derived from the project's content
  (name, version, dependencies, lock pins, file set), so it changes with it.
  [Harvesting](#harvesting-new-ids) then pins those ids, as minted, so
  after a release one SBOM can hold the registry's namespace and the
  namespaces of earlier documents.

The registry's namespace is random, not content-derived, because it must
outlive every release (a content-derived one would move with each) and be
unique per registry (a name-derived one would be shared by two projects of the
same name). It is a registry input, so the same registry gives the same SBOM.
For a namespace you choose, pass `--namespace` (a URL you own). It governs only
the ids the registry mints, not the document's namespace.

## Harvesting new ids

`loom project`/`wheel`/`env`/`generate` also write newly minted ids back into
a *declared* registry after each run (`--update-id-registry`, on by default;
`--no-update-id-registry` to stop; never creates a registry). Running `loom
project`, then `loom wheel --id-registry loom-id-registry.json` and `loom env
--id-registry loom-id-registry.json`, keeps the same spdxIds with no manual
`id generate`/`import` between them. A name held by several elements of one
document is not written.

A harvest records a SHA-256 only for `software_File` and `ai_AIPackage`
entries (the two content-gated types) and never erases one already recorded:
an element with no hash and another id leaves such an entry as is, with one
`INFO: ID registry: content gate kept for '<type>' <key>: harvested id <id>
not recorded over <id>`. `loom id import` is the exception: there the
imported id wins and the hash goes, with one `INFO: ID registry: content gate
dropped for '<type>' <key>: imported id <id> replaces <id>` per entry, so
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
logs one `WARNING:`, what stopped it with its code: a write the system refused
is `WARNING: FILE=<path>: could not write for the ID registry; <reason>
[file-unwritable]` (the registry as given, never a temporary file), a file
that no longer loads says its own line. The run's SBOM is built before the
save and still written. The registry is written through a temporary file, so
a failure leaves it as it was; where the directory refuses a temporary file it
is written in place, and a full disk can leave it part-written. `loom
id generate` and `loom id import` print the same line as their one `ERROR:`
and exit 1. A library `IdRegistry` with no file logs `WARNING: ID registry: no
file to save to; the ids this run added are not saved
[registry-file-missing]`.

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
registry file that's missing (or not a file) raises `FileNotFoundError`
(`ID registry file not found: '<path>'`, adding `is not a file` when
something else is there, a FIFO or device included, code `input-not-found`),
naming the path as given -- the flag or argument
as typed, the configured `id-registry` value as written -- never the
resolved absolute path; one that's unreadable or invalid raises
`ValueError` carrying its code (`registry-malformed`, `registry-wrong-format`,
`registry-unknown-key`, `json-malformed`, `file-unreadable`: `ID registry:
FILE=<path>: <reason>` or `FILE=<path>: not valid JSON for the ID registry;
<reason>`), naming the path as given too. See
[ID registry message codes](message-codes-id-registry.md).
Neither is silently skipped or replaced. `loom.run` reads no `[tool.pitloom]` unless given one
as `pitloom_config=`; its own `id_registry=` resolves against the current
directory, a `pitloom_config=` file's `id-registry` against that file's
directory.

`IdRegistry.load()` takes a `str` or path-like (else `TypeError`), not
empty (else `ValueError`), as `--id-registry ""` is refused; both carry the
code `option-invalid`. `save()` with no path, for a registry made without
one, raises `ValueError` (`registry-file-missing`). `register()`
and the loader reject a name that UTF-8 cannot hold (a lone surrogate) with
`ValueError` (`text-malformed/registry`, `registry-malformed`); `generate()`
skips such a file with the `PATH` `WARNING:`, and harvest and `id import`
skip such an element with a `WARNING:` (both `text-malformed/registry`).
`register()` stores a key holding user information, a secret query value
or an access token, or a query nested or encoded too deeply to read (a PURL
qualifier and a dotless scp-style address included) with a `WARNING:`, and
raises `ValueError` for it in the `refuse` mode (`refuse_credentials=True` on
`IdRegistry.load()`, `IdRegistry.new()` or the constructor); harvest and `id
import` skip an element whose key or `spdxId` holds one, with a `WARNING:`, in
either mode; `IdRegistry.load()` and `IdRegistry.rebase()` load a file that
holds such an entry with a `WARNING:`, and in the `refuse` mode raise
`ValueError` and leave it as it is (all `credentials-unsafe/registry`; see
[Credentials in a key](id-registry-keys.md#credentials-in-a-key)).
`generate()` raises `FileNotFoundError` (`PATH not found: '<path>'
[input-not-found]`) for a path that is not there, and `ValueError` (`ID
registry: PATH '<path>' is not inside the project root '<root>'
[option-invalid]`) for
a path outside the root; a symlink inside the project that points outside is keyed
by its project path. `id import` of an SBOM whose `@graph` is not a list is
`ERROR: loom id import: FILE=<path>: SBOM @graph is not a list [sbom-invalid]`,
as `embed-wheel --sbom` refuses it; one the SPDX 3 reader refuses (an object
with no type) is `ERROR: loom id import: FILE=<path>: SBOM cannot be read as
SPDX 3; <reason> [sbom-invalid]`.

## In CI

A registry is used only when declared: via the Action's `id-registry` input, or
via `[tool.pitloom] id-registry` in the project's own config. Nothing is
auto-discovered. Once declared, `loom project`/`wheel`/`env`/`generate` (and
the Action, which wraps them) harvest newly-minted ids back into it by
default -- see `update-id-registry` in [Configuration](configuration.md).
That write only ever touches the runner's local checkout; it never needs
elevated permissions itself (that's a `git push`, which Pitloom never does).
But the write is ephemeral unless a workflow step commits it back, so a
release/publish job that intentionally runs with `permissions: contents: read`
(common for trusted PyPI publishing -- see this repo's own
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

A committed registry from an earlier Pitloom release (format version 3 or 2)
is an `ERROR:`: regenerate it with `loom id generate` or `loom id import` and
commit the result. A registry in format version 4, which that command
writes, can be read only by Pitloom 0.22.0 or later (0.21.x reads version 3,
0.20.2 and earlier version 2), so the snippet below pins 0.22.0 for both the
CLI and the action.

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
      # 0.22.0 is the first release with registry format 4.
      - run: pip install pitloom==0.22.0

      # Extras-free: keys each model by its file path, with the file's
      # SHA-256, whether or not "ai" extras are installed. Creates
      # loom-id-registry.json on first run. Only omit this step if a
      # loom-id-registry.json is already committed to the repo -- a
      # declared-but-missing registry fails the step below.
      - name: Seed/refresh AI model registry entries
        run: loom id generate --id-registry loom-id-registry.json

      # Pin the first release with registry format 4 (v0.21.x reads version 3).
      - uses: bact/pitloom@v0.22.0
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
