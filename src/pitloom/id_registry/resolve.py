# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Loom ID registry resolution for a project or a project-less target.

See also: :mod:`pitloom.id_registry._registry` for ``IdRegistry`` itself.
"""

from __future__ import annotations

import os
from pathlib import Path

from pitloom.id_registry._registry import IdRegistry

__all__ = ["registry_base_dir", "resolve_registry"]


def registry_base_dir(target: Path) -> Path:
    """The base directory a relative declared ``id-registry`` path
    resolves against, for a *target* that may be either a project
    directory or a single file (e.g. an sdist archive).

    A file target has no directory of its own to resolve a relative
    registry path against -- :func:`~pitloom.core.project.read_project`
    resolves an sdist archive's own config keys relative to the archive
    itself, but a registry path is not read from inside the archive, so
    that convention doesn't apply here. Falls back to the current
    directory instead, same as the no-``project_dir`` case.

    Shared by every ``resolve_registry()`` call site that resolves a
    *target* which might be an sdist (or, in :mod:`pitloom.embed`, any
    single-file ``project_dir``) -- callers that already know they have a
    directory (or already know they have none, using ``Path.cwd()``
    directly) don't need this helper.
    """
    return Path.cwd() if os.path.isfile(target) else target


def resolve_registry(
    id_registry: str | Path | IdRegistry | None,
    configured: str | None,
    base_dir: Path,
) -> IdRegistry | None:
    """Resolve the registry a build should consult -- an explicit source
    only, never searched for.

    Precedence: *id_registry* (a flag/kwarg, or an already-loaded
    :class:`IdRegistry`), else *configured* (the applicable config's own
    ``id-registry``: the project's own ``[tool.pitloom]``, or an explicit
    ``--config``, which replaces it). Neither given: ``None``, silently --
    no ``loom-id-registry.json`` is searched for, near the target or
    anywhere else. A relative path resolves against *base_dir* (the
    project directory, or the current directory for a target with none of
    its own); an already-absolute path (e.g. a config's own key, made
    absolute by :func:`~pitloom.core.config_cascade.load_config_file`, or
    a CLI flag made absolute against cwd) is used as given.

    Raises ``ValueError`` (via :meth:`IdRegistry.load`) when the resolved
    path does not load -- a declared registry is always meant to load;
    this function never swallows that failure.
    """
    source = id_registry if id_registry is not None else configured
    if source is None:
        return None
    if isinstance(source, IdRegistry):
        return source
    path = Path(source)
    return IdRegistry.load(path if path.is_absolute() else base_dir / path)
