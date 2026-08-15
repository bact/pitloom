---
Created: 2026-08-11
Last-Modified: 2026-08-14
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
only), as compact canonical JSON.

[PEP 770]: https://peps.python.org/pep-0770/

## Quick guide

```toml
[build-system]
requires = ["hatchling>=1.29.0", "pitloom>=0.14.1"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.pitloom]
# This can be empty
```

That's all -- `hatch build` and `python -m build` now embed the SBOM.

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

## Usage details

Every `hatch build`/`python -m build` invocation now:

1. Generates a Source SBOM for the project being built.
2. Merges in any fragments registered under `[tool.pitloom.fragment]`
   (see the [Python API](python-api.md#tracking-decorator) tracking
   decorator, or a hand-authored fragment).
3. Embeds the result into the wheel's `.dist-info/sboms/` directory.

The table's `enabled` key defaults to `true`, so an empty
`[tool.hatch.build.hooks.pitloom]` is enough. Set `enabled = false`
inside it to skip generation for a particular build without removing
the table.

## Configuration

Basename and fragments are configured under `[tool.pitloom]`:

```toml
[tool.pitloom]
sbom-basename = "custom-bom"       # -> "custom-bom.spdx3.json" (default: "<name>-<version>")

[tool.pitloom.fragment]
files = ["fragments/model.json"]   # merge externally tracked fragments
```

Creator/tool metadata uses the same `[[tool.pitloom.creator]]` /
`[[tool.pitloom.creation-tool]]` / `[tool.pitloom.creation]` tables the
CLI reads -- see [Creation metadata](creation-metadata.md). Provenance
detail is controlled the same way too -- see [Metadata
provenance](metadata-provenance.md).

## See also

- [Command line](cli.md) -- generate an SBOM manually or post-process built
  wheels with `loom embed-wheel`.
- [GitHub Action](github-action.md) -- embed PEP 770 SBOMs in CI for any
  build backend.
- [Python API](python-api.md) -- the tracking decorator that produces the
  fragments this hook merges.
