# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Loom ID registry resolution for a project or a project-less target,
and a file path's key relative to a registry's project root.

See also: :mod:`pitloom.id_registry._registry` for ``IdRegistry`` itself.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePath

from pitloom.core.path_confine import inside_ancestor
from pitloom.id_registry._registry import IdRegistry

__all__ = [
    "registry_base_dir",
    "registry_file_path",
    "registry_key_for_path",
    "resolve_registry",
]


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


def registry_file_path(registry: IdRegistry | None) -> Path | None:
    """The file *registry* was loaded from, to leave out of every project
    file walk (see :func:`~pitloom.core.walk_rules.same_path`); ``None``
    with no registry or an in-memory one, which excludes nothing."""
    return registry.path if registry is not None else None


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
    its own), itself resolved first, so the loaded registry's path (and
    every message naming it) is absolute even for a relative *base_dir*;
    an already-absolute path (e.g. a config's own key, made absolute by
    :func:`~pitloom.core.config_cascade.load_config_file`, or a CLI flag
    made absolute against cwd) is used as given.

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
    return IdRegistry.load(path if path.is_absolute() else base_dir.resolve() / path)


def registry_key_for_path(registry: IdRegistry, path: Path) -> str | None:
    """*path*'s ``software_File`` key in *registry*: the path relative to
    :meth:`IdRegistry.root_dir`, ``/``-separated -- ``id generate``'s keying,
    whatever the current directory. ``None`` when *path* lies outside the
    root (another drive included); the root itself is ``"."``.

    A relative *path* is taken from the current directory. Tried first
    lexically (``..`` collapsed, no symlink followed), so an in-project
    file symlink keys by its own location, as ``id generate`` keys it; then
    an ancestor of that lexical path that is the root by file identity
    (reached through a symlinked ancestor: macOS ``/tmp`` is
    ``/private/tmp``; or spelt in another case), the remainder kept as
    spelt; last through ``os.path.realpath`` (a symlink from outside into
    the root), matching an ancestor by spelling or identity (see
    :func:`~pitloom.core.path_confine.inside_ancestor`). Never raises.
    """
    root = PurePath(registry.root_dir())
    lexical = PurePath(os.path.normpath(os.path.join(os.getcwd(), path)))
    ancestor = inside_ancestor(lexical, root)
    if ancestor is not None:
        return lexical.relative_to(ancestor).as_posix()
    try:
        real = PurePath(os.path.realpath(lexical))
    except ValueError:  # a NUL: no file to resolve
        return None
    ancestor = inside_ancestor(real, root)
    return None if ancestor is None else real.relative_to(ancestor).as_posix()
