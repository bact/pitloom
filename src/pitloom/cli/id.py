# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``loom id``: create and update the Loom ID registry."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Any

from pitloom.cli._id_args import entity_arg, namespace_arg, registry_file_arg
from pitloom.cli._id_entity import EntityEntry, entity_entry, say_stored_as
from pitloom.cli._id_target import (
    _log_config_hint,
    _normalized_absolute,
    _resolve_id_registry_target,
    resolve_dataset_hash_ceiling,
    resolve_id_refuse,
)
from pitloom.cli._parser_credentials import (
    REFUSE_HELP_ID_GENERATE,
    REFUSE_HELP_ID_IMPORT,
    add_refuse_argument,
)
from pitloom.cli._path_args import non_empty_path
from pitloom.cli.commands.utils import cli_error_handler
from pitloom.cli.kv_output import print_kv
from pitloom.cli.options import positive_byte_ceiling
from pitloom.core.current_dir import current_dir
from pitloom.core.given_path import TypedPath, keep_spelling
from pitloom.id_registry import (
    IdRegistry,
    check_key_credentials,
    require_registry_namespace,
    save_registry,
    say_ambiguous_keys,
)
from pitloom.messages import CodedValueError, say_summary
from pitloom.messages.id_registry import HOLDS_IDS, say_save_failure
from pitloom.messages.options import OPTION_INVALID, PATH_OUTSIDE_LINE
from pitloom.messages.targets import (
    INPUT_NOT_FOUND,
    NO_ID_PATHS_LINE,
    is_input_dir,
    is_input_file,
    refuse_empty_input,
    say_input_not_found,
)

log = logging.getLogger("pitloom.id_registry")

#: Candidate directory names for `loom id generate`'s implicit-paths
#: fallback (see :func:`_default_id_generate_paths`). CLI-only: no other
#: id_registry consumer needs this list.
_DEFAULT_ID_GENERATE_DIR_NAMES: tuple[str, ...] = ("src", "data", "models")


def _load_or_create_registry(
    registry_path: Path,
    project_dir_name: str,
    *,
    namespace: str | None = None,
    project_root: Path | None = None,
    refuse_credentials: bool = False,
) -> IdRegistry:
    """Load the registry at *registry_path*, or create a fresh one if
    nothing exists there yet, with *namespace* and *project_root* (both
    only for a new registry: an existing one keeps its own), in the
    ``url-credentials`` mode *refuse_credentials*.

    Raises ``ValueError`` (from :meth:`~pitloom.id_registry.IdRegistry.load`)
    when *registry_path* exists but doesn't load, or ``FileNotFoundError``
    when what is there is not a file.
    """
    if not os.path.lexists(registry_path):
        return IdRegistry.new(
            project_dir_name,
            path=registry_path,
            namespace=namespace,
            project_root=project_root,
            refuse_credentials=refuse_credentials,
        )
    return IdRegistry.load(registry_path, refuse_credentials=refuse_credentials)


def _default_id_generate_paths(project_dir: Path) -> list[Path]:
    """Return default candidate paths for `loom id generate`."""
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
    say_summary(log, HOLDS_IDS, number=registry.id_count())


def _save(registry: IdRegistry, registry_path: Path) -> bool:
    """Save *registry* (loaded from or created for *registry_path*) through
    the one registry write routine
    (:func:`~pitloom.id_registry.save_registry`), which keeps what another
    run saved meanwhile; on failure say the one ``ERROR:`` line of what
    stopped it (:func:`~pitloom.messages.id_registry.say_save_failure`) and
    return ``False``."""
    try:
        save_registry(registry)
    except (ValueError, OSError) as exc:
        say_save_failure(log, exc, file=registry_path, fatal=True)
        return False
    return True


