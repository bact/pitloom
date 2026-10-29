---
Created: 2026-09-29
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry: what it pins, how to create one, what its log lines mean

Companion to `../SKILL.md`'s "Pinning element ids" section, which holds the
rule that matters most: a registry is used **only when declared**. This
file is the detail behind it. Full reference:
[Loom ID registry](https://bact.github.io/pitloom/id-registry/).

## Declaring a registry

Element ids are content-addressed: rerunning on unchanged source
reproduces them with no registry. A registry (format version 3, a JSON
file) pins ids across runs whose inputs differ -- e.g. a fragment written
today, merged into next week's regeneration after the source changed (see
`sbom-enrich`), or a `loom.run` script's datasets and models.

A registry is used **only when declared**, never searched for:
`--id-registry FILE` (relative to the current directory), else
`id-registry` in the applicable config -- a `--config FILE` (relative
to that file's directory; replaces the project config), or the
project's own `[tool.pitloom]`/`[tool:pitloom]` (relative to the
project). Wheel, env and model-file targets, and `enrich`/`embed-wheel`
without `--project-dir`, read no project config; an sdist's own key is
ignored. Nothing declared: no registry, silently. Declared but missing,
invalid or an old version 2 file: one `ERROR:`, exit 1. Generating runs also
add newly minted ids to a declared registry; no run ever creates one.

## What a registry pins

