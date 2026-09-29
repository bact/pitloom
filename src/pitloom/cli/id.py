# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from pitloom.extract.project import read_project
from pitloom.id_registry import IdRegistry

log = logging.getLogger("pitloom.id_registry")

#: Candidate directory names for `pitloom id generate`'s implicit-paths
#: fallback (see :func:`_default_id_generate_paths`). CLI-only: no other
#: id_registry consumer needs this list.
_DEFAULT_ID_GENERATE_DIR_NAMES: tuple[str, ...] = ("src", "data", "models")


def _load_or_create_registry(registry_path: Path, project_dir_name: str) -> IdRegistry:
    """Load the registry at *registry_path*, or create a fresh one if
    nothing exists there yet.

    Raises ``ValueError`` (from :meth:`~pitloom.id_registry.IdRegistry.load`)
    when *registry_path* exists but doesn't load -- never returns ``None``.
    """
    if not os.path.lexists(registry_path):
        return IdRegistry.new(project_dir_name, path=registry_path)
    return IdRegistry.load(registry_path)


#: Bare ``[tool.pitloom]``-style table name, keyed by the config file
#: basename :func:`_project_configured_id_registry` reports
#: (``pitloom.core.project.read_project``'s ``config_path``). Anything
#: else (no config file at all, or a ``pyproject.toml``) defaults to the
#: ``pyproject.toml`` table -- the common case, and the only one possible
#: when there is no config file yet to add the key to. The single source
#: of the pyproject.toml-vs-setup.cfg selection: every caller that needs
#: a human-readable hint (:func:`_log_config_hint`'s INFO line, the "no
#: registry declared" ERROR) builds it from this table name rather than
#: re-deriving the selection itself.
_SETUP_CFG_TABLE = "[tool:pitloom]"
_PYPROJECT_TABLE = "[tool.pitloom]"
_TABLE_CONFIG_FILE = {
    _SETUP_CFG_TABLE: "setup.cfg",
    _PYPROJECT_TABLE: "pyproject.toml",
}


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
    which would also follow a symlink (see the dangling-symlink note at
    this function's own call sites)."""
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
) -> tuple[Path, bool, str]:
    """Resolve the registry path `pitloom id generate`/`import` writes to.

    Precedence: *flag* (``--id-registry``/``-o``; a relative *flag*
    resolves against the current directory, like every other command --
    ``id import``'s own *project_dir* already *is* the current directory,
    so this is only observable for ``id generate`` with a ``--project-dir``
    different from cwd), else the project's own configured ``id-registry``
    (see :func:`_project_configured_id_registry`; relative to
    *project_dir*). Raises :func:`_no_id_registry_declared_error` when
    neither is declared -- there is no implicit default file.
    Returns ``(path, declared_by_config, table)`` -- *declared_by_config* is
    ``True`` exactly when *path* is the project's own declared
    ``id-registry`` (whether that came from the config's own key or from a
    *flag* that happens to name the same file), i.e. exactly when a config
    hint (see :func:`_run_id_generate`) is *not* worth printing afterwards;
    *table* names the ``[tool.pitloom]``/``[tool:pitloom]`` table that hint
    should point at.
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
        return path, path == configured_path, table
    # No flag: the project's own config is read unconditionally, so a
    # broken/invalid config raises here and takes precedence over the
    # "nothing declared" error below.
    configured, table = _project_configured_id_registry(project_dir)
    if configured is not None:
        return _normalized_absolute(project_dir / configured), True, table
    raise _no_id_registry_declared_error(table)


def _log_config_hint(registry_path: Path, project_dir: Path, table: str) -> None:
    """Log the ``id-registry = ...`` config hint after a fresh save, when
    *registry_path* didn't already come from the project's own config.

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
    hint = f"{table} in {_TABLE_CONFIG_FILE[table]}"
    value = json.dumps(rel) if table == _PYPROJECT_TABLE else rel
    log.info(
        "ID registry: to use this registry, add to %s: id-registry = %s",
        hint,
        value,
    )


def _default_id_generate_paths(project_dir: Path) -> list[Path]:
    """Return default candidate paths for `pitloom id generate`."""
    return [
        project_dir / name
        for name in _DEFAULT_ID_GENERATE_DIR_NAMES
        if (project_dir / name).exists()
    ]


def _resolve_id_generate_path(
    path: Path, project_dir: Path, lexical_project_dir: Path
) -> Path | None:
    """Resolve one `id generate` PATH argument to a path rooted at
    *project_dir* (already ``.resolve()``d by the caller).

    Tries the lexical (unresolved) form first, against both
    *lexical_project_dir* (the ``--project-dir`` value as given, only
    made absolute -- see :func:`_normalized_absolute`) and *project_dir*
    itself -- so an in-project symlink that points outside the project
    (e.g. ``proj/models -> ../bigdisk/models``) still resolves under the
    project, the same as :func:`_default_id_generate_paths`'s own
    existence-only check. Falls back to ``os.path.realpath()`` relative
    to *project_dir* for a PATH reached only through a symlink from
    *outside* the project (e.g. a symlinked source directory). Returns
    ``None`` when neither form lands inside *project_dir*.

    ``..`` is collapsed lexically (via :func:`_normalized_absolute`'s
    ``os.path.normpath()``) before any symlink is followed, for both the
    lexical and the ``os.path.realpath()`` forms.
    """
    lexical = _normalized_absolute(path)
    for base in (lexical_project_dir, project_dir):
        try:
            rel = lexical.relative_to(base)
        except ValueError:
            continue
        return project_dir / rel
    real = Path(os.path.realpath(path))
    try:
        rel = real.relative_to(project_dir)
    except ValueError:
        return None
    return project_dir / rel