def _generate_paths(args: argparse.Namespace, project_dir: Path) -> list[Path]:
    """The `id generate` PATHs, each rooted at *project_dir*; ``ValueError``
    for one outside it, or when there is none to index;
    ``input-not-found`` for an empty one.

    A relative PATH resolves against the current directory, like every
    other command, and is made absolute before ``IdRegistry.generate()``
    sees it, so the file walk's "relative -> under project_root" rule
    never applies. The implicit default paths stay under
    ``--project-dir``. Every returned path is rooted at the resolved
    *project_dir*.
    """
    if args.paths:
        lexical_project_dir = _normalized_absolute(args.project_dir or current_dir())
        paths: list[Path] = []
        for path in args.paths:
            # Where a missing PATH is said (after the registry is settled):
            # an empty one reads as the current directory.
            refuse_empty_input(path, "PATH")
            resolved = _resolve_id_generate_path(path, project_dir, lexical_project_dir)
            if resolved is None:
                raise CodedValueError(
                    OPTION_INVALID,
                    line=PATH_OUTSIDE_LINE,
                    path=path,
                    root=args.project_dir or project_dir,
                )
            # The typed spelling rides along, for a warning to name it.
            paths.append(keep_spelling(resolved, path))
    else:
        paths = _default_id_generate_paths(project_dir)
    if not paths:
        raise CodedValueError(
            INPUT_NOT_FOUND,
            line=NO_ID_PATHS_LINE,
            path=args.project_dir or project_dir,
        )
    return paths


def _id_refuse(args: argparse.Namespace, project_dir: Path) -> bool:
    """Whether this `loom id` run refuses a credential (see
    :func:`pitloom.cli._id_target.resolve_id_refuse`): the project's config
    is read without ``-o``, or best-effort with ``-o`` and an explicit
    ``--project-dir``."""
    return resolve_id_refuse(
        args.refuse_url_credentials,
        project_dir,
        read_config=args.id_registry is None or args.project_dir is not None,
        best_effort=args.id_registry is not None,
    )


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
        refuse_credentials=_id_refuse(args, project_dir),
    )
    if not is_new:
        registry.require_project_root(project_dir)
        if args.namespace is not None:
            registry.require_namespace(args.namespace)
    return registry


def _register_entities(
    args: argparse.Namespace, project_dir: Path, registry: IdRegistry
) -> list[tuple[str, EntityEntry]]:
    """Register each ``-e`` entity under its key and SHA-256, and return
    each NAME and entry for :func:`~pitloom.cli._id_entity.say_stored_as`
    to say once the registry is saved; raises ``ValueError`` for an
    unreadable project config when a dataset needs its
    ``max-dataset-hash-bytes``."""
    entities: list[tuple[str, str]] = args.entity or []
    ceiling = resolve_dataset_hash_ceiling(
        args.max_dataset_hash_bytes, project_dir, [t for t, _ in entities]
    )
    stored: list[tuple[str, EntityEntry]] = []
    for type_name, name in entities:
        # Before entity_entry says anything about the entity.
        check_key_credentials(type_name, name, refuse=registry.refuse_credentials)
        entry = entity_entry(registry, project_dir, type_name, name, ceiling)
        registry.register(type_name, entry.key, sha256=entry.sha256)
        stored.append((name, entry))
    return stored


def _run_id_generate(args: argparse.Namespace) -> int:
    """Run `loom id generate`."""
    if args.namespace is not None:
        require_registry_namespace(args.namespace)  # before any file is read
    project_dir: Path = (args.project_dir or current_dir()).resolve()
    if not is_input_dir(project_dir, shown=args.project_dir or project_dir):
        say_input_not_found("project directory", args.project_dir or project_dir)
        return 1
    # A failure here is the one ERROR line of cli_error_handler.
    registry_path, from_project_key, slot = _resolve_id_registry_target(
        args.id_registry, project_dir
    )
    is_new = not os.path.lexists(registry_path)
    registry = _open_generate_registry(args, project_dir, registry_path, is_new)
    paths = _generate_paths(args, project_dir)
    registry.generate(
        paths, project_dir, exclude=registry_path, explicit=bool(args.paths)
    )
    stored = _register_entities(args, project_dir, registry)
    if not _save(registry, registry_path):
        return 1
    # A repeated -e is said once, in the order first given.
    for name, entry in dict.fromkeys(stored):
        say_stored_as(name, entry)
    _report_registry_written(registry_path, registry)
    if is_new and not from_project_key:
        _log_config_hint(registry_path, project_dir, slot)
    return 0


