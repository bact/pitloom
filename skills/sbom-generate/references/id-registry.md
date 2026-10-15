---
Created: 2026-09-29
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry: what it pins, how to create one, what its log lines mean

Companion to `../SKILL.md`'s "Pinning element ids" section, which holds the
rule that matters most: a registry is used **only when declared**. This
file is the detail behind it. Full reference:
[Loom ID registry](https://bact.github.io/pitloom/id-registry/).

## What a registry pins

One table, keyed by element type and name; each entry holds an `spdxId` and,
when the element has content, its SHA-256.

- **Files and directories** (`software_File`), keyed by path from the
  registry's project root. A file's entry is content-gated: changed bytes
  get a new id.
- **Packages** (`software_Package`, keyed by PEP 503 name): dependencies,
  and the project's own package for `project`, `wheel`, `embed-wheel` and
  the Hatchling hook. `env` pins dependency packages only; its root
  package is minted on every run.
- **AI models** (`ai_AIPackage`), keyed by name (a model file's stem for
  `id generate`, which also records the file's SHA-256). Only a
  `loom.Run` model declared with `path=` is checked against that hash: a
  retrained or re-exported file is a new model with a new id. `project`,
  `wheel`, `model` and `embed-wheel` look a model up by name alone, so a
  retrained file keeps its id there. A stem several model files share gets
  no hash: a new entry has none, an existing one is left as is (one `INFO:`
  per run; `its new entry is not content-gated` when it had none).
- **Per-document entities**: a harvest also writes, by name, every agent
  (the creator, the main package's authors, a model's generic producer
  `Agent`, a fragment's `Person`/`Organization`), `Tool` and licence entries
  (`LicenseExpression`/`SimpleLicensingText`). They carry that document's own
  ids, so a run into another document rewrites them; nothing looks a model's
  `Agent` up, so new `Agent` rows in a committed registry are expected; they
  are not something to pin.
- **Datasets** (`dataset_DatasetPackage`) only through the Python SDK
  (`pitloom.loom.Run(..., id_registry=...)`, which reads `[tool.pitloom]`
  only from an explicit `pitloom_config=`). A dataset package is looked up
  by the exact string the script passes (`add_dataset("data/train.txt")`),
  with no content check, so a remote or missing name is pinned the same way.
  A run holds one package per name and content digest.
  A dataset that is one file also has a `software_File` (the package
  `contains` it), keyed by its path from the project root and gated by its
  hash; a dataset directory gets a Merkle root and no file elements.
  `loom id generate <dataset-dir>` does **not** pin the dataset package (it
  indexes the files below it as `software_File`s). Pin the package with
  `loom id generate -e NAME:dataset_DatasetPackage -o <registry>`, `NAME`
  being the string the script passes, or by `loom id import` of an SBOM or
  fragment that has it.

A package name held by several registry-reading elements of one document
(e.g. one dependency at two versions) is never written by a run, and `id
import` skips it. A name-keyed registry holds one id per name, so it can pin
only one holder: `loom id generate <PATH> -e NAME:software_Package -o
<registry>` pins the first claimant (order: main package, dependencies,
phantom dependencies). Every later run then logs the `registered for both`
`WARNING:` below for the other holder -- expected here, not a stale entry.
The pin goes into the **declared** registry; if none is declared and the
user did not ask to pin ids, do not create one -- tell the user. A
self-referencing extra (`demo[x]`) and a phantom dependency named like the
project or another dependency never read the registry, so they do not count
as holders: the project's own package is still pinned by a run.

## When the user asks to pin ids

The user asked ("pin the ids", "keep ids stable", "create or update an ID
registry", "run `loom id generate`/`import`"): do it, without asking again.

1. Use the registry the user names, else the one the project config
   declares. If neither exists, create `loom-id-registry.json` in the
   project root (the default; any other file only if the user names it).
2. Run `loom id generate <PATH...> -o <registry>` (files and AI models; add
   `-e NAME:TYPE` for a package or dataset the user wants pinned) or `loom id
   import <sbom> -o <registry>` (reuse an existing SBOM's ids), from the
   project directory (see "Create one").
3. Report the exact command, the `PITLOOM_ID_REGISTRY_PATH=` line and every
   `INFO:`/`WARNING:`/`ERROR:` it printed. An `INFO: ID registry: to use this
   registry, ...` line is the declaration the user still has to add: relay it
   verbatim, and do not edit their config yourself.
4. A registry file the command rejects (a version 2 file, an invalid one):
   relay the `ERROR:`. Delete it and re-run only if the user agrees (its pins
   are lost); non-interactive: change nothing and report the `ERROR:` and the
   commands.

An unasked run (a plain generate request) never creates, edits or passes a
registry the user did not name. `sbom-enrich` never pins ids: it hands the
request to this skill. Every question above ("which file?", "delete the
rejected file?") has a non-interactive fallback: change nothing and report
the commands.

## Create one

Only `loom id generate` and `loom id import` create or index a registry;
never hand-edit one. Run from the project directory (`PATH` and `-o`
resolve against the current directory; a `PATH` outside the project, an
unreadable one, or a `--project-dir` that is not a directory is an `ERROR:`,
exit 1, nothing written; a `PATH` that does not exist is only `WARNING: ID
registry: path not found, skipping: <path>` (exit 0, so a typo indexes
nothing: check the `holds N id(s)` count); `-o -` is a usage error, exit 2):

```bash
loom id generate <PATH...> -o loom-id-registry.json   # index files and AI models
loom id import <sbom> -o loom-id-registry.json        # reuse an SBOM's ids
# more: --project-dir DIR  --namespace IRI  -e NAME[:TYPE] (repeatable); import takes none
```

- `-o`/`--id-registry` is required unless the project config already
  declares `id-registry`; without either, one `ERROR:`, exit 1.
- `PATH` is `src` (src layout) or the package directory (flat layout).
  With no `PATH`, whichever of `src`/`data`/`models` exist are used
  (`ERROR:` if none), so `-e` alone needs one of them or an explicit `PATH`.
  Build, virtual-environment, VCS and cache directories below the project
  are not indexed (the list:
  <https://bact.github.io/pitloom/id-registry/#directories-that-are-skipped>).
- **Models**: `id generate` registers each AI model file under `PATH` by
  file stem, with its SHA-256, and `id import` registers each `ai_AIPackage`
  by its model name (with its hash, when the SBOM has one; one without a
  hash replaces a hashed entry's id and drops its hash, with an `INFO:`). A
  project or wheel run never adds an unhashed model id. For one outside `PATH`, add
  `--entity <stem>` (no `:TYPE` means `ai_AIPackage`; no hash is recorded).
- **Packages**: `id generate` registers none. Seed them with one `project`
  run into a declared registry, with `id import <sbom>`, or by hand:
  `loom id generate <PATH> -e NAME:software_Package -o <registry>` pins a
  dependency's or the project's own package id (the `:software_Package`
  suffix is required).
- **Datasets**: `-e NAME:dataset_DatasetPackage`, `NAME` being the string
  the script passes to `add_dataset()` (see above).
- **`-e NAME[:TYPE]`** splits on the last colon: the suffix is a `TYPE` only
  when it is a known registry type (`software_File`, `software_Package`,
  `ai_AIPackage`, `dataset_DatasetPackage`); one shaped like a type name
  (`prefix_ClassName`) or a known type in another case is a usage error (exit
  2); any other suffix stays part of `NAME`, so a URL or a Windows drive path
  works
  (`-e https://huggingface.co/datasets/imdb:dataset_DatasetPackage`). A
  trailing `:`, white space around the `TYPE`, a control character or a blank
  `NAME` is also a usage error (exit 2).
- **Unreadable files**: a file or directory below a `PATH` that cannot be
  read or listed is a `WARNING: FILE=...`/`DIR=...` (project-relative path)
  and the run continues (so does a file whose name is not UTF-8 encodable); an
  unreadable `PATH` argument is `ERROR: PATH <path>: could not be read: ...`
  (an unreadable default directory is only the `DIR=` warning). An explicit `PATH` that is or lies
  in a skipped directory (`build`, `dist`, ...) indexes nothing and warns
  `ID registry: path has a skipped directory name (build), skipping: <path>`.
  Neither command rewrites an unchanged registry, and `id import` keeps the
  namespace it adopted unless another run changed it meanwhile.
- **Namespace**: a new registry gets one minted from the project name and a
  random UUID4; `--namespace IRI` (an absolute IRI without `#`; `id generate`
  only, `id import` has no such option) sets a reproducible one. An existing
  registry with another namespace is an `ERROR:`, exit 1.
- **Project root**: a new registry stores the project directory
  (`--project-dir` for `generate`, the current directory for `import`)
  relative to its own file. `id generate` into a registry made for another
  project directory is an `ERROR:`, exit 1: pick one root per registry.

The file is JSON with `version: 3`, `namespace`, `project_root`, an
`elements` table and `id_counters` (per id prefix, the highest number
issued, so a retired id is never minted again; do not lower or drop it by
hand: a file without it does not load; neither does one with a non-integer
`version` or a repeated JSON key). A **version 2** registry (a committed file from an
earlier release, with `files` and `entities`) is rejected, on every
command, with one `ERROR:` and nothing written. `id generate`/`id import` print
it as below; other commands prefix their own (`ERROR: SBOM generation
failed: ...`):

```text
ERROR: ID registry file <path>: version 2, expected 3 (no migration support -- delete it and re-run `pitloom id generate` or `pitloom id import`)
```

Pitloom releases before registry format 3 write version 2, so a registry
committed under one needs this; a version 3 file needs a release that ships
the format. Relay the `ERROR:`. Deleting the file loses its pins
(every id is minted again), so ask first. If the user agrees: delete the file,
then re-run `loom id generate <PATH> -o <REGISTRY>` (add `-e` as before),
or `loom id import <SBOM> -o <REGISTRY>` to carry an earlier SBOM's ids
over (same path as the deleted file). Non-interactive: stop, report the `ERROR:` and both commands, change
nothing. Never convert the file by hand.

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
(the project root, not `src/<package>/`). One inside it is left out of the
SBOM's file set, with one `WARNING: ID registry: <path> is inside the
project's file set; left out of it` per run (`id generate` leaves it out
silently; also with `--allow-build`, and
for the copy a built wheel or sdist carries, read by `wheel`, `embed-wheel`
or `project <sdist>`: matched by its path below `--project-dir`, else below
the project root the registry stores); the SBOM then does not list it.

## Python SDK (`pitloom.loom`)

A script that records its own run declares the registry and, for the model,
the file:

```python
from pitloom import loom

with loom.run("fragments/train.spdx3.json", id_registry="loom-id-registry.json"):
    loom.add_input_dataset("data/train.txt")
    loom.set_model("my-model", path="model.bin")   # path= : hashed at exit
    train()                                        # writes model.bin, out/pred.csv
    loom.add_output_dataset("out/pred.csv")        # declare AFTER writing
```

- `id_registry=` takes a path (relative to the current directory) or an
  `IdRegistry`; without it the registry comes from `pitloom_config=` (a path to
  a config file or a `PitloomConfig`; its `id-registry`, `update-id-registry`
  and `max-dataset-hash-bytes` are the only keys loom reads). No
  `[tool.pitloom]` is read implicitly; a missing `pitloom_config` file is a
  `ValueError`. With neither, no registry.
- `set_model()`/`use_model()` take `path=`; the model resolves when the block
  ends without an exception (nothing is written if it raises). A changed file
  at `path` is a new model: `INFO: ... content changed ...`, a new id.
  Without `path=`, one `WARNING: loom: model X has no path=` and a name-only
  lookup.
- The `INFO: ID registry: to use this registry` hint is for CLI runs; a script
  passes `id_registry=` (or `pitloom_config=`) itself.
- A dataset is hashed when declared, so declare an output dataset after the
  file is written, or it has no hash and is not found.
- To pin, run once the files exist, from the project directory:
  `loom id generate data out/pred.csv script.py -e data/train.txt:dataset_DatasetPackage
  -o loom-id-registry.json` (files and the script are `software_File`; the
  dataset package needs its own `-e`, named by the exact string the script
  passes). Until then each unpinned item logs `WARNING: loom: ... not found in
  registry; minting a new spdxId`: expected on a first run, not an error.
- The package pin matches the exact string passed: `../data/t.txt` from a
  subdirectory misses it, though the file's own entry (keyed by its path from
  the project root) still hits.

## Harvest: what writes to a registry

Only a **declared** registry is ever written; nothing creates one but `id
generate`/`id import` (above).

- **Writes back** newly minted ids: `project` (a directory or an sdist),
  `wheel`, `env` and `generate` (which dispatches to those). Stop it with
  `--no-update-id-registry` or `update-id-registry = false`.
- **Writes** by design: `id generate` and `id import`.
- **`loom.run`** writes one kind of entry: a model declared with `path=`
  whose file the registry does not know (saved after the fragment, only when
  the block ends without an exception; `update-id-registry = false` in
  `pitloom_config` stops it). Datasets, files and the script are only read.
  It calls `configure_logging()` itself, so its `WARNING:`/`INFO:` lines
  carry their tag like the CLI's (and reset the `pitloom` logger's level and
  handlers each run).
- **Reads, never writes**: `model`, `enrich`, `embed-wheel`, `wheel
  --embed` and the Hatchling build hook. `--update-id-registry` on a CLI
  command among them logs a `WARNING: Options: ...`.
- **Ignored**: Hugging Face targets ignore `--id-registry` (also a
  `WARNING:` if passed).

`dataset_DatasetPackage` ids are never harvested; an `ai_AIPackage` only when it
carries a hash (a loom model declared with `path=`, merged as a fragment).

## Log lines that are not a broken registry

- `INFO: ID registry: added N new id(s) to <path>` (N counts ids under keys
  the registry did not hold) or `INFO: ID registry: updated stale entries in
  <path>` (keys moved or ids were replaced) -- a run wrote into the declared
  registry.
- `INFO: ID registry: holds N id(s)` -- `id generate`/`id import` finished;
  the data line `PITLOOM_ID_REGISTRY_PATH=<path>` is on stdout.
- `INFO: ID registry: not imported (name held by several elements): <type>
  'NAME', ...` --
  `id import` only; the SBOM holds several elements under that name, so no
  single id can be pinned for it.
- `INFO: ID registry: content changed for <name>; minting a new spdxId (old:
  <id>).` -- a file or model whose content differs from its entry gets a
  new id (`id generate` re-indexing, or a `loom.Run` model with `path=`);
  normal after an edit or a retrain (a `project` run reports a changed file
  as `updated stale entries` above).
- `INFO: ID registry: N model files share the name X; its entry is left as
  is` -- `id generate`; expected for same-stem models (a hash recorded
  earlier is kept).
- `INFO: ID registry: content gate dropped for <type> 'X': imported id <id>
  replaces <id>` -- `id import` only; the SBOM's element has no hash and
  another id, which wins, so the entry is no longer checked against content
  (an older SBOM brings its older id back).
- `INFO: ID registry: content gate kept for <type> 'X': harvested id <id>
  not recorded over <id>` -- a run met such an element; the hashed entry is
  kept.
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
  expected on a first run. `... exists but its SHA-256 no longer matches ...`
  means the file changed since it was pinned. Either way a fresh id is used.
- `WARNING: loom: file X is outside the ID registry's project root ...;
  minting a new spdxId` -- the script passed a path outside the project;
  its file is not looked up.
- `WARNING: loom: registry entry for entity 'X' exists but under a different
  type; minting a new spdxId.` -- a model name that the registry holds only
  as another type; the model gets a fresh id.
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
- `INFO: ID registry: package identity unknown; not looked up or recorded` --
  a wheel with no usable `.dist-info` or `METADATA` name; the registry is not
  touched for its package.
- `WARNING: ID registry: not adopting the namespace ...` -- `id import` met
  an SBOM whose document id is not a valid namespace IRI; the registry keeps
  its own namespace.
- `WARNING: DIR=<dir>: could not list for ID registry indexing` -- `id
  generate` skipped an unlistable subdirectory; fix its permissions and re-run.
- `WARNING: ID registry: <path> is inside the project's file set; left out
  of it` -- keep the registry outside the
  package tree (above).

A declared registry that is missing or invalid (a version 2 file included)
is different: one `ERROR:`, exit 1, nothing written.