def _run_id_generate(args: argparse.Namespace) -> int:
    """Run `pitloom id generate`."""
    project_dir: Path = (args.project_dir or Path.cwd()).resolve()
    try:
        registry_path, from_project_key, table = _resolve_id_registry_target(
            args.id_registry, project_dir
        )
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    is_new = not os.path.lexists(registry_path)

    try:
        registry = _load_or_create_registry(registry_path, project_dir.name)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # A relative PATH argument resolves against the current directory,
    # like every other command -- absolutise before generate() ever sees
    # it, so IdRegistry._iter_files()'s own "relative -> under
    # project_root" fallback (meant for a project_dir-relative registry
    # key, not a CLI argument) never applies here. The implicit default
    # paths stay under --project-dir, already absolute.
    #
    # _resolve_id_generate_path() tries the lexical (unresolved) path
    # first -- so an in-project symlink stays keyed by its lexical
    # location, matching _default_id_generate_paths()'s own
    # existence-only check -- and only falls back to os.path.realpath()
    # for a PATH reached only through a symlink from outside the
    # project. Either way the stored path is rooted at project_dir
    # (already .resolve()'d), so _registry.py's own
    # `file_path.relative_to(project_root)` sees consistent, comparable
    # trees.
    if args.paths:
        lexical_project_dir = _normalized_absolute(args.project_dir or Path.cwd())
        paths: list[Path] = []
        for path in args.paths:
            resolved = _resolve_id_generate_path(path, project_dir, lexical_project_dir)
            if resolved is None:
                print(
                    f"ERROR: PATH {path} is outside --project-dir {project_dir}",
                    file=sys.stderr,
                )
                return 1
            paths.append(resolved)
    else:
        paths = _default_id_generate_paths(project_dir)
    if not paths:
        print(
            f"ERROR: no source/data directories found under {project_dir}; "
            "pass explicit PATH argument(s).",
            file=sys.stderr,
        )
        return 1

    try:
        registry.generate(paths, project_dir)
        for entity_spec in args.entity or []:
            name, _, type_name = entity_spec.partition(":")
            registry.register_entity(name, type_name or "ai_AIPackage")
        registry.save(registry_path)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"pitloom id: wrote {len(registry.files)} file(s) and "
        f"{len(registry.entities)} entit(y/ies) to {registry_path}"
    )
    if is_new and not from_project_key:
        _log_config_hint(registry_path, project_dir, table)
    return 0


def _run_id_import(args: argparse.Namespace) -> int:
    """Run `pitloom id import`."""
    sbom_path: Path = args.sbom.resolve()
    if not os.path.isfile(sbom_path):
        print(f"ERROR: SBOM file not found: {sbom_path}", file=sys.stderr)
        return 1

    project_dir = Path.cwd()
    try:
        registry_path, from_project_key, table = _resolve_id_registry_target(
            args.id_registry, project_dir
        )
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    is_new = not os.path.lexists(registry_path)

    try:
        registry = _load_or_create_registry(registry_path, sbom_path.stem)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        registry.import_sbom(sbom_path)
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        print(f"ERROR: failed to import SBOM {sbom_path}: {exc}", file=sys.stderr)
        return 1

    try:
        registry.save(registry_path)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"pitloom id: imported into {registry_path} "
        f"({len(registry.files)} file(s), {len(registry.entities)} entit(y/ies))"
    )
    if is_new and not from_project_key:
        _log_config_hint(registry_path, project_dir, table)
    return 0


def _run_id_command(args: argparse.Namespace) -> int:
    """Dispatch `pitloom id <command> ...` arguments."""
    if args.id_command == "generate":
        return _run_id_generate(args)
    if args.id_command == "import":
        return _run_id_import(args)
    return 1


def add_parser(subparsers: Any, _parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``id`` subcommand to the main parser."""
    id_parser = subparsers.add_parser(
        "id",
        help="Manage the Loom ID registry.",
        description=(
            "Manage the Loom ID registry, a stable file/entity -> SPDX ID "
            "registry consulted by 'pitloom.loom', the Hatchling build hook, "
            "and the CLI -- only when named explicitly (a flag, or a "
            "config's own id-registry key); never searched for."
        ),
    )
    id_subparsers = id_parser.add_subparsers(dest="id_command", required=True)

    gen_parser = id_subparsers.add_parser(
        "generate",
        help="Index files (and detected AI models) under PATHs into the registry.",
    )
    gen_parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=None,
        help="Files or directories to index.",
    )
    gen_parser.add_argument(
        "-o",
        "--id-registry",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Registry file to update. Required unless the project config "
            "declares id-registry (pyproject.toml [tool.pitloom] or "
            "setup.cfg [tool:pitloom])."
        ),
    )
    gen_parser.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help="Project directory root.",
    )
    gen_parser.add_argument(
        "-e",
        "--entity",
        action="append",
        default=None,
        metavar="NAME[:TYPE]",
        help="Explicit entity name to register.",
    )

    imp_parser = id_subparsers.add_parser(
        "import",
        help="Import entries from an external SBOM file.",
    )
    imp_parser.add_argument(
        "sbom",
        type=Path,
        help="Source SBOM JSON file to import.",
    )
    imp_parser.add_argument(
        "-o",
        "--id-registry",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Registry file to update. Required unless the project config "
            "declares id-registry (pyproject.toml [tool.pitloom] or "
            "setup.cfg [tool:pitloom])."
        ),
    )

    id_parser.set_defaults(func=_run_id_command)
