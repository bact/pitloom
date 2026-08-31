# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Poetry-core-backed wheel file discovery.

See also: :mod:`pitloom.core._models_wheel` (dispatch facade),
:mod:`pitloom.core._models_wheel_types`,
:mod:`pitloom.core._models_wheel_hatchling` (same delegate-to-the-real-
library pattern this module follows).
"""

from __future__ import annotations

import logging
from pathlib import Path

from pitloom.core._models_wheel_types import IncludedFile

log = logging.getLogger(__name__)


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
    call signature -- poetry-core's ``Factory`` reads ``pyproject.toml``
    itself.
    """
    # pylint: disable=import-outside-toplevel,cyclic-import
    from poetry.core.factory import Factory
    from poetry.core.masonry.builders.wheel import WheelBuilder

    try:
        poetry_project = Factory().create_poetry(project_dir)
        builder = WheelBuilder(poetry_project)
        return [
            IncludedFile(
                path=str(included_file.path),
                distribution_path=str(included_file.relative_to_target_root()).replace(
                    "\\", "/"
                ),
            )
            for included_file in builder.find_files_to_add()
        ]
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        log.warning("Poetry file discovery failed for %s: %s", project_dir, exc)
        return None
