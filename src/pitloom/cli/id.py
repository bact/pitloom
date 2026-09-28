# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from pitloom.id_registry import DEFAULT_ID_REGISTRY_FILENAME, IdRegistry

#: Candidate directory names for `pitloom id generate`'s implicit-paths
#: fallback (see :func:`_default_id_generate_paths`). CLI-only: no other
#: id_registry consumer needs this list.
_DEFAULT_ID_GENERATE_DIR_NAMES: tuple[str, ...] = ("src", "data", "models")


def _load_or_create_registry(
    registry_path: Path, project_dir_name: str
) -> IdRegistry | None:
    """Load existing registry from registry_path or return a new one."""
    if registry_path.exists():
        try:
            return IdRegistry.load(registry_path)
        # pylint: disable=broad-exception-caught
        except Exception as exc:
            print(
                f"ERROR: failed to load registry from {registry_path}: {exc}",
                file=sys.stderr,
            )
            return None

    namespace = f"https://spdx.org/spdxdocs/{project_dir_name}-{uuid4()}"
    return IdRegistry(namespace=namespace)


def _default_id_generate_paths(project_dir: Path) -> list[Path]:
    """Return default candidate paths for `pitloom id generate`."""
    return [
        project_dir / name
        for name in _DEFAULT_ID_GENERATE_DIR_NAMES
        if (project_dir / name).exists()
    ]


def _run_id_generate(args: argparse.Namespace) -> int:
    """Run `pitloom id generate`."""
    project_dir: Path = (args.project_dir or Path.cwd()).resolve()
    registry_path = (
        (project_dir / args.id_registry).resolve()
        if args.id_registry
        else (project_dir / DEFAULT_ID_REGISTRY_FILENAME)
    )

    registry = _load_or_create_registry(registry_path, project_dir.name)
    if registry is None:
        return 1

    paths: list[Path] = args.paths or _default_id_generate_paths(project_dir)
    if not paths:
        print(
            f"ERROR: no source/data directories found under {project_dir}; "
            "pass explicit PATH argument(s).",
            file=sys.stderr,
        )
        return 1

    registry.generate(paths, project_dir)
    for entity_spec in args.entity or []:
        name, _, type_name = entity_spec.partition(":")
        registry.register_entity(name, type_name or "ai_AIPackage")
    registry.save(registry_path)
    print(
        f"pitloom id: wrote {len(registry.files)} file(s) and "
        f"{len(registry.entities)} entit(y/ies) to {registry_path}"
    )
    return 0


def _run_id_import(args: argparse.Namespace) -> int:
    """Run `pitloom id import`."""
    sbom_path: Path = args.sbom.resolve()
    if not sbom_path.exists():
        print(f"ERROR: SBOM file not found: {sbom_path}", file=sys.stderr)
        return 1

    registry_path = (
        args.id_registry.resolve()
        if args.id_registry
        else Path.cwd() / DEFAULT_ID_REGISTRY_FILENAME
    )
    registry = _load_or_create_registry(registry_path, sbom_path.stem)
    if registry is None:
        return 1

    try:
        registry.import_sbom(sbom_path)
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        print(f"ERROR: failed to import SBOM {sbom_path}: {exc}", file=sys.stderr)
        return 1

    registry.save(registry_path)
    print(
        f"pitloom id: imported into {registry_path} "
        f"({len(registry.files)} file(s), {len(registry.entities)} entit(y/ies))"
    )
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
            "and the CLI."
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
        help="Registry file to update.",
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
        help="Registry file to update.",
    )

    id_parser.set_defaults(func=_run_id_command)
