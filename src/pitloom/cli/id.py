# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``pitloom id``: create and update the Loom ID registry."""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from pitloom.cli._id_entity import entity_entry
from pitloom.cli._id_target import (
    _log_config_hint,
    _normalized_absolute,
    _resolve_id_registry_target,
)
from pitloom.cli.kv_output import print_kv
from pitloom.core.iri import require_namespace_iri
from pitloom.core.quote_source import quote_source
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    PACKAGE_TYPE,
    IdRegistry,
    ambiguous_keys_message,
    failed_to_save_message,
    save_registry,
)

log = logging.getLogger("pitloom.id_registry")

#: Candidate directory names for `pitloom id generate`'s implicit-paths
#: fallback (see :func:`_default_id_generate_paths`). CLI-only: no other
#: id_registry consumer needs this list.
_DEFAULT_ID_GENERATE_DIR_NAMES: tuple[str, ...] = ("src", "data", "models")

#: The TYPEs ``id generate -e NAME:TYPE`` accepts: the types a lookup reads.
_ENTITY_TYPES: tuple[str, ...] = (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    PACKAGE_TYPE,
)
#: The shape of an SPDX 3 compact type name (``prefix_ClassName``).
_COMPACT_TYPE = re.compile(r"[a-z]+_[A-Z][A-Za-z0-9]*")


def _load_or_create_registry(
    registry_path: Path,
    project_dir_name: str,
    *,
    namespace: str | None = None,
    project_root: Path | None = None,
) -> IdRegistry:
    """Load the registry at *registry_path*, or create a fresh one if
    nothing exists there yet, with *namespace* and *project_root* (both
    only for a new registry: an existing one keeps its own).

    Raises ``ValueError`` (from :meth:`~pitloom.id_registry.IdRegistry.load`)
    when *registry_path* exists but doesn't load.
    """
    if not os.path.lexists(registry_path):
        return IdRegistry.new(
            project_dir_name,
            path=registry_path,
            namespace=namespace,
            project_root=project_root,
        )
    return IdRegistry.load(registry_path)


