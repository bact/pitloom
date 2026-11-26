---
Created: 2026-11-26
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom ID registry, creating one

See also: [Loom ID registry](id-registry.md) for declaring a registry,
what it pins and harvesting, and [Keys and content
gates](id-registry-keys.md) for what an entry is keyed by.

How `loom id generate` and `loom id import` create or update a registry,
which file they write, and how they fail.

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
`--max-dataset-hash-bytes BYTES` (an integer of at least 1; `0` is a usage
error) caps the bytes read to hash one dataset, else the project's own
`max-dataset-hash-bytes`, else 4 GiB.
`--entity NAME@VERSION:software_Package` pins one release of a dependency, or
of the project's own package (a `NAME` with no `@VERSION` holds only a package
that states no version; see [Package keys](id-registry-keys.md#package-keys)).
The string splits on its last colon: the suffix is a `TYPE` only
when it is a known registry type (`software_File`, `software_Package`,
`ai_AIPackage`, `dataset_DatasetPackage`). A suffix shaped like a type name
(`prefix_ClassName`) or a known type in another case is a usage error (exit
2), not part of `NAME`. Anything else is part of `NAME`, so a URL or a
Windows drive path works, as in
`-e https://huggingface.co/datasets/imdb:dataset_DatasetPackage`. A trailing
`:`, a `TYPE` with white space around it, a control character (a newline), a
blank `NAME` or a package `NAME` that is not a PEP 508 name (`foo==1.0`:
write `foo@1.0`) is a usage error too.
`--namespace IRI` sets a new registry's namespace, the one its own ids are
minted in ([Namespaces](id-registry.md#namespaces)) (an absolute IRI without `#`, and without user information, a secret query
value such as `token` or an access token, or a query nested or encoded too
deeply to read, also in a URL anywhere in it
(`urn:x:https://user:pw@host/ns`): any user name is refused,
`ssh://git@...` too; a
`code`, `session`, `ticket`, `sid` or `otp` parameter is accepted as
written; default: the project directory's name and a random UUID4); an
existing registry with another namespace is one `ERROR:`, exit 1. The
library's `IdRegistry(namespace=...)` and `IdRegistry.new(namespace=...)`
refuse such a namespace with a `ValueError`, coded
`credentials-unsafe/registry` for a credential. A
registry whose `namespace` is not a valid namespace IRI (one holding a
credential included), or whose `spdxId` is not a non-empty string, does not
load. One with an entry whose key or `spdxId` holds a credential loads
with a `WARNING:` per entry by default, and in the `refuse` mode
(`url-credentials = "refuse"`, `--refuse-url-credentials`) does not load: it
is refused, left as it is. Either way you remove the entry (see
[Credentials in a key](id-registry-keys.md#credentials-in-a-key)). `id import` into an empty
registry adopts the SBOM document's namespace only when it is a valid
namespace IRI; otherwise one
`WARNING: FILE=<sbom>: SBOM namespace <why>; the ID registry keeps its
own, not <namespace> [sbom-invalid]`. It keeps the namespace it adopted
unless another run changed the file's namespace meanwhile.
`id import SBOM_FILE` takes `-o`/`--id-registry FILE` and `--project-dir DIR`.

A new registry stores its project root (`--project-dir`, default the current
directory, for both commands) relative to its own directory; an existing one
keeps it, and `generate`, or `import` with an explicit `--project-dir`, naming
another root is one `ERROR:`, exit 1.
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
retrained file (other bytes) gets a new id on every surface. A registry from an
earlier release (format version 3 or 2) is rejected, on every command, with one
`ERROR:` and nothing written; delete it and re-run `loom id generate` or `loom
id import` ([what changed](id-registry-keys.md#what-changed-for-an-existing-registry)).

**Target file.** `-o`/`--id-registry` if given, else the config's
`id-registry` key (both commands: read from `--project-dir`, default the
current directory; `pyproject.toml`'s `[tool.pitloom]` or `setup.cfg`'s
`[tool:pitloom]`). The location is required, never assumed: with neither,
both commands print `ERROR: loom id <command>: no ID registry declared: pass --id-registry FILE
or set id-registry in [tool.pitloom]` (`[tool:pitloom]` for `setup.cfg`),
exit 1 and write nothing. `loom-id-registry.json` is only the suggested name.
A broken `pyproject.toml`/`setup.cfg` is one `ERROR:` line, never a
traceback, and takes precedence over that error.

- A missing target is created. An existing target that cannot be loaded (not
  JSON, wrong version, a version 3 or 2 file, a key the format does not have:
  `ID registry: FILE=<path>: unknown top-level key(s): 'files'
  [registry-unknown-key]`) is one `ERROR:` and exit 1, never silently
  replaced. A registry file that cannot record its project root (on
  Windows, a file on another drive than the project) is not saved: `ID
  registry: FILE=<path>: project root '<root>' has no path relative to the
  file's directory; <reason> [registry-unusable]` (`ERROR:` for `loom id`,
  `WARNING:` where the SBOM is already built; the library raises it
  coded). A registry file inside the project always works.
- A registry file is read whole, up to the fixed 50 MiB cap for a JSON
  document: a larger one is not read (`FILE=<path>: larger than the
  <limit>-byte JSON-document cap for the ID registry; not read [over-cap]`,
  exit 1). Only a regular file is read: a
  FIFO or a device there is `input-not-found` (`is not a file`), opened
  without waiting for a writer.
- Registry keys, and the default `PATH`s (`src`, `data`, `models`), stay
  relative to `--project-dir`; a relative `-o` or `PATH` resolves against the
  current directory.
- `--project-dir` must be an existing directory, else `ERROR: loom id <command>: project directory not found: '<p>'
  [input-not-found]` (a file there adds `is not a directory`; exit 1). Each `PATH` must exist, else
  `ERROR: loom id generate: PATH not found: '<p>' [input-not-found]` (exit 1, nothing written), and
  must resolve inside `--project-dir`, else
  `ERROR: loom id generate: PATH '<p>' is outside --project-dir '<dir>' [option-invalid]` (exit 1),
  whether directly or only through a symlink. Both name the `PATH` as typed. `..` is collapsed lexically before any symlink
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
  is never indexed silently. A file whose name a registry cannot hold (not
  UTF-8 encodable) gets `WARNING: ID registry: PATH '<path>': name cannot be
  encoded as UTF-8 (lone surrogate); not indexed [text-malformed/registry]`.
  A `PATH` argument itself that cannot be read or listed is an `ERROR:` (exit
  1, nothing written) on every Python version, naming it as typed:
  `FILE=<path>: could not read for ID registry indexing; <reason>
  [file-unreadable]`, `DIR=<path>: could not list for ID registry indexing;
  <reason> [dir-unlistable]`, or, when its directory cannot be searched,
  `FILE=<path>: could not read for the input check; <reason>`. An
  unreadable default directory (`src`, `data`, `models`) is the `DIR=`
  warning instead, and a missing one is left out.
- Build, virtual-environment, VCS and cache directories are not indexed; see
  [Directories that are skipped](id-registry.md#directories-that-are-skipped). A `PATH`
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
