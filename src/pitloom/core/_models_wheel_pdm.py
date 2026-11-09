# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""PDM-backend-backed wheel file discovery.

See also: :mod:`pitloom.core._models_wheel_dispatch` (dispatch facade --
this backend is registered with ``needs_write_lock=True``, see
:class:`~pitloom.core._models_wheel_dispatch._RegisteredBackend`),
:mod:`pitloom.core._models_wheel_types`,
:mod:`pitloom.core._models_wheel_setuptools` (the other "writer"
backend, same ``discovery_chdir`` contract); :mod:`pitloom.extract.project.pdm` (the
sibling metadata-side module, sharing this ``Builder``/``Context``
construction pattern and its custom-build-hook caveat, documented there),
:mod:`pitloom.core._models_wheel_clone` (what a clone leaves out).
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from collections.abc import Iterable
from importlib.metadata import entry_points
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pitloom.core._models_wheel_clone import warn_build_code_ignored
from pitloom.core._models_wheel_guard import discovery_chdir, discovery_deadline
from pitloom.core._models_wheel_types import (
    IncludedFile,
    to_posix_distribution_path,
    warn_discovery_failed,
)
from pitloom.core.clone_mark import in_remote_clone

if TYPE_CHECKING:
    from pdm.backend.hooks import BuildHookInterface
    from pdm.backend.wheel import WheelBuilder

log = logging.getLogger(__name__)


def plugin_hooks() -> list[Any]:
    """The build hooks of the installed PDM plugins (entry points of the
    ``pdm.build.hook`` group): a hook class made once, or a hook module."""
    hooks: list[Any] = []
    for entry_point in entry_points(group="pdm.build.hook"):
        hook = entry_point.load()
        try:
            hooks.append(hook())  # a hook class
        except TypeError:
            hooks.append(hook)  # a hook module
    return hooks


def wheel_builder(project_dir: Path, plugins: list[Any] | None = None) -> WheelBuilder:
    """pdm-backend's ``WheelBuilder`` for *project_dir*; in a Git URL's
    clone, one that loads none of the repository's own build hooks: the
    local hook (``pdm_build.py`` or ``custom-hook``), imported when the
    builder is made, and ``run-setuptools``, which runs ``setup.py`` when
    the files are listed. The hooks of installed plugins run as usual:
    *plugins* (:func:`plugin_hooks`, loaded before the working directory
    is the clone), else loaded when the builder is made."""
    # pylint: disable=import-outside-toplevel
    from pdm.backend.hooks.setuptools import SetuptoolsBuildHook
    from pdm.backend.wheel import WheelBuilder

    if not in_remote_clone():
        return WheelBuilder(project_dir)

    class _CloneWheelBuilder(WheelBuilder):
        """Loads the hooks :func:`wheel_builder` keeps."""

        def get_hooks(self) -> Iterable[BuildHookInterface]:
            build = self.config.build_config
            ignored = [
                setting
                for setting, named in (
                    ("tool.pdm.build.custom-hook", build.custom_hook is not None),
                    ("tool.pdm.build.run-setuptools", build.run_setuptools),
                )
                if named
            ]
            warn_build_code_ignored(project_dir, "pyproject.toml", ignored)
            yield from (h for h in self.hooks if not isinstance(h, SetuptoolsBuildHook))
            yield from plugin_hooks() if plugins is None else plugins

    return _CloneWheelBuilder(project_dir)


def discover(
    project_dir: Path,
    *,
    # pylint: disable-next=unused-argument
    pyproject_data: dict[str, object] | None = None,
) -> list[IncludedFile] | None:
    """Discover a wheel's file set using pdm-backend's own ``WheelBuilder``.

    Uses :class:`~pdm.backend.wheel.WheelBuilder` (not the plain
    ``Builder`` base) so a ``src/``-layout project's ``package-dir``
    config is normalised away the same way a real PDM wheel would --
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

    Never calls ``builder.initialize(context)`` either: that runs
    ``DynamicVersionBuildHook.pdm_build_initialize()``, which -- for a
    project declaring ``[tool.pdm.version] source = "scm"`` together
    with a ``write_to`` option -- writes the resolved version string to
    a real file under ``context.build_dir`` (``.pdm-build/<write_to>``)
    as a side effect of resolving the version, the same kind of
    build-time write ``_get_metadata_files()`` was already excluded
    for above. File discovery never needs the resolved version at all
    (``_collect_files()``/``_get_wheel_data()`` don't read
    ``metadata["version"]``), so skipping ``initialize()`` changes
    nothing about the returned file set either -- only avoids the write.

    ``context.build_dir`` points at a path guaranteed never to exist on
    disk, never *project_dir* / ``.pdm-build`` itself: the base
    ``Builder``'s ``get_files()`` unconditionally globs ``build_dir`` for
    extra files via ``_collect_build_files()``, so pointing it at the
    project's own ``.pdm-build/`` would leak any *stale* content left
    over from a real ``pdm build`` the user ran earlier (that
    directory is normally only gitignored, not cleaned up) straight into
    the returned file list -- a static rescan must reflect the source
    tree, not leftovers of a past build.

    Returns ``None`` on any discovery failure (e.g. not a PDM project,
    malformed config) -- the caller falls back accordingly.

    The builder loads the project's own build hook (``pdm_build.py``),
    whose ``pdm_build_update_files`` runs here, and with ``run-setuptools``
    runs ``setup.py``: in a Git URL's clone neither is loaded
    (:func:`wheel_builder`).

    *pyproject_data* is accepted, not used, for the same reason
    :mod:`pitloom.core._models_wheel_poetry` ignores it: pdm-backend's
    own ``Config.from_pyproject()`` always re-reads ``pyproject.toml``
    itself, with no variant accepting a pre-parsed mapping.
    """
    # pylint: disable=import-outside-toplevel,cyclic-import
    from pdm.backend.base import Builder as PDMBuilder
    from pdm.backend.hooks.base import Context

    try:
        plugins = plugin_hooks() if in_remote_clone() else None
        with discovery_chdir(project_dir), discovery_deadline(project_dir):
            builder = wheel_builder(project_dir, plugins)
            context = Context(
                # A path that never exists (a random UUID under the
                # system temp root, never created), so
                # _collect_build_files()'s `if not
                # context.build_dir.exists()` guard short-circuits and
                # never picks up stale build output (see docstring). Not
                # tempfile.TemporaryDirectory(): that creates a directory
                # only to prove non-existence, and this call holds the
                # discovery dispatcher's exclusive write lock (see
                # discovery_chdir's docstring), so extra I/O blocks every other
                # discoverer for longer.
                build_dir=Path(tempfile.gettempdir())
                / f"pitloom-unused-{uuid.uuid4().hex}",
                dist_dir=project_dir,
                kwargs={},
                builder=builder,
            )
            files = list(PDMBuilder.get_files(builder, context))
            # pylint: disable-next=protected-access
            files.extend(builder._get_wheel_data(context))
        return [
            IncludedFile(
                path=str(full_path),
                distribution_path=to_posix_distribution_path(rel_path),
            )
            for rel_path, full_path in files
        ]
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        warn_discovery_failed(log, "PDM", project_dir, exc)
        return None
