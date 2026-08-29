# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Hatchling-backed wheel file discovery.

See also: :mod:`pitloom.core._models_wheel` (dispatch facade),
:mod:`pitloom.core._models_wheel_types`.
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
    """Discover a wheel's file set using Hatchling's own ``WheelBuilder``.

    Uses :class:`~hatchling.builders.wheel.WheelBuilder` to walk
    ``recurse_included_files()`` -- respecting every include/exclude
    rule, ``force-include`` entry, and ``packages`` configuration from
    ``[tool.hatch.build...]`` in ``pyproject.toml``. This is a distinct
    method from ``WheelBuilder.build()`` and never runs custom Hatchling
    build hooks (``[tool.hatch.build.hooks.*]``'s ``initialize``/
    ``finalize``), so this stays a static-config read, not a build.

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
        return [
            IncludedFile(
                path=included_file.path,
                distribution_path=included_file.distribution_path.replace("\\", "/"),
            )
            for included_file in builder.recurse_included_files()
        ]
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        log.warning("Hatchling file discovery failed for %s: %s", project_dir, exc)
        return None