One table, keyed by element type and key; each entry holds an `spdxId` and,
when the element has content, its SHA-256. A key is a **path key** (the path
from the registry's project root, `/`-separated, case kept) for anything that
is a file or directory below the root, else a **name key** (a package's PEP 503
name, a Hugging Face model id, a URL or missing dataset). One helper computes
every key, so every command and the Python SDK agree on it.

- **Files and directories** (`software_File`): a file is keyed by path from
  the registry's project root and its entry is content-gated: changed bytes
  get a new id. A directory is the exception: it is keyed by its distribution
  path (`demo`, not `src/demo`), and `id generate` does not index directories.
- **Packages** (`software_Package`, keyed by PEP 503 name): dependencies,
  and the project's own package for `project`, `wheel`, `embed-wheel` and
  the Hatchling hook. `env` pins dependency packages only; its root
  package is minted on every run.
- **AI models** (`ai_AIPackage`): one model file is one id on every surface
  (`project`, `--allow-build`, `wheel`, `embed-wheel`, the hook, `model`,
  `enrich`, `loom.Run`, `id generate`, `id import`), keyed by the model
  file's own path key (the same text as its `software_File`). The entry holds
  the file's SHA-256 and every lookup is gated by it: retrained or
  re-exported bytes at the same path get a new id, with `INFO: ... content
  changed ...` (`id generate`, `loom.Run`) or `INFO: ... no registry entry
  records its SHA-256 ...` (`project`, `model`, `wheel`); an entry with no
  hash never hits. Two models with one stem are two keys. A model with no file
  (a Hugging Face id) is keyed by name.
- **Per-document entities**: a harvest also writes, by name, every agent
  (the creator, the main package's authors, a model's generic producer
  `Agent`, a fragment's `Person`/`Organization`), `Tool` and licence entries
  (`LicenseExpression`/`SimpleLicensingText`). They carry that document's own
  ids, so a run into another document rewrites them; nothing looks a model's
  `Agent` up, so new `Agent` rows in a committed registry are expected; they
  are not something to pin.
- **Datasets** (`dataset_DatasetPackage`) only through the Python SDK
  (`pitloom.loom.Run(..., id_registry=...)`, which reads `[tool.pitloom]`
  only from an explicit `pitloom_config=`). A package whose path exists below
  the root is keyed by that path (`data/t.txt`, `./data/t.txt` and an absolute
  path are one package per run), anything else (URL, missing or outside-the-root
  path) by the name as first declared. In one run, names that differ only by
  whitespace runs or, for a Hugging Face repository id, case (`Org/Data`,
  `org/data`) are one package, as for a model card's datasets; the registry
  is asked for the first spelling only (an id pinned under a later one is not
  used, with a `WARNING:`). Two spellings of one missing path (`./a`, `a`)
  are two packages. `add_output_dataset(input_datasets=...)`
  matches the string an input was declared with, not its key: another spelling logs a `WARNING:` and skips
  the link. An entry **with** a SHA-256 is content-gated (a file's SHA-256, a
  directory's Merkle root): a refreshed dataset, or a file added to a
  directory, is a new package id. An entry **without** one (a pin made
  before the data existed, an old pin) hits any content, with `INFO: ...
  content not checked`; running the same `-e` again once the data exists
  adopts the digest and keeps the id (`INFO: ... pin now gated by its
  SHA-256`), unless the entry already records another digest (new id). A
  dataset that is one file also has a `software_File` (the package `contains`
  it); a dataset directory gets a Merkle root and no file elements. Run-time
  harvest never records a dataset package.
  `loom id generate <dataset-dir>` does **not** pin the package (it indexes
  the files below it as `software_File`s). Pin it with `loom id generate -e
  NAME:dataset_DatasetPackage -o <registry>` (an existing `NAME` is stored as
  its path key with its digest, so pin after the data exists), or by `loom id
  import` of an SBOM or loom fragment that has it (records the digest).

A package name held by several registry-reading elements of one document
(e.g. one dependency at two versions) is never written by a run, and `id
import` skips it. A name-keyed registry holds one id per name, so it can pin
only one holder: `loom id generate <PATH> -e NAME:software_Package
-o <registry>` pins the first claimant (order: main package, dependencies,
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
# more: --project-dir DIR (both; import from above the project needs it)  --namespace IRI  -e NAME[:TYPE] (repeatable, generate only)  --max-dataset-hash-bytes BYTES (generate only; caps a -e dataset's hashing)
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
  its path key, with its SHA-256. `id import` gives a hashed `ai_AIPackage`
  the key of the one `software_File` in the same SBOM with the same hash
  (else its name, with an `INFO:`); one without a hash replaces a hashed
  entry's id and drops its hash, with an `INFO:`. For a model file outside
  `PATH`, add `-e <path-to-file>` (no `:TYPE` means `ai_AIPackage`; an
  existing file is stored as its path key with its SHA-256).
- **Packages**: `id generate` registers none. Seed them with one `project`
  run into a declared registry, with `id import <sbom>`, or by hand:
  `loom id generate <PATH> -e NAME:software_Package -o <registry>` pins a
  dependency's or the project's own package id (the `:software_Package`
  suffix is required).
- **Datasets**: `-e NAME:dataset_DatasetPackage`, `NAME` the path from the
  project root (`-e` resolves it against `--project-dir`, not the script's
  directory: a script in `scripts/` declaring `../data/t.txt` is looked up as
  `data/t.txt`). Only a dataset with no path below the root is matched by the
  script's exact string (see above).
- **`-e NAME[:TYPE]`** splits on the last colon: the suffix is a `TYPE` only
  when it is a known registry type (`software_File`, `software_Package`,
  `ai_AIPackage`, `dataset_DatasetPackage`); one shaped like a type name
  (`prefix_ClassName`) or a known type in another case is a usage error (exit
  2); any other suffix stays part of `NAME`, so a URL or a Windows drive path
  works
  (`-e https://huggingface.co/datasets/imdb:dataset_DatasetPackage`).
  For `dataset_DatasetPackage` (file or directory), `ai_AIPackage` and
  `software_File` (regular files), a `NAME` that exists below `--project-dir`
  is stored as its path key plus content digest (`INFO: ID registry: -e NAME
  stored as KEY` when the key differs from the text); any other
  `ai_AIPackage` or `software_File` name is stored by name with `INFO: ID
  registry: -e NAME stored by name: <reason>` (an `ai_AIPackage` name applies
  only to a model with no file), and a dataset that is missing, outside the
  root or unhashable by name with no hash and `INFO: ID registry: dataset NAME
  pinned without SHA-256: <reason>`. `software_Package` is always by name. A
  trailing `:`, white space around the `TYPE`, a control character or a blank
  `NAME` is also a usage error (exit 2).
- **Unreadable files**: a file or directory below a `PATH` that cannot be
  read or listed is a `WARNING: FILE=...`/`DIR=...` (project-relative path)
  and the run continues (so does a file whose name is not UTF-8 encodable); an
  unreadable `PATH` argument is `ERROR: PATH '<path>': could not be read: ...`
  (an unreadable default directory is only the `DIR=` warning). An explicit
  `PATH` that is or lies in a skipped directory (`build`, `dist`, ...) indexes
  nothing and warns
  `ID registry: path has a skipped directory name (build), skipping: <path>`.
  Neither command rewrites an unchanged registry, and `id import` keeps the
  namespace it adopted unless another run changed it meanwhile.
- **Namespace**: a new registry gets one minted from the project directory's name and a
  random UUID4; `--namespace IRI` (an absolute IRI without `#`; `id generate`
  only, `id import` has no such option) sets a reproducible one. An existing
  registry with another namespace is an `ERROR:`, exit 1.
- **Project root**: a new registry stores the project directory
  (`--project-dir`, default the current directory, for both `generate` and
  `import`) relative to its own file. `id generate`, or `id import` with an
  explicit `--project-dir`, into a registry made for another project directory
  is an `ERROR:`, exit 1: pick one root per registry.

The file is JSON with `version: 3`, `namespace`, `project_root`, an
`elements` table and `id_counters` (per id prefix, the highest number
issued, so a retired id is never minted again; do not lower or drop it by
hand: a file without it does not load; neither does one with a non-integer
`version` or a repeated JSON key). A **version 2** registry (a committed file
from an earlier release, with `files` and `entities`) is rejected, on every
command, with one `ERROR:` and nothing written. `id generate`/`id import` print
it as below; other commands prefix their own (`ERROR: SBOM generation
failed: ...`):

```text
ERROR: ID registry file '<path>': version 2, expected 3 (no migration support -- delete it and re-run `pitloom id generate` or `pitloom id import`)
```

Pitloom releases before registry format 3 write version 2, so a registry
committed under one needs this; a version 3 file needs a release that ships
the format. Relay the `ERROR:`. Deleting the file loses its pins
(every id is minted again), so ask first. If the user agrees: delete the file,
then re-run `loom id generate <PATH> -o <REGISTRY>` (add `-e` as before),
or `loom id import <SBOM> -o <REGISTRY>` to carry an earlier SBOM's ids
over (same path as the deleted file). Non-interactive: stop, report the
`ERROR:` and both commands, change nothing. Never convert the file by hand.

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
    loom.set_model("my-model", path="model.bin")  # path= : hashed at exit
    train()  # writes model.bin, out/pred.csv
    loom.add_output_dataset("out/pred.csv")  # declare AFTER writing
```

- `id_registry=` takes a path (relative to the current directory) or an
  `IdRegistry`; without it the registry comes from `pitloom_config=` (a path to
  a config file or a `PitloomConfig`; its `id-registry`, `update-id-registry`
  and `max-dataset-hash-bytes` are the only keys loom reads; the keyword
  `max_dataset_hash_bytes=` beats the last). No
  `[tool.pitloom]` is read implicitly; a missing `pitloom_config` file is a
  `ValueError`. With neither, no registry.
- `set_model()`/`use_model()` take `path=`; the model resolves when the block
  ends without an exception (nothing is written if it raises). A changed file
  at `path` is a new model: `INFO: ... content changed ...`, a new id.
  Without `path=`, one `WARNING: loom: model X has no path=` and a name-only
  lookup that hits a hash-less entry only: an id recorded with a SHA-256
  (a model file, `id import` of a model SBOM) is not reused, since no
  content vouches for it (`WARNING: ... records a SHA-256 but no content was
  hashed`), so a new id is minted.
- The `INFO: ID registry: to use this registry` hint is for CLI runs; a script
  passes `id_registry=` (or `pitloom_config=`) itself.
- A dataset is hashed when declared, so declare an output dataset after the
  file is written, or it has no hash and is not found.
- To pin, run once the files exist, from the project directory:
  `loom id generate data out/pred.csv script.py -e data/train.txt:dataset_DatasetPackage
  -o loom-id-registry.json` (files and the script are `software_File`; the
  dataset package needs its own `-e`, named by its path from the project
  root). Until then each unpinned item logs `WARNING: loom: ... not found in
  registry; minting a new spdxId`: expected on a first run, not an error.
- A dataset path that exists below the root is matched by its path key, so
  `data/t.txt`, `./data/t.txt` and `../data/t.txt` from a subdirectory reach one
  package. A name pin made before the data existed has no hash and hits any
  content (see Datasets).

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
  command among them logs a `WARNING: Options: ...`; an `update-id-registry`
  key in the project's `[tool.pitloom]` gets one `INFO: Options: ...` from the
  build hook and `embed-wheel --project-dir`.
- **Ignored**: Hugging Face targets ignore `--id-registry` (also a
  `WARNING:` if passed).

A run writes each element under the key its lookup used. `dataset_DatasetPackage`
ids are never harvested; an `ai_AIPackage` only when it carries its file's
hash. An element with no recorded key (merged fragment, `id import`) never
moves an id held under another key of the same type, and a stale element (an
older SHA-256) never rolls a newer entry back.

Pins made by an earlier branch of format 3 (model stem keys, own-name model
keys, dataset strings that differ from the canonical path such as
`./data/t.txt`) no longer match: ids renumber once. Re-run `loom id generate`
(add `-e` pins again) into a fresh file, or `loom id import` an earlier SBOM.

## Log lines that are not a broken registry

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
  (old: <id>).` -- a file, model or dataset pin whose content differs from its entry
  gets a new id (`id generate` re-indexing or `-e`, a `loom.Run` model with
  `path=`, a model file in a project run); normal after an edit or a retrain (a
  `project` run reports a changed file as `updated stale entries` above).
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
- `INFO: ID registry: -e NAME stored as KEY` / `stored by name: <why>` --
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
- `WARNING: DIR=<dir>: could not list for ID registry indexing` -- `id
  generate` skipped an unlistable subdirectory; fix its permissions and re-run.
- `WARNING: ID registry: <path> is inside the project's file set; left out
  of it` -- keep the registry outside the
  package tree (above).

A declared registry that is missing or invalid (a version 2 file included)
is different: one `ERROR:`, exit 1, nothing written.

## Choosing the registry before generating

**Choose the registry before generating** (not for a Hugging Face model or
`embed-wheel --sbom`: `--id-registry` is ignored there, with a `WARNING:`):

1. If the applicable config declares a registry, it is used -- tell the user
   which file, and that a `project`, `wheel`, `env` or `generate` run may add
   new ids to it; `model`, `enrich`, `embed-wheel` and the hook only read it.
2. None declared, and ids must stay stable across runs or a fragment will be
   merged after the source changes:
   - Interactive: ask "Pin ids with a Loom ID registry? If yes, which
     file -- an existing one, or create `loom-id-registry.json`?" Yes: create
     it first if new (per the reference), then pass `--id-registry FILE`. No:
     generate without one.
   - Non-interactive: use none, create nothing, and report "No Loom ID
     registry used (none declared). To pin ids, run `loom id
     generate <PATH> -o loom-id-registry.json` in the project directory, then
     declare it as the INFO line says (project target) or pass
     `--id-registry loom-id-registry.json` on each run (other targets)."