def _run_id_import(args: argparse.Namespace) -> int:
    """Run `loom id import`."""
    refuse_empty_input(args.sbom, "SBOM file")
    sbom_path: Path = args.sbom.resolve()
    if not is_input_file(sbom_path, shown=args.sbom):
        say_input_not_found("SBOM file", args.sbom)
        return 1

    project_dir: Path = (args.project_dir or current_dir()).resolve()
    if not is_input_dir(project_dir, shown=args.project_dir or project_dir):
        say_input_not_found("project directory", args.project_dir or project_dir)
        return 1
    # A failure here is the one ERROR line of cli_error_handler.
    registry_path, from_project_key, slot = _resolve_id_registry_target(
        args.id_registry, project_dir
    )
    is_new = not os.path.lexists(registry_path)
    registry = _load_or_create_registry(
        registry_path,
        sbom_path.stem,
        project_root=project_dir,
        refuse_credentials=_id_refuse(args, project_dir),
    )
    if not is_new and args.project_dir is not None:
        registry.require_project_root(project_dir)
    # The path as given: a line about the SBOM names it as the user did.
    skipped = registry.import_sbom(args.sbom)

    if not _save(registry, registry_path):
        return 1
    _report_registry_written(registry_path, registry)
    if skipped:
        say_ambiguous_keys(log, "not imported", skipped)
    if is_new and not from_project_key:
        _log_config_hint(registry_path, project_dir, slot)
    return 0


@cli_error_handler
def _run_id_command(args: argparse.Namespace) -> int:
    """Dispatch `loom id <command> ...` arguments; an exception no command
    handled is one ``ERROR:`` line (status 1)."""
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
        type=TypedPath,
        default=None,
        help="Files or directories to index.",
    )
    gen_parser.add_argument(
        "-o",
        "--id-registry",
        type=registry_file_arg,
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
        type=non_empty_path,
        default=None,
        help="Project directory root.",
    )
    gen_parser.add_argument(
        "--namespace",
        type=namespace_arg,
        default=None,
        metavar="IRI",
        help=(
            "Document namespace of a new registry: an absolute IRI without "
            "'#'. Default: one minted from the project directory's name and "
            "a random UUID."
        ),
    )
    gen_parser.add_argument(
        "-e",
        "--entity",
        action="append",
        type=entity_arg,
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
            "id). A package is NAME@VERSION (one release); a NAME with no "
            "@VERSION holds only a package that states no version."
        ),
    )
    add_refuse_argument(gen_parser, REFUSE_HELP_ID_GENERATE)
    gen_parser.add_argument(
        "--max-dataset-hash-bytes",
        type=positive_byte_ceiling,
        default=None,
        metavar="BYTES",
        help=(
            "Most bytes read to hash one dataset given with -e (a file, or "
            "all files of a directory together); a dataset over it is "
            "pinned without a hash. An integer of at least 1. Default: "
            "max-dataset-hash-bytes in the project config, else 4 GiB."
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
        type=TypedPath,
        help="Source SBOM JSON file to import.",
    )
    imp_parser.add_argument(
        "-o",
        "--id-registry",
        type=registry_file_arg,
        default=None,
        metavar="FILE",
        help=(
            "Registry file to update. Required unless the project config "
            "declares id-registry (pyproject.toml [tool.pitloom] or "
            "setup.cfg [tool:pitloom])."
        ),
    )
    imp_parser.add_argument(
        "--project-dir",
        type=non_empty_path,
        default=None,
        help=(
            "Project directory root: a new registry's root, which the SBOM's "
            "file names are relative to. An existing registry must have this "
            "root. Default: the current directory (not checked against an "
            "existing registry)."
        ),
    )
    add_refuse_argument(imp_parser, REFUSE_HELP_ID_IMPORT)

    id_parser.set_defaults(func=_run_id_command)
