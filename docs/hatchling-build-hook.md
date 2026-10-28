---
Created: 2026-08-11
Last-Modified: 2026-10-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Hatchling build hook

Use this when you build wheels with [Hatchling][hatchling] and want an
SBOM embedded automatically -- no separate CLI step to remember.

[hatchling]: https://hatch.pypa.io/latest/plugins/build-hook/reference/

Pitloom embeds the SBOM at
`.dist-info/sboms/<name>-<version>.spdx3.json` (e.g.
`.dist-info/sboms/mypackage-1.0.0.spdx3.json`), per [PEP 770] (wheels
only), as compact canonical JSON. The name and version are escaped as for
`loom project`, so no project metadata can make the file name a path.

[PEP 770]: https://peps.python.org/pep-0770/

## Quick guide

```toml
[build-system]
requires = ["hatchling>=1.29.0", "pitloom>=0.21.1"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.pitloom]
# This can be empty
```

That's all -- `hatch build` and `python -m build` embed the SBOM.

## Installation

Add `pitloom` as a build requirement (Hatchling **1.29.0+** required) and
add the `[tool.hatch.build.hooks.pitloom]` table to `pyproject.toml`
(as shown above) -- both parts are required. Listing `pitloom` under
`[build-system] requires` alone does not activate the hook: Hatchling
only runs hooks whose name appears under `[tool.hatch.build.hooks]`, so
the table itself is what turns it on, even left empty.

No separate `pip install` step is needed beyond that -- the build
front-end (`pip`, `build`, `hatch`) installs `pitloom` as a build-time
dependency automatically, the same way it installs Hatchling itself.

> [!NOTE]
> Hatchling 1.32.3 changed the build-hook plugin interface, and 1.32.4
> reverted the change. Pitloom works with both, but other build-hook
> plugins written for the usual interface may fail to import on 1.32.3.
> If you pin Hatchling, prefer any version other than 1.32.3.

## Usage details

Every `hatch build`/`python -m build` invocation:

1. Generates a Build SBOM (`software_SbomType.build`) for the project being built.
2. Merges in any fragments registered under `[tool.pitloom.fragment]`
   (see the [Python API](python-api.md#tracking-decorator) tracking
   decorator, or a hand-authored fragment).
3. Embeds the result into the wheel's `.dist-info/sboms/` directory.

> [!NOTE]
> Lock-file resolution and lock-file SHA-256 hash preservation are
> source-stage only (`loom project` / `loom generate`). Wheels built via
> `hatch build` do not consult source-stage lock files; dependency
> integrity hashes in embedded build SBOMs are resolved via PyPI (when
> online) or omitted (when offline).

The table's `enabled` key defaults to `true`, so an empty
`[tool.hatch.build.hooks.pitloom]` is enough. Set `enabled = false`
inside it to skip generation for a particular build without removing
the table.

Besides `enabled`, the table takes the keys Hatchling itself reads from any
hook (`enable-by-default`, `dependencies`, `require-runtime-dependencies`,
`require-runtime-features`); any other key is an error.

Status/skip/deviation messages the hook logs during a build follow the
same grep-able `INFO:`/`WARNING:`/`ERROR:` stderr convention as the
`loom` CLI (see [Command line](cli.md)) -- e.g. a merge failure (see
[Merge fragments](fragments.md#merge-fragments)) fails the build outright
with an `ERROR: SBOM generation failed: <reason>` line (once, whatever the
cause: an invalid setting, a missing `required = true` fragment, a malformed
`SOURCE_DATE_EPOCH`), and "generation skipped: hook disabled" is an `INFO:`.

The hook skips, with one `INFO:`, a build that is not a wheel (an sdist) and
the `editable` variant of a wheel: an editable wheel holds a `.pth` file, not
the project's files, so an SBOM would list files that are not in it.

A `[tool.hatch.build.targets.wheel]` `sbom-files` entry with the same file
name as the hook's SBOM, ignoring case (typically `loom project`'s default
`<name>-<version>.spdx3.json`), is an `ERROR:`, as the wheel would hold the
name twice, or two names that Windows and macOS extract onto one file: set `[tool.pitloom] sbom-basename` to another name, or drop the entry.

## Reproducible builds

With `SOURCE_DATE_EPOCH` set (or `creation-datetime` in
`[tool.pitloom.creation]`), repeated builds of unchanged sources give the same
wheel bytes. Without either, the SBOM's `created` and its package's `builtTime`
come from the clock, so the wheel differs between builds even though Hatchling
itself is reproducible; the hook says so with one `INFO:`. A
`SOURCE_DATE_EPOCH` that is not an integer number of seconds (or is out of
range) is an `ERROR:` that fails the build, as the
[specification][source-date-epoch] asks, even with `creation-datetime` set.

[source-date-epoch]: https://reproducible-builds.org/specs/source-date-epoch/

## Configuration

Basename and fragments are configured under `[tool.pitloom]`:

```toml
[tool.pitloom]
sbom-basename = "custom-bom"       # -> "custom-bom.spdx3.json" (default: "<name>-<version>")
                                   # (a trailing ".spdx3.json" is dropped, with a WARNING)

[tool.pitloom.fragment]
files = ["fragments/model.json"]   # merge externally tracked fragments
```

The hook does not act on `describe-relationship` or `update-id-registry`: a
build backend does not write to the source tree (an ID registry is read, never
updated, as with `embed-wheel`), and relationship descriptions are not written.
Each of them set to `true` in `[tool.pitloom]` gets one
`INFO: Options: ... has no effect` line (`false` agrees with the hook, so is
silent); harvest ids with `loom project` instead.

Creator/tool metadata uses the same `[[tool.pitloom.creator]]` /
`[[tool.pitloom.creation-tool]]` / `[tool.pitloom.creation]` tables the
CLI reads -- see [Creation metadata](creation-metadata.md). Provenance
detail is controlled the same way too -- see [Metadata
provenance](metadata-provenance.md).

## See also

- [Command line](cli.md) -- generate an SBOM manually or post-process built
  wheels with `loom embed-wheel`.
- [Dependency sources and precedence](dependency-sources.md) -- why wheel
  embedding scopes dependencies to the build stage.
- [GitHub Action](github-action.md) -- embed PEP 770 SBOMs in CI for any
  build backend.
- [Python API](python-api.md) -- the tracking decorator that produces the
  fragments this hook merges.
