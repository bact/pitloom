---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Hatchling build hook and PEP 770 wheel embedding

## Overview

This document describes the design of Loom's Hatchling build hook plugin
(`loom.plugins.hatch`) and the PEP 770-compliant embedding of SBOMs inside
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

Target placement for Loom output:

```text
{name}-{version}.dist-info/
└── sboms/
    └── sbom.spdx3.json
```

## Hatchling plugin registration

Hatchling supports build hooks registered as Python entry points under the
`hatch.build.hook` group. The hook class name identifies the plugin.

### Entry point in Loom's `pyproject.toml`

```toml
[project.entry-points."hatch.build.hook"]
loom = "loom.plugins.hatch:LoomBuildHook"
```

### User configuration in the target project's `pyproject.toml`

The user adds `loom` to their build dependencies and enables the hook:

```toml
[build-system]
requires = ["hatchling", "loom"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.loom]
# All fields are optional. Defaults are shown.
enabled = true
filename = "sbom.spdx3.json"
creator-name = ""           # Defaults to "Loom"
creator-email = ""          # Optional
fragments = []              # List of pre-generated fragment paths to merge
```

Specifying fragments allows the hook to merge `loom.bom`-generated AI/ML
fragments produced during training before the build:

```toml
[tool.hatch.build.hooks.loom]
fragments = [
    "fragments/train_run.spdx3.json",
    "fragments/eval_run.spdx3.json",
]
```

## Build hook class design

### File: `src/loom/plugins/hatch.py`

```python
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

from loom.assemble import generate_sbom

log = logging.getLogger(__name__)


class LoomBuildHook(BuildHookInterface):
    """Hatchling build hook that embeds an SPDX 3 SBOM in the wheel.

    Activated by adding ``[tool.hatch.build.hooks.loom]`` to the project's
    ``pyproject.toml`` and listing ``loom`` as a build dependency.

    The SBOM is written to ``.dist-info/sboms/<filename>`` inside the wheel,
    conforming to PEP 770.
    """

    PLUGIN_NAME = "loom"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._staging_dir: tempfile.TemporaryDirectory[str] | None = None
        self._sbom_staging_path: Path | None = None

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Generate the SBOM and stage it for inclusion in the build artifact.

        Called by Hatchling before packaging. Adds the SBOM to
        ``build_data["extra_metadata"]`` so Hatchling places it in
        ``.dist-info/sboms/`` inside the wheel.
        """
        config = self._get_loom_config()
        if not config.get("enabled", True):
            log.info("Loom build hook is disabled; skipping SBOM generation.")
            return

        project_dir = Path(self.root)
        creator_name: str | None = config.get("creator-name") or None
        creator_email: str | None = config.get("creator-email") or None
        sbom_filename: str = config.get("filename", "sbom.spdx3.json")
        fragment_paths: list[str] = config.get("fragments", [])

        # Validate and resolve fragment files
        resolved_fragments = _resolve_fragments(project_dir, fragment_paths)

        sbom_json = generate_sbom(
            project_dir,
            creator_name=creator_name,
            creator_email=creator_email,
        )

        # Use a TemporaryDirectory so the file outlives initialize()
        self._staging_dir = tempfile.TemporaryDirectory()
        self._sbom_staging_path = Path(self._staging_dir.name) / sbom_filename
        self._sbom_staging_path.write_text(sbom_json, encoding="utf-8")

        # Hatchling reads extra_metadata as {relative-path-in-dist-info: abs-path}
        build_data.setdefault("extra_metadata", {})
        build_data["extra_metadata"][f"sboms/{sbom_filename}"] = str(
            self._sbom_staging_path
        )

        log.info(
            "Loom: staged SBOM for .dist-info/sboms/%s (%d fragments merged)",
            sbom_filename,
            len(resolved_fragments),
        )

    def finalize(
        self,
        version: str,
        build_data: dict[str, Any],
        artifact_path: str,
    ) -> None:
        """Clean up temporary staging files after the wheel is packaged."""
        if self._staging_dir is not None:
            self._staging_dir.cleanup()
            self._staging_dir = None
            self._sbom_staging_path = None

    def _get_loom_config(self) -> dict[str, Any]:
        """Return the ``[tool.loom]`` section from pyproject.toml, if present.

        Falls back to ``self.config`` (the ``[tool.hatch.build.hooks.loom]``
        section) for hook-specific options.
        """
        # self.config is already the [tool.hatch.build.hooks.loom] section
        return dict(self.config)


def _resolve_fragments(
    project_dir: Path,
    fragment_paths: list[str],
) -> list[Path]:
    """Resolve fragment paths relative to the project root.

    Logs a warning for each path that does not exist.
    """
    resolved: list[Path] = []
    for frag in fragment_paths:
        p = project_dir / frag
        if p.exists():
            resolved.append(p)
        else:
            log.warning("Loom: fragment file not found, skipping: %s", p)
    return resolved
```

