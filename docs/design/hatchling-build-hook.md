---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Hatchling build hook and PEP 770 wheel embedding

## Overview

This document describes the design of Pitloom's Hatchling build hook plugin
(`pitloom.plugins.hatch`) and the PEP 770-compliant embedding of SBOMs inside
Python wheel archives.

The goal is to make SBOM generation a zero-friction, automatic step: when
a developer runs `hatch build` or `python -m build`, the SBOM is generated
and embedded into the wheel with no additional commands.

## PEP 770 background

[PEP 770](https://peps.python.org/pep-0770/) reserves the
`.dist-info/sboms/` directory inside wheel archives for SBOM documents.
The directory may contain one or more SBOM files in any standard format.
Downstream tools (e.g., Trivy, Grype, `pip show`) can discover and consume
these documents from an installed package or directly from the wheel file.

Target placement for Pitloom output:

```text
{name}-{version}.dist-info/
└── sboms/
    └── sbom.spdx3.json
```

## Hatchling plugin registration

Hatchling discovers build hooks registered as Python entry points under the
`hatch` group (consumed via [pluggy](https://pluggy.readthedocs.io/)).
The module must expose a `@hookimpl`-decorated
`hatch_register_build_hook()` function that returns the hook class.

### Entry point in Pitloom's `pyproject.toml`

```toml
[project.entry-points."hatch"]
loom = "pitloom.plugins.hatch"
```

### User configuration in the target project's `pyproject.toml`

The user adds `loom` to their build dependencies and enables the hook:

```toml
[build-system]
requires = ["hatchling", "pitloom"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.pitloom]
# All fields are optional. Defaults are shown.
enabled = true
sbom-basename = ""          # Name part only, no extension; default "sbom"
creator-name = ""           # Defaults to "Pitloom"
creator-email = ""          # Optional
fragments = []              # List of pre-generated fragment paths to merge
```

The full SBOM filename is derived by appending the format extension to the
basename: `{sbom-basename}.spdx3.json` (e.g., `sbom.spdx3.json` by default).

Specifying fragments allows the hook to merge `pitloom.bom`-generated AI/ML
fragments produced during training before the build:

```toml
[tool.hatch.build.hooks.pitloom]
fragments = [
    "fragments/train_run.spdx3.json",
    "fragments/eval_run.spdx3.json",
]
```

## SBOM filename conventions

### Inside the wheel (PEP 770)

The default filename is `sbom.spdx3.json`. The user can override the base
name via `sbom-basename`; the `.spdx3.json` extension is always appended by
Pitloom to reflect the SPDX 3 JSON-LD format.

PEP 770 allows a wheel to contain multiple SBOM files (e.g., one per
format), so the `sbom-basename` option is designed to be forward-compatible
with multi-SBOM scenarios.

### Standalone CLI output

When no `-o` / `--output` argument is given, the CLI derives the default
output filename in priority order:

1. `{sbom-basename}.spdx3.json` — if `sbom-basename` is set in `[tool.pitloom]`
2. `{name}-{version}.spdx3.json` — derived from project metadata
3. `sbom.spdx3.json` — fallback

## Build hook class design

### File: `src/pitloom/plugins/hatch.py`

```python
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from hatchling.builders.config import BuilderConfig
from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.plugin import hookimpl

from pitloom.assemble.spdx3.assembler import build as assemble_spdx3
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.extract.pyproject import read_pyproject

log = logging.getLogger(__name__)

_SPDX3_JSON_EXT = ".spdx3.json"


class PitloomBuildHook(BuildHookInterface[BuilderConfig]):
    PLUGIN_NAME = "pitloom"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._staging_dir: tempfile.TemporaryDirectory[str] | None = None
        self._sbom_staging_path: Path | None = None
        self._sbom_filename: str = f"sbom{_SPDX3_JSON_EXT}"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        config = dict(self.config)
        _validate_config(config)

        if not config.get("enabled", True):
            log.info("Pitloom build hook: disabled; skipping SBOM generation.")
            return

        sbom_basename: str = config.get("sbom-basename", "") or "sbom"
        sbom_filename: str = f"{sbom_basename}{_SPDX3_JSON_EXT}"
        creator_name: str = config.get("creator-name", "") or "Pitloom"
        creator_email: str = config.get("creator-email", "")
        hook_fragments: list[str] = config.get("fragments", [])

        project_dir = Path(self.root)
        metadata, pitloom_config = read_pyproject(project_dir / "pyproject.toml")

        creation_meta = CreationMetadata(
            creator_name=creator_name,
            creator_email=creator_email,
        )
        doc = DocumentModel(project=metadata, creation=creation_meta)
        exporter = assemble_spdx3(doc)

        all_fragments = pitloom_config.fragments + hook_fragments
        merge_fragments(project_dir, all_fragments, exporter)

        sbom_json = exporter.to_json(pretty=pitloom_config.pretty)

        self._sbom_filename = sbom_filename
        # TemporaryDirectory intentionally spans initialize() → finalize().
        self._staging_dir = tempfile.TemporaryDirectory()
        self._sbom_staging_path = Path(self._staging_dir.name) / sbom_filename
        self._sbom_staging_path.write_text(sbom_json, encoding="utf-8")

        # Hatchling 1.16.0+ places each path in sbom_files at
        # .dist-info/sboms/<basename> inside the wheel (PEP 770).
        build_data.setdefault("sbom_files", []).append(str(self._sbom_staging_path))

    def finalize(
        self,
        version: str,
        build_data: dict[str, Any],
        artifact_path: str,
    ) -> None:
        """Clean up the temporary staging directory."""
        if self._staging_dir is not None:
            self._staging_dir.cleanup()
            self._staging_dir = None
            self._sbom_staging_path = None


@hookimpl
def hatch_register_build_hook() -> type[PitloomBuildHook]:
    return PitloomBuildHook
```

## Fragment merging and `[tool.pitloom]` configuration

Fragment paths listed under `[tool.hatch.build.hooks.pitloom] fragments` are
merged with any fragments already declared under `[tool.pitloom] fragments`.
The hook concatenates both lists and passes them to `merge_fragments()`.

This means the existing fragment-merging logic is reused unchanged; the hook
only needs to forward the combined list.

## `build_data["sbom_files"]` API

Hatchling 1.16.0 introduced native PEP 770 support.  The wheel builder
initialises `build_data["sbom_files"]` as an empty list and, after all hook
`initialize()` calls complete, copies every path in the list into
`.dist-info/sboms/<basename>` inside the wheel.

`initialize()` uses `build_data.setdefault("sbom_files", []).append(...)` so
that it is safe to call even if another hook or plugin has already added
entries to the list.

## Interaction diagram

```text
Developer runs:
  hatch build  OR  python -m build
         │
         ▼
  Hatchling build process
         │
         ├─── PitloomBuildHook.initialize()
         │       │
         │       ├── read_pyproject(project_dir)
         │       ├── assemble_spdx3(DocumentModel)
         │       ├── merge_fragments(all_fragments)
         │       ├── exporter.to_json()
         │       ├── write staged SBOM → TemporaryDirectory
         │       └── build_data["sbom_files"].append(staged_path)
         │
         ├─── Hatchling packages wheel
         │       └── copies sbom_files → .dist-info/sboms/  ← PEP 770
         │
         └─── PitloomBuildHook.finalize()
                 └── TemporaryDirectory.cleanup()

Output:
  dist/
  ├── mypackage-1.0.tar.gz
  └── mypackage-1.0-py3-none-any.whl
          └── mypackage-1.0.dist-info/
                  └── sboms/
                          └── sbom.spdx3.json
```

## New files and `pyproject.toml` changes

### New source files

```text
src/pitloom/
└── plugins/
    ├── __init__.py
    └── hatch.py            ← PitloomBuildHook + hatch_register_build_hook()
tests/
├── fixtures/
│   └── sampleproject/      ← minimal wheel-build fixture
│       ├── pyproject.toml
│       ├── src/sampleproject/__init__.py
│       └── README.md
└── test_hatch_hook.py
```

### Changes to Pitloom's `pyproject.toml`

Register the plugin via pluggy entry point:

```toml
[project.entry-points."hatch"]
loom = "pitloom.plugins.hatch"
```

Require Hatchling 1.16.0+ for native `sbom_files` support:

```toml
dependencies = [
    "hatchling>=1.16.0",
    ...
]
```

## Test plan

| Test | Description |
| :--- | :--- |
| `test_hook_initialize_stages_sbom` | Calls `initialize()` and asserts the staged SBOM path exists and is non-empty. |
| `test_hook_sbom_is_valid_json` | Asserts the staged SBOM is valid JSON-LD with `@context` and `@graph`. |
| `test_hook_creator_name_propagated` | Sets `creator-name` in config; asserts it appears in `@graph`. |
| `test_hook_custom_basename_stored` | Sets `sbom-basename`; asserts `_sbom_filename` and staged path name match. |
| `test_hook_disabled_skips_generation` | Sets `enabled = false`; asserts no staging path and no `sbom_files` entry. |
| `test_hook_finalize_cleans_up` | Asserts temp directory and paths are cleared after `finalize()`. |
| `test_hook_finalize_idempotent` | Calls `finalize()` twice; asserts no exception on the second call. |
| `test_hook_sbom_files_populated` | Asserts `build_data["sbom_files"]` is populated with the staged path after `initialize()`. |
| `test_hook_sbom_files_custom_basename` | Asserts `sbom-basename` config is reflected in the filename in `sbom_files`. |
| `test_hook_sbom_files_appended_to_existing` | Pre-populates `sbom_files`; asserts `initialize()` appends rather than replaces. |
| `test_hook_with_pitloom_fragments` | Provides a valid fragment; asserts its content is merged into the SBOM. |
| `test_hook_missing_fragment_logs_warning` | Provides a non-existent path; asserts a warning is logged, not an exception. |
| `test_hook_with_sampleproject_fixture` | Runs `initialize()` on the real `sampleproject` fixture; asserts package name appears in SBOM. |
| `test_hook_invalid_config_raises_before_io` | Passes bad config; asserts `ValueError` is raised before any filesystem access. |

## References

- PEP 770: <https://peps.python.org/pep-0770/>
- Hatchling build hook reference: <https://hatch.pypa.io/latest/plugins/build-hook/reference/>
- Hatchling build hook interface: `hatchling.builders.hooks.plugin.interface.BuildHookInterface`
- Trivy PEP 770 tracking issue: <https://github.com/aquasecurity/trivy/issues/10021>
