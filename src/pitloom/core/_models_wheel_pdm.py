# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""PDM-backend-backed wheel file discovery.

See also: :mod:`pitloom.core._models_wheel` (dispatch facade -- this
backend is registered as a "writer", see ``_WRITER_BACKENDS`` there),
:mod:`pitloom.core._models_wheel_types`,
:mod:`pitloom.core._models_wheel_setuptools` (the other "writer"
backend, same ``_chdir`` contract); :mod:`pitloom.extract._pdm` (the
sibling metadata-side module, sharing this ``Builder``/``Context``
construction pattern and its custom-build-hook caveat, documented there).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pitloom.core._models_wheel_types import IncludedFile

log = logging.getLogger(__name__)


@contextmanager
def _chdir(project_dir: Path) -> Iterator[None]:
    """pdm-backend's own package auto-discovery
    (``pdm.backend.base._find_top_packages``) globs relative to the
    process's current working directory, not the ``Builder``'s own
    ``location`` -- so, like setuptools, discovery needs to run from
    *project_dir* for the duration of the call.

    This process-wide ``os.chdir()`` is only safe because
    :mod:`pitloom.core._models_wheel` -- the sole caller of
    :func:`discover` -- runs every call to this function under its
    read/write discovery lock's exclusive write mode (this backend is
    listed in ``_WRITER_BACKENDS`` there), which keeps it from
    overlapping any other backend's discovery call; this module holds
    no lock of its own.
    """
    original_cwd = Path.cwd()
    os.chdir(project_dir)
    try:
        yield
    finally:
        os.chdir(original_cwd)


def discover(
    project_dir: Path,
    *,
    # pylint: disable-next=unused-argument
    pyproject_data: dict[str, object] | None = None,
) -> list[IncludedFile] | None:
    """Discover a wheel's file set using pdm-backend's own ``WheelBuilder``.

    Uses :class:`~pdm.backend.wheel.WheelBuilder` (not the plain
    ``Builder`` base) so a ``src/``-layout project's ``package-dir``
    config is normalized away the same way a real PDM wheel would --
    ``WheelBuilder._collect_files()`` overrides the base class
    specifically to strip that prefix, which the base class alone does
    not do (see the ``physical_path``/``distribution_path`` split every
    backend's discovery module must get right).

    Deliberately calls the base ``Builder.get_files()`` (via an unbound
    call, so ``self._collect_files()`` still resolves to
    ``WheelBuilder``'s override) plus ``_get_wheel_data()`` directly,
    **not** ``WheelBuilder.get_files()`` itself: the latter also calls
    ``_get_metadata_files()``, which unconditionally *writes*
    ``METADATA``/``WHEEL``/``RECORD``/license files to
    ``context.build_dir`` on disk (via ``context.ensure_build_dir()``) --
    a real build-time side effect this static rescan must never trigger.
    Metadata files are excluded from every other backend's discoverer
    too, so skipping that call changes nothing about the returned file
    set, only avoids writing to disk to get it.

    Never calls ``Builder.build()``/``build_context()`` either (the
    latter also ``mkdir()``s a destination directory) -- constructs a
    :class:`~pdm.backend.hooks.base.Context` directly, pointed at
    *project_dir* itself (already on disk, never written to by anything
    called here) instead of a build output directory.

    Returns ``None`` on any discovery failure (e.g. not a PDM project,
    malformed config) -- the caller falls back accordingly.

    *pyproject_data* is accepted, not used, for the same reason
    :mod:`pitloom.core._models_wheel_poetry` ignores it: pdm-backend's
    own ``Config.from_pyproject()`` always re-reads ``pyproject.toml``
    itself, with no variant accepting a pre-parsed mapping.
    """
    # pylint: disable=import-outside-toplevel,cyclic-import
    from pdm.backend.base import Builder as PDMBuilder
    from pdm.backend.hooks.base import Context
    from pdm.backend.wheel import WheelBuilder

    try:
        with _chdir(project_dir):
            builder = WheelBuilder(project_dir)
            context = Context(
                build_dir=project_dir / ".pdm-build",
                dist_dir=project_dir,
                kwargs={},
                builder=builder,
            )
            builder.initialize(context)
            files = list(PDMBuilder.get_files(builder, context))
            # pylint: disable-next=protected-access
            files.extend(builder._get_wheel_data(context))
        return [
            IncludedFile(path=str(full_path), distribution_path=rel_path)
            for rel_path, full_path in files
        ]
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        log.warning("PDM file discovery failed for %s: %s", project_dir, exc)
        return None
