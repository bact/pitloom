# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Flit-core-backed wheel file discovery.

See also: :mod:`pitloom.core._models_wheel` (dispatch facade),
:mod:`pitloom.core._models_wheel_types`,
:mod:`pitloom.core._models_wheel_poetry` (same delegate-to-the-real-
library pattern this module follows); :mod:`pitloom.extract._flit`
(the sibling metadata-side module, sharing the same
``flit_core.config.read_flit_config`` + ``flit_core.common.Module``
lookup).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from pitloom.core._models_wheel_types import (
    IncludedFile,
    to_posix_distribution_path,
)

log = logging.getLogger(__name__)


def discover(
    project_dir: Path,
    *,
    # pylint: disable-next=unused-argument
    pyproject_data: dict[str, object] | None = None,
) -> list[IncludedFile] | None:
    """Discover a wheel's file set using flit-core's own module resolution.

    Mirrors ``flit_core.wheel.WheelBuilder.copy_module()``/
    ``add_data_directory()`` exactly: the target module's files (via
    ``Module.iter_files()``, relative to ``module.source_dir`` -- so a
    ``src/``-layout project's distribution paths already have the
    ``src/`` prefix stripped, matching a real Flit wheel) plus any
    ``[tool.flit.external-data]`` directory contents (mapped to
    ``<dist>.data/data/...``, the same scheme path a real wheel uses).
    Purely declarative -- flit-core has no build script/hook system to
    execute, unlike setuptools' ``setup.py``.

    Computing the ``<dist>.data/`` prefix needs the project's
    name/version, but never via flit-core's ``make_metadata()``: for a
    project with ``dynamic = ["version"]`` whose ``__version__`` isn't a
    literal assignment (e.g. computed by a function call), flit-core's
    own ``get_info_from_module()`` falls back to *importing* (executing)
    the target module -- exactly the code-execution risk this static
    rescan must never take (see :mod:`pitloom.extract._setuptools`'s
    same stance on ``setup.py``). Reads ``loaded_cfg.metadata`` (the
    statically-declared ``[project]`` fields) first; if ``version`` is
    dynamic, tries an AST-only scan
    (``flit_core.common.get_docstring_and_version_via_ast``, no import)
    before giving up and excluding the external-data files with a
    ``WARNING:`` rather than risk executing project code.

    Returns ``None`` on any discovery failure (e.g. not a Flit project,
    malformed config, module not found) -- the caller falls back
    accordingly.

    *pyproject_data* is accepted, not used, for the same reason
    :mod:`pitloom.core._models_wheel_poetry` ignores it: flit-core's own
    ``read_flit_config()`` is the only public entry point and always
    re-reads ``pyproject.toml`` itself.
    """
    # pylint: disable=import-outside-toplevel,cyclic-import
    from flit_core.common import (
        Module,
        get_docstring_and_version_via_ast,
        normalize_dist_name,
        walk_data_dir,
    )
    from flit_core.config import read_flit_config

    try:
        loaded_cfg = read_flit_config(project_dir / "pyproject.toml")
        module = Module(loaded_cfg.module, project_dir)
        source_dir = str(module.source_dir)

        files = [
            IncludedFile(
                path=full_path,
                distribution_path=to_posix_distribution_path(
                    os.path.relpath(full_path, source_dir)
                ),
            )
            for full_path in module.iter_files()
        ]

        if loaded_cfg.data_directory is not None:
            name = loaded_cfg.metadata.get("name") or loaded_cfg.module
            version = loaded_cfg.metadata.get("version")
            if version is None:
                # Dynamic version: AST-only resolution, same as
                # pitloom.extract._flit's own approach -- never falls
                # back to importing the module the way flit-core's own
                # get_info_from_module()/make_metadata() would.
                _, version = get_docstring_and_version_via_ast(module)

            if version is None:
                log.warning(
                    "%s: could not resolve a static version for "
                    "[tool.flit.external-data] without executing the "
                    "project's module -- external-data files excluded "
                    "from this result",
                    project_dir,
                )
            else:
                dist_name = normalize_dist_name(name, version)
                for full_path in walk_data_dir(loaded_cfg.data_directory):
                    rel_path = os.path.relpath(full_path, loaded_cfg.data_directory)
                    files.append(
                        IncludedFile(
                            path=full_path,
                            distribution_path=to_posix_distribution_path(
                                f"{dist_name}.data/data/{rel_path}"
                            ),
                        )
                    )

        return files
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        log.warning("Flit file discovery failed for %s: %s", project_dir, exc)
        return None