## Fragment merging and `[tool.loom]` configuration

Fragment paths listed under `[tool.hatch.build.hooks.loom] fragments` are
passed to `generate_sbom()` via the
`[tool.loom] fragments = [...]` mechanism already present in the metadata
extractor. The hook reads its own `self.config` (the
`[tool.hatch.build.hooks.loom]` table) and forwards the fragment list
to the generator.

This means the existing `metadata.py` fragment-merging logic is reused
unchanged; the hook only needs to pass the list of paths.

## Interaction diagram

```text
Developer runs:
  hatch build  OR  python -m build
         │
         ▼
  Hatchling build process
         │
         ├─── LoomBuildHook.initialize()
         │       │
         │       ├── generate_sbom(project_dir)
         │       │       │
         │       │       ├── extract_metadata_from_pyproject()
         │       │       ├── merge loom.bom fragments (if configured)
         │       │       └── Spdx3JsonExporter.to_json()
         │       │
         │       └── stage sbom.spdx3.json → TemporaryDirectory
         │               └── build_data["extra_metadata"]
         │                      ["sboms/sbom.spdx3.json"] = staged path
         │
         ├─── Hatchling packages wheel
         │       └── includes .dist-info/sboms/sbom.spdx3.json  ← PEP 770
         │
         └─── LoomBuildHook.finalize()
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
src/loom/
└── plugins/
    ├── __init__.py
    └── hatch.py            ← LoomBuildHook
tests/
└── test_hatch_hook.py
```

### Changes to Loom's `pyproject.toml`

Add the entry point so Hatchling can discover the plugin:

```toml
[project.entry-points."hatch.build.hook"]
loom = "loom.plugins.hatch:LoomBuildHook"
```

Add `hatchling` as a runtime dependency (needed in the hook code):

```toml
dependencies = [
    "hatchling",
    "pyproject-metadata>=0.10.0",
    "spdx-python-model>=0.0.4",
    "tomli>=2.0.0; python_version<'3.11'",
]
```

## Test plan

| Test | Description |
| :--- | :--- |
| `test_hook_initialize_adds_extra_metadata` | Calls `initialize()` and asserts `build_data["extra_metadata"]` contains the expected key. |
| `test_hook_finalize_cleans_up` | Asserts temp files are removed after `finalize()`. |
| `test_hook_disabled_skips_generation` | Sets `enabled = false` in config; asserts no key in `build_data`. |
| `test_hook_with_fragments` | Provides a valid fragment file; asserts it is merged in the output. |
| `test_hook_missing_fragment_logs_warning` | Provides a non-existent path; asserts a warning is logged, not an exception. |
| `test_pep770_path_format` | Asserts the key in `extra_metadata` is `"sboms/sbom.spdx3.json"`. |

## Open questions

- Hatchling's `extra_metadata` API is not yet widely documented for
  placing files in nested subdirectories inside `.dist-info/`. Verify with
  a real `hatch build` before finalising implementation.
  The `finalize()` fallback (injecting directly into the wheel zip) should
  be implemented as a safety net if `extra_metadata` does not support
  subdirectory nesting.
- PEP 770 does not yet specify whether multiple SBOM files (e.g., one per
  format) are permitted or whether a single canonical file is expected.
  Design the filename config option to be forward-compatible.

## References

- PEP 770: <https://peps.python.org/pep-0770/>
- Hatchling build hook reference: <https://hatch.pypa.io/latest/plugins/build-hook/reference/>
- Hatchling build hook interface: `hatchling.builders.hooks.plugin.interface.BuildHookInterface`
- Trivy PEP 770 tracking issue: <https://github.com/aquasecurity/trivy/issues/10021>
