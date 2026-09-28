# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Loom ID registry resolution for a project or a project-less target.

See also: :mod:`pitloom.id_registry._registry` for ``IdRegistry`` itself.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pitloom.id_registry._registry import IdRegistry

log = logging.getLogger("pitloom.id_registry")

__all__ = ["resolve_explicit_registry", "resolve_registry"]


def resolve_registry(
    project_dir: Path,
    id_registry: str | Path | IdRegistry | None = None,
) -> IdRegistry | None:
    """Resolve the registry a project build should consult."""
    if isinstance(id_registry, IdRegistry):
        return id_registry
    if id_registry is not None:
        path = Path(id_registry)
        registry_path = path if path.is_absolute() else project_dir / path
        try:
            return IdRegistry.load(registry_path)
        except (FileNotFoundError, ValueError, OSError) as exc:
            log.warning("ID registry: could not load %s: %s", registry_path, exc)
            return None
    return IdRegistry.find(start=project_dir)


def resolve_explicit_registry(
    id_registry: str | Path | IdRegistry | None,
    configured_id_registry: str | None,
) -> IdRegistry | None:
    """Resolve the registry for a target with no project of its own (a
    wheel, an installed environment, a model file).

    Only an explicit source counts: *id_registry* (``--id-registry``), else
    *configured_id_registry* from an explicitly named config. Unlike
    :func:`resolve_registry`, this never searches for a
    ``loom-id-registry.json`` -- one found near the current directory
    belongs to whatever project that is, not to this target. A relative
    path resolves against the current directory;
    :func:`pitloom.core.config_cascade.load_config_file` has already made a
    config's own ``id-registry`` absolute.
    """
    source = id_registry if id_registry is not None else configured_id_registry
    if source is None:
        return None
    return resolve_registry(Path.cwd(), source)
