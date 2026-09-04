from __future__ import annotations

import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import hatchling.metadata.core as hatchling_metadata_core  # noqa: E402
import pytest
from hatchling.plugin.manager import PluginManager  # noqa: E402

from pitloom.plugins.hatch import (  # noqa: E402
    PitloomBuildHook,
)

"""Tests for the Pitloom Hatchling build hook (pitloom.plugins.hatch)."""

pytest.importorskip("hatchling", reason="hatchling is required for hook tests")

MINIMAL_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "testpkg"
version = "0.1.0"
description = "Test package."
requires-python = ">=3.10"
"""


def make_hook(
    root: str,
    config: dict[str, Any],
    target_name: str = "wheel",
) -> PitloomBuildHook:
    """Construct a ``PitloomBuildHook`` without invoking
    ``BuildHookInterface.__init__``.

    ``BuildHookInterface`` stores ``root``, ``config``, ``build_config``,
    ``project_metadata``, and ``target_name`` under mangled names and exposes them as
    read-only properties, so we set the mangled attributes directly via
    ``object.__setattr__``.  A bare ``SimpleNamespace`` satisfies
    ``build_config`` -- ``initialize()`` does not access it (file discovery
    uses ``WheelBuilder`` directly), but the slot must exist to prevent
    ``AttributeError`` from base-class property access.

    ``project_metadata`` is a real ``hatchling.metadata.core.ProjectMetadata`` bound
    to *root*, matching what Hatchling itself passes to a build hook; its
    properties are evaluated lazily, so constructing it does not require
    ``root`` to contain a valid ``pyproject.toml`` yet.
    """
    hook: PitloomBuildHook = object.__new__(PitloomBuildHook)
    object.__setattr__(hook, "_BuildHookInterface__root", root)
    object.__setattr__(hook, "_BuildHookInterface__config", config)
    object.__setattr__(
        hook, "_BuildHookInterface__build_config", types.SimpleNamespace()
    )
    object.__setattr__(
        hook,
        "_BuildHookInterface__metadata",
        hatchling_metadata_core.ProjectMetadata(root, PluginManager()),
    )
    object.__setattr__(hook, "_BuildHookInterface__target_name", target_name)
    hook._staging_dir = None
    hook._sbom_staging_path = None
    hook._sbom_filename = "sbom.spdx3.json"
    return hook


def write_pyproject(directory: Path, content: str = MINIMAL_PYPROJECT) -> None:
    """Write ``content`` as ``pyproject.toml`` in ``directory``."""
    (directory / "pyproject.toml").write_text(content, encoding="utf-8")


def write_pyproject_with_pitloom_config(directory: Path, extra_toml: str) -> None:
    """Write ``MINIMAL_PYPROJECT`` plus *extra_toml* (e.g. a ``[tool.pitloom]``
    or ``[tool.pitloom.creation]`` block) as ``pyproject.toml``."""
    write_pyproject(directory, MINIMAL_PYPROJECT + "\n" + extra_toml)


_FAKE_CORE_DEFAULTS: dict[str, Any] = {
    "description": "",
    "readme_path": "",
    "readme": "",
    "requires_python": "",
    "license": "",
    "license_expression": "",
    "license_files": [],
    "keywords": [],
    "authors_data": {"name": [], "email": []},
    "urls": {},
    "dependencies": [],
}


def _fake_hatch_metadata(
    *,
    name: str = "fakepkg",
    version: str = "1.0.0",
    core: dict[str, Any] | None = None,
) -> SimpleNamespace:
    """Build a lightweight duck-typed stand-in for Hatchling's
    ``hatchling.metadata.core.ProjectMetadata`` (``.core`` + ``.version``).

    *core* overrides individual ``_FAKE_CORE_DEFAULTS`` fields (including
    ``raw_name``, which defaults to *name*), e.g.
    ``_fake_hatch_metadata(core={"license_expression": "MIT"})``.

    The fake ``core.config`` (the raw, unprocessed ``[project]`` table --
    see :func:`pitloom.extract.hatchling._resolve_hatchling_license_files`)
    gets a ``"license-files"`` key exactly when *core* explicitly overrides
    ``license_files``, mirroring how a real declared field would show up in
    both places at once.
    """
    merged_core = {"raw_name": name, **_FAKE_CORE_DEFAULTS, **(core or {})}
    config: dict[str, Any] = {}
    if core is not None and "license_files" in core:
        config["license-files"] = merged_core["license_files"]
    return SimpleNamespace(
        name=name,
        version=version,
        core=SimpleNamespace(config=config, **merged_core),
    )


SYNTHETIC_NONCANONICAL_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "My_Package.Extra"
version = "1.0.0"
dependencies = ["typing_extensions>=4.0", "zope.interface>=5.0"]
"""

CONFLICT_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "testpkg"
version = "1.0.0"
license = "MIT"
"""

MISSING_README_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "testpkg"
version = "0.1.0"
readme = "MISSING.md"
"""

MISSING_LICENSE_FILE_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "testpkg"
version = "0.1.0"
license = {file = "MISSING-LICENSE.txt"}
"""

POETRY_GAP_FILL_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "testpkg"
version = "0.1.0"
description = "Test package."

[tool.poetry]
name = "testpkg"
version = "0.1.0"
authors = ["Poetry Author <poetry@example.com>"]
keywords = ["from-poetry", "gap-fill"]
"""

PYPROJECT_WITH_PRETTY = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "testpkg"
version = "0.1.0"
description = "Test package."
requires-python = ">=3.10"

[tool.pitloom]
pretty = true
"""


__all__ = [
    "Any",
    "CONFLICT_PYPROJECT",
    "MINIMAL_PYPROJECT",
    "MISSING_LICENSE_FILE_PYPROJECT",
    "MISSING_README_PYPROJECT",
    "POETRY_GAP_FILL_PYPROJECT",
    "PYPROJECT_WITH_PRETTY",
    "Path",
    "PitloomBuildHook",
    "PluginManager",
    "SYNTHETIC_NONCANONICAL_PYPROJECT",
    "SimpleNamespace",
    "_FAKE_CORE_DEFAULTS",
    "_fake_hatch_metadata",
    "annotations",
    "hatchling_metadata_core",
    "make_hook",
    "pytest",
    "types",
    "write_pyproject",
    "write_pyproject_with_pitloom_config",
]

__all__ = [
    "Any",
    "CONFLICT_PYPROJECT",
    "MINIMAL_PYPROJECT",
    "MISSING_LICENSE_FILE_PYPROJECT",
    "MISSING_README_PYPROJECT",
    "POETRY_GAP_FILL_PYPROJECT",
    "PYPROJECT_WITH_PRETTY",
    "Path",
    "PitloomBuildHook",
    "PluginManager",
    "SYNTHETIC_NONCANONICAL_PYPROJECT",
    "SimpleNamespace",
    "_FAKE_CORE_DEFAULTS",
    "_fake_hatch_metadata",
    "annotations",
    "hatchling_metadata_core",
    "make_hook",
    "pytest",
    "types",
    "write_pyproject",
    "write_pyproject_with_pitloom_config",
]