def _namespace_arg(text: str) -> str:
    """``type=`` callable for ``--namespace``: validate through
    :func:`~pitloom.core.iri.require_namespace_iri`, reported the normal
    argparse way (``argument --namespace: ...``, exit code 2)."""
    try:
        return require_namespace_iri(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _registry_file_arg(text: str) -> Path:
    """``type=`` callable for ``-o``: a file path, never ``-``: a registry is
    not written to stdout, and ``-`` would name a file called ``-``."""
    if text == "-":
        raise argparse.ArgumentTypeError("'-' (stdout) is not supported")
    return Path(text)


def _entity_arg(text: str) -> tuple[str, str]:
    """``type=`` callable for ``-e NAME[:TYPE]``: ``(TYPE, NAME)``.

    Split at the last ``:`` only when what follows is one of
    :data:`_ENTITY_TYPES`, so the ``:`` of a URL or a drive letter stays in
    NAME. A typo is reported the argparse way (exit 2), never silently made
    part of NAME: a trailing ``:``, a suffix shaped like a compact type, a
    known one in another case or with whitespace around it, a control
    character (a newline) anywhere, and an empty or blank NAME.
    """
    if any(unicodedata.category(char) == "Cc" for char in text):
        raise argparse.ArgumentTypeError(f"control character in {text!r}")
    name, _, suffix = text.rpartition(":")
    if suffix in _ENTITY_TYPES:
        type_name = suffix
    elif (
        text.endswith(":")
        or _COMPACT_TYPE.fullmatch(suffix.strip())
        or suffix.strip().lower() in {known.lower() for known in _ENTITY_TYPES}
    ):
        raise argparse.ArgumentTypeError(
            f"unknown TYPE {suffix!r} (one of: {', '.join(_ENTITY_TYPES)})"
        )
    else:
        name, type_name = text, AI_PACKAGE_TYPE
    if not name.strip():
        raise argparse.ArgumentTypeError(f"no NAME in {text!r}")
    return type_name, name


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
    *lexical_project_dir* (the ``--project-dir`` value as given, only made
    absolute) and *project_dir*, so an in-project symlink that points
    outside the project (``proj/models -> ../bigdisk/models``) still keys
    under the project. Falls back to ``os.path.realpath()`` for a PATH
    reached only through a symlink from outside the project. Returns
    ``None`` when neither form lands inside *project_dir*. ``..`` is
    collapsed lexically (:func:`_normalized_absolute`) before any symlink
    is followed, in the fallback too: ``link/..`` is the directory above
    ``link`` as written, not above its target.
    """
    lexical = _normalized_absolute(path)
    for base in (lexical_project_dir, project_dir):
        try:
            rel = lexical.relative_to(base)
        except ValueError:
            continue
        return project_dir / rel
    real = Path(os.path.realpath(lexical))
    try:
        rel = real.relative_to(project_dir)
    except ValueError:
        return None
    return project_dir / rel


def _report_registry_written(registry_path: Path, registry: IdRegistry) -> None:
    """Print the ``PITLOOM_ID_REGISTRY_PATH=<path>`` data line for the
    registry just saved, and log what it now holds."""
    print_kv(PITLOOM_ID_REGISTRY_PATH=registry_path)
    log.info("ID registry: holds %d id(s)", registry.id_count())


def _save(registry: IdRegistry, registry_path: Path) -> bool:
    """Save *registry* (loaded from or created for *registry_path*) through
    the one registry write routine
    (:func:`~pitloom.id_registry.save_registry`), which keeps what another
    run saved meanwhile; on failure print the one ``ERROR:`` failed-to-save
    line and return ``False``."""
    try:
        save_registry(registry)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {failed_to_save_message(registry_path, exc)}", file=sys.stderr)
        return False
    return True


def _generate_paths(args: argparse.Namespace, project_dir: Path) -> list[Path]:
    """The `id generate` PATHs, each rooted at *project_dir*; ``ValueError``
    for one outside it, or when there is none to index.

    A relative PATH resolves against the current directory, like every
    other command, and is made absolute before ``IdRegistry.generate()``
    sees it, so the file walk's "relative -> under project_root" rule
    never applies. The implicit default paths stay under
    ``--project-dir``. Every returned path is rooted at the resolved
    *project_dir*.
    """
    if args.paths:
        lexical_project_dir = _normalized_absolute(args.project_dir or Path.cwd())
        paths: list[Path] = []
        for path in args.paths:
            resolved = _resolve_id_generate_path(path, project_dir, lexical_project_dir)
            if resolved is None:
                raise ValueError(f"PATH {path} is outside --project-dir {project_dir}")
            paths.append(resolved)
    else:
        paths = _default_id_generate_paths(project_dir)
    if not paths:
        raise ValueError(
            f"no source/data directories found under {project_dir}; "
            "pass explicit PATH argument(s)."
        )
    return paths


def _open_generate_registry(
    args: argparse.Namespace, project_dir: Path, registry_path: Path, is_new: bool
) -> IdRegistry:
    """Load or create the registry for `id generate`, checking an existing
    one against *project_dir* and ``--namespace``; raises ``ValueError``."""
    registry = _load_or_create_registry(
        registry_path,
        project_dir.name,
        namespace=args.namespace,
        project_root=project_dir,
    )
    if not is_new:
        registry.require_project_root(project_dir)
        if args.namespace is not None:
            registry.require_namespace(args.namespace)
    return registry


def _run_id_generate(args: argparse.Namespace) -> int:
    """Run `pitloom id generate`."""
    project_dir: Path = (args.project_dir or Path.cwd()).resolve()
    if not os.path.isdir(project_dir):
        print(
            f"ERROR: --project-dir {quote_source(args.project_dir)} is not a directory",
            file=sys.stderr,
        )
        return 1
    try:
        registry_path, from_project_key, slot = _resolve_id_registry_target(
            args.id_registry, project_dir
        )
        is_new = not os.path.lexists(registry_path)
        registry = _open_generate_registry(args, project_dir, registry_path, is_new)
        paths = _generate_paths(args, project_dir)
        registry.generate(
            paths, project_dir, exclude=registry_path, explicit=bool(args.paths)
        )
        for type_name, name in args.entity or []:
            key, sha256 = entity_entry(registry, project_dir, type_name, name)
            registry.register(type_name, key, sha256=sha256)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not _save(registry, registry_path):
        return 1
    _report_registry_written(registry_path, registry)
    if is_new and not from_project_key:
        _log_config_hint(registry_path, project_dir, slot)
    return 0


def _run_id_import(args: argparse.Namespace) -> int:
    """Run `pitloom id import`."""
    sbom_path: Path = args.sbom.resolve()
    if not os.path.isfile(sbom_path):
        print(f"ERROR: SBOM file not found: {quote_source(sbom_path)}", file=sys.stderr)
        return 1

    project_dir = Path.cwd()
    try:
        registry_path, from_project_key, slot = _resolve_id_registry_target(
            args.id_registry, project_dir
        )
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    is_new = not os.path.lexists(registry_path)

    try:
        registry = _load_or_create_registry(
            registry_path, sbom_path.stem, project_root=project_dir
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        skipped = registry.import_sbom(sbom_path)
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        print(
            f"ERROR: failed to import SBOM {quote_source(sbom_path)}: {exc}",
            file=sys.stderr,
        )
        return 1

    if not _save(registry, registry_path):
        return 1
    _report_registry_written(registry_path, registry)
    if skipped:
        log.info("%s", ambiguous_keys_message("not imported", skipped))
    if is_new and not from_project_key:
        _log_config_hint(registry_path, project_dir, slot)
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
            "Manage the Loom ID registry, a typed ID registry (compact type "
            "and path or name -> SPDX ID) consulted by 'pitloom.loom', the Hatchling "
            "build hook, and the CLI -- only when named explicitly (a flag, "
            "or a config's own id-registry key); never searched for."
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
        type=_registry_file_arg,
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
        "--namespace",
        type=_namespace_arg,
        default=None,
        metavar="IRI",
        help=(
            "Document namespace of a new registry: an absolute IRI without "
            "'#'. Default: one minted from the project name and a random UUID."
        ),
    )
    gen_parser.add_argument(
        "-e",
        "--entity",
        action="append",
        type=_entity_arg,
        default=None,
        metavar="NAME[:TYPE]",
        help=(
            "Register NAME under TYPE (default: ai_AIPackage; also "
            "dataset_DatasetPackage, software_File, software_Package). NAME "
            "may hold ':' (a URL, a drive letter). A dataset, model or file "
            "that exists below --project-dir (a model or file: a regular "
            "file) is stored by its path, with its content hash: other "
            "content gets a new id. Else it is stored by name; a model "
            "name then holds only for a model with no file (a Hugging Face "
            "id)."
        ),
    )

    imp_parser = id_subparsers.add_parser(
        "import",
        help=(
            "Import entries from an external SBOM file (a model or dataset "
            "under the key a run looks it up by)."
        ),
    )
    imp_parser.add_argument(
        "sbom",
        type=Path,
        help="Source SBOM JSON file to import.",
    )
    imp_parser.add_argument(
        "-o",
        "--id-registry",
        type=_registry_file_arg,
        default=None,
        metavar="FILE",
        help=(
            "Registry file to update. Required unless the project config "
            "declares id-registry (pyproject.toml [tool.pitloom] or "
            "setup.cfg [tool:pitloom])."
        ),
    )

    id_parser.set_defaults(func=_run_id_command)
