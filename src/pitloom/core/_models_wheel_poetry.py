# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Poetry-core-backed wheel file discovery.

See also: :mod:`pitloom.core._models_wheel_dispatch` (dispatch facade),
:mod:`pitloom.core._models_wheel_types`,
:mod:`pitloom.core._models_wheel_hatchling` (same delegate-to-the-real-
library pattern this module follows).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pitloom.core._models_wheel_clone import LeftOut
from pitloom.core._models_wheel_guard import discovery_deadline
from pitloom.core._models_wheel_types import (
    IncludedFile,
    to_posix_distribution_path,
    warn_discovery_failed,
)
from pitloom.core.clone_mark import in_remote_clone

log = logging.getLogger(__name__)


def _confine(package: Any, project_dir: Path) -> None:
    """Leave out of the clone's poetry-core *package*, before anything walks
    them, the ``packages`` whose ``from`` or ``include`` and the
    ``include`` and ``exclude`` entries that reach out of the clone or into
    its ``.git``, each named as written in one ``WARNING:``
    (:class:`~pitloom.core._models_wheel_clone.LeftOut`)."""
    left = LeftOut(project_dir)
    package.packages = [
        item for item in package.packages if not _package_outside(item, left)
    ]
    package.include = [
        item
        for item in package.include
        if not left.pattern_outside(str(item.get("path", "")))
    ]
    package.exclude = left.kept([str(e) for e in package.exclude], left.pattern_outside)
    left.warn("pyproject.toml")


def _package_outside(item: dict[str, Any], left: LeftOut) -> bool:
    """Whether the ``packages`` entry *item* reads out of the clone or in
    its ``.git``: by its ``from`` folder, else by its ``include``."""
    source = item.get("from")
    if source is not None and (
        left.pattern_outside(str(source)) or left.outside(str(source))
    ):
        return True
    return left.pattern_outside(str(item.get("include", "")))


def discover(
    project_dir: Path,
    *,
    # pylint: disable-next=unused-argument
    pyproject_data: dict[str, object] | None = None,
) -> list[IncludedFile] | None:
    """Discover a wheel's file set using poetry-core's own ``WheelBuilder``.

    Uses :class:`~poetry.core.masonry.builders.wheel.WheelBuilder` to walk
    ``find_files_to_add()`` -- respecting every ``packages``/``include``/
    ``exclude`` rule from ``[tool.poetry]`` in ``pyproject.toml``, purely
    declarative like Hatchling's own discovery (no ``setup.py``-style
    arbitrary code execution). ``find_files_to_add()`` never runs
    ``[tool.poetry.build].script`` -- that only affects a real ``build()``,
    not file-list resolution -- so this stays a static-config read, not a
    build.

    A ``.git`` directory, when present, is consulted to additionally
    *exclude* ``.gitignore``-matched files; it is never required and never
    changes the *included* base set, so this is deterministic the same way
    the Hatchling delegation is.

    Returns ``None`` on any discovery failure (e.g. not a Poetry project,
    malformed config) -- the caller falls back accordingly.

    *pyproject_data* is accepted, not used, purely so this matches
    :class:`~pitloom.core._models_wheel_types.BackendDiscoverer`'s shared
    call signature. Unlike the setuptools discoverer (which reuses the
    caller's already-parsed dict), this one can't avoid a second read of
    ``pyproject.toml``: poetry-core's ``Factory.create_poetry()`` is the
    only public entry point into ``[tool.poetry]`` resolution and it always
    re-reads the file from *project_dir* itself, with no variant that
    accepts a pre-parsed mapping, so the extra read and parse per call is
    unavoidable.
    """
    # pylint: disable=import-outside-toplevel,cyclic-import
    from poetry.core.factory import Factory
    from poetry.core.masonry.builders.wheel import WheelBuilder

    try:
        with discovery_deadline(project_dir):
            poetry_project = Factory().create_poetry(project_dir)
            if in_remote_clone():
                _confine(poetry_project.package, project_dir)
            builder = WheelBuilder(poetry_project)
            return [
                IncludedFile(
                    path=str(included_file.path),
                    distribution_path=to_posix_distribution_path(
                        str(included_file.relative_to_target_root())
                    ),
                )
                for included_file in builder.find_files_to_add()
            ]
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        warn_discovery_failed(log, "Poetry", project_dir, exc)
        return None
