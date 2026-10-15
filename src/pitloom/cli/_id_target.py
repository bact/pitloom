# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Where `pitloom id generate`/`import` write the registry: the target
resolution and the config hint.

See also: :mod:`pitloom.cli.id` (the commands).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import NamedTuple

from pitloom.extract.project import read_project

log = logging.getLogger("pitloom.id_registry")

#: The config table name and its file. A ``setup.cfg`` project selects
#: ``[tool:pitloom]``; anything else (a ``pyproject.toml``, or no config
#: file yet) selects ``[tool.pitloom]``. Every hint
#: (:func:`_log_config_hint`, the "no registry declared" ERROR) builds from
#: these names instead of re-deriving the selection.
_SETUP_CFG_TABLE = "[tool:pitloom]"
_PYPROJECT_TABLE = "[tool.pitloom]"
_TABLE_CONFIG_FILE = {
    _SETUP_CFG_TABLE: "setup.cfg",
    _PYPROJECT_TABLE: "pyproject.toml",
}


class _ConfigSlot(NamedTuple):
    """Where :func:`_log_config_hint` points: the config table, and
    whether that table already sets an ``id-registry``."""

    table: str
    has_key: bool


def _project_configured_id_registry(project_dir: Path) -> tuple[str | None, str]:
    """The project's own configured ``id-registry``, and which table it
    would live in -- resolved the same way
    :func:`pitloom.extract.project.read_project` selects between
    ``pyproject.toml``'s ``[tool.pitloom]`` and ``setup.cfg``'s
    ``[tool:pitloom]`` for every other Pitloom surface (see
    ``CLAUDE.md``'s "Usage surfaces": a hand-rolled pyproject.toml-only
    read here would silently diverge from that selection).

    Returns ``(None, _PYPROJECT_TABLE)`` when *project_dir* has no
    ``pyproject.toml``/``setup.cfg``/``setup.py`` at all -- nothing to
    read, not an error.
    """
    if not (
        os.path.isfile(project_dir / "pyproject.toml")
        or os.path.isfile(project_dir / "setup.cfg")
        or os.path.isfile(project_dir / "setup.py")
    ):
        return None, _PYPROJECT_TABLE
    _metadata, pitloom_config, config_path = read_project(
        project_dir,
        include_locked_dependencies=False,
        include_installed_metadata=False,
        quiet=True,
    )
    table = (
        _SETUP_CFG_TABLE
        if config_path is not None and config_path.name == "setup.cfg"
        else _PYPROJECT_TABLE
    )
    return pitloom_config.id_registry, table


def _normalized_absolute(path: Path) -> Path:
    """``path.absolute()``, then ``os.path.normpath()`` to collapse
    lexical ``..``/``.`` segments for display -- never ``.resolve()``,
    which would also follow a symlink (see the dangling-symlink note in
    :func:`_resolve_id_registry_target`)."""
    return Path(os.path.normpath(path.absolute()))


def _no_id_registry_declared_error(table: str) -> ValueError:
    """The ``ValueError`` `pitloom id generate`/`import` raise when
    neither a flag nor the project's own config declares a registry
    location -- no implicit default file is assumed (see docs/cli.md's
    "Pin ids across fragments")."""
    return ValueError(
        "no ID registry declared: pass --id-registry FILE or set "
        f"id-registry in {table}"
    )


def _resolve_id_registry_target(
    flag: Path | None, project_dir: Path
) -> tuple[Path, bool, _ConfigSlot]:
    """Resolve the registry path `pitloom id generate`/`import` writes to.

    Precedence: *flag* (``--id-registry``/``-o``; a relative *flag*
    resolves against the current directory, like every other command --
    ``id import``'s own *project_dir* already *is* the current directory,
    so this is only observable for ``id generate`` with a ``--project-dir``
    different from cwd), else the project's own configured ``id-registry``
    (see :func:`_project_configured_id_registry`; relative to
    *project_dir*). Raises :func:`_no_id_registry_declared_error` when
    neither is declared -- there is no implicit default file.
    Returns ``(path, declared_by_config, slot)`` -- *declared_by_config* is
    ``True`` exactly when *path* is the project's own declared
    ``id-registry`` (whether that came from the config's own key or from a
    *flag* that happens to name the same file), i.e. exactly when a config
    hint (see :func:`_run_id_generate`) is *not* worth printing afterwards;
    *slot* names the ``[tool.pitloom]``/``[tool:pitloom]`` table that hint
    should point at, and whether it already declares another registry.
    """
    # .absolute() only, never .resolve(): resolving would follow a dangling
    # symlink at the final path component to its (nonexistent) target and
    # write through it there instead of surfacing IdRegistry.load()'s own
    # "not found or not a file" error at the symlink's own path.
    # normpath() after .absolute() only collapses lexical ".."/"." noise
    # (e.g. a `-o ../x` display) -- it never touches a symlink itself, so
    # the dangling-symlink behaviour above is preserved.
    if flag is not None:
        path = _normalized_absolute(flag)
        # A broken/invalid config must not fail this call when a flag
        # already names the target explicitly (see
        # _project_configured_id_registry's own callers for the case where
        # it must raise) -- only used here, best-effort, to decide whether
        # *flag* happens to name the project's own declared file.
        try:
            configured, table = _project_configured_id_registry(project_dir)
        except (ValueError, OSError):
            configured, table = None, _PYPROJECT_TABLE
        configured_path = (
            _normalized_absolute(project_dir / configured)
            if configured is not None
            else None
        )
        slot = _ConfigSlot(table, configured is not None)
        return path, path == configured_path, slot
    # No flag: the project's own config is read unconditionally, so a
    # broken/invalid config raises here and takes precedence over the
    # "nothing declared" error below.
    configured, table = _project_configured_id_registry(project_dir)
    if configured is not None:
        path = _normalized_absolute(project_dir / configured)
        # Declared by the config itself, so no hint is logged: the slot is unused.
        return path, True, _ConfigSlot(table, True)
    raise _no_id_registry_declared_error(table)


def _log_config_hint(registry_path: Path, project_dir: Path, slot: _ConfigSlot) -> None:
    """Log the ``id-registry = ...`` config hint after a fresh save, when
    *registry_path* didn't already come from the project's own config.

    When the table already declares another ``id-registry``, the hint says
    to change that key, never to add a second one (a duplicate TOML key
    fails to parse).

    ``pyproject.toml`` is TOML, where quotes are string syntax, so the
    value is formatted with :func:`json.dumps` (a valid TOML string
    literal). ``setup.cfg`` is INI: :func:`~pitloom.extract.project.
    setuptools_cfg._read_pitloom_config_from_cfg` reads a string
    ``[tool:pitloom]`` value with ``str.strip()`` only, never stripping
    quotes, so a quoted hint pasted verbatim would become part of the
    value itself -- the value is emitted unquoted here instead.
    """
    try:
        rel = registry_path.relative_to(project_dir).as_posix()
    except ValueError:
        rel = registry_path.as_posix()
    where = f"{slot.table} in {_TABLE_CONFIG_FILE[slot.table]}"
    value = json.dumps(rel) if slot.table == _PYPROJECT_TABLE else rel
    action = f"change id-registry in {where} to" if slot.has_key else f"add to {where}"
    log.info("ID registry: to use this registry, %s: id-registry = %s", action, value)
