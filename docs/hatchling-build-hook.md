---
Created: 2026-08-11
Last-Modified: 2026-08-11
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

<!-- markdownlint-disable-next-line MD041 -->
{% include nav.html %}

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
requires = ["hatchling>=1.29.0", "pitloom>=0.13.3"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.pitloom]
enabled = true
```

That's all -- `hatch build`/`python -m build` now embeds the SBOM.

## Installation

Add `pitloom` as a build requirement (Hatchling **1.29.0+** required) and
register the hook in `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling>=1.29.0", "pitloom>=0.13.3"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.pitloom]
enabled = true    # set to false to skip SBOM generation
```

No separate `pip install` step is needed beyond that -- the build
front-end (`pip`, `build`, `hatch`) installs `pitloom` as a build-time
dependency automatically, the same way it installs Hatchling itself.

## Usage details

Every `hatch build`/`python -m build` invocation now:

1. Generates a Source SBOM for the project being built.
2. Merges in any fragments registered under `[tool.pitloom.fragments]`
   (see the [Python API](python-api.md#tracking-decorator) tracking
   decorator, or a hand-authored fragment).
3. Embeds the result into the wheel's `.dist-info/sboms/` directory.

Set `enabled = false` under `[tool.hatch.build.hooks.pitloom]` to skip
generation for a particular build without removing the hook.

## Setting/config

Basename and fragments are configured under `[tool.pitloom]`:

```toml
[tool.pitloom]
sbom-basename = "custom-bom"       # -> "custom-bom.spdx3.json" (default: "<name>-<version>")

[tool.pitloom.fragments]
files = ["fragments/model.json"]   # merge externally tracked fragments
```

Creator/tool metadata uses the same `[[tool.pitloom.creator]]` /
`[[tool.pitloom.creation-tool]]` / `[tool.pitloom.creation]` tables the
CLI reads -- see [Creation metadata](creation-metadata.md). Provenance
detail is controlled the same way too -- see [Metadata
provenance](metadata-provenance.md).

## See also

- [Command line](cli.md) -- generate an SBOM manually, outside a build.
- [Python API](python-api.md) -- the tracking decorator that produces the
  fragments this hook merges.
