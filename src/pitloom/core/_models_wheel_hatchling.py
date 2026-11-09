# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Hatchling-backed wheel file discovery.

See also: :mod:`pitloom.core._models_wheel_dispatch` (dispatch facade),
:mod:`pitloom.core._models_wheel_types`, :mod:`pitloom.core._models_wheel_clone`
(what a clone leaves out).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pitloom.core._models_wheel_clone import (
    clone_root,
    left_out,
    warn_build_code_ignored,
    warn_entries_left_out,
)
from pitloom.core._models_wheel_types import (
    IncludedFile,
    to_posix_distribution_path,
    warn_discovery_failed,
)
from pitloom.core.lfs_pointer import in_remote_clone

if TYPE_CHECKING:
    from hatchling.builders.wheel import WheelBuilder

log = logging.getLogger(__name__)


def _without_hooks(
    hatch: dict[str, Any], pyproject_hatch: object, project_dir: Path
) -> dict[str, Any]:
    """*hatch* (the merged ``[tool.hatch]`` and ``hatch.toml`` settings)
    without its metadata hooks, which load the repository's own code
    (``hatch_build.py``, a ``path``) when the file list is resolved, said
    in one ``WARNING:`` naming the file that declares them."""
    metadata = hatch.get("metadata")
    hooks = metadata.get("hooks") if isinstance(metadata, dict) else None
    if not (isinstance(metadata, dict) and isinstance(hooks, dict) and hooks):
        return hatch
    in_pyproject = (
        isinstance(pyproject_hatch, dict)
        and pyproject_hatch.get("metadata") is metadata
    )
    file, setting = (
        ("pyproject.toml", "tool.hatch.metadata.hooks")
        if in_pyproject
        else ("hatch.toml", "metadata.hooks")
    )
    warn_build_code_ignored(project_dir, file, [setting])
    return {
        **hatch,
        "metadata": {key: value for key, value in metadata.items() if key != "hooks"},
    }


def _force_include_kept(
    table: dict[str, Any], project_dir: Path, left: list[str]
) -> dict[str, Any]:
    """*table*'s ``force-include`` without the sources out of the clone
    (expanded as Hatchling expands them), each added to *left* as written,
    so no directory of the host is walked."""
    entries = table.get("force-include")
    if not isinstance(entries, dict):
        return table
    root = clone_root(project_dir)
    kept: dict[str, object] = {}
    for source, target in entries.items():
        expanded = os.path.expanduser(os.path.normpath(str(source)))
        if left_out(os.path.join(project_dir, expanded), root):
            left.append(str(source))
        else:
            kept[source] = target
    return {**table, "force-include": kept}


def _confine(builder: WheelBuilder, project_dir: Path) -> None:
    """Have *builder*, in a clone, run none of the repository's code and
    walk none of the host's directories: its metadata hooks and the
    ``force-include`` sources out of the clone are left out of its
    settings before anything reads them."""
    metadata = builder.metadata
    tool = metadata.config.get("tool")
    hatch_table = tool.get("hatch") if isinstance(tool, dict) else None
    hatch = _without_hooks(dict(metadata.hatch.config), hatch_table, project_dir)
    declared = hatch.get("build")
    left: list[str] = []
    if isinstance(declared, dict):
        build = _force_include_kept(declared, project_dir, left)
        targets = build.get("targets")
        if isinstance(targets, dict) and isinstance(targets.get("wheel"), dict):
            wheel = _force_include_kept(targets["wheel"], project_dir, left)
            build = {**build, "targets": {**targets, "wheel": wheel}}
        hatch["build"] = build
    warn_entries_left_out(project_dir, left)
    metadata.hatch.config = hatch


def discover(
    project_dir: Path,
    *,
    # pylint: disable-next=unused-argument
    pyproject_data: dict[str, object] | None = None,
) -> list[IncludedFile] | None:
    """Discover a wheel's file set using Hatchling's own ``WheelBuilder``.

    Uses :class:`~hatchling.builders.wheel.WheelBuilder` to walk
    ``recurse_included_files()`` -- respecting every include/exclude
    rule, ``force-include`` entry, and ``packages`` configuration from
    ``[tool.hatch.build...]`` in ``pyproject.toml``. This is a distinct
    method from ``WheelBuilder.build()`` and never runs custom Hatchling
    build hooks (``[tool.hatch.build.hooks.*]``'s ``initialize``/
    ``finalize``), so this stays a static-config read, not a build. A
    metadata hook does run (the project's name is read through it): in a
    Git URL's clone it is left out, as is a ``force-include`` source out of
    the clone (:func:`_confine`).

    Returns ``None`` on any discovery failure (e.g. not a Hatchling
    project, malformed config) -- the caller falls back accordingly.

    *pyproject_data* is accepted, not used, purely so this matches
    :class:`~pitloom.core._models_wheel_types.BackendDiscoverer`'s shared
    call signature -- ``WheelBuilder`` reads ``pyproject.toml`` itself.
    """
    # pylint: disable=import-outside-toplevel,cyclic-import
    from hatchling.builders.wheel import WheelBuilder

    try:
        builder = WheelBuilder(str(project_dir))
        if in_remote_clone():
            _confine(builder, project_dir)
        return [
            IncludedFile(
                path=included_file.path,
                distribution_path=to_posix_distribution_path(
                    included_file.distribution_path
                ),
            )
            for included_file in builder.recurse_included_files()
        ]
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        warn_discovery_failed(log, "Hatchling", project_dir, exc)
        return None
