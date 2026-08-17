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

from pitloom.ids import (
    DEFAULT_REGISTRY_FILENAME,
    _default_ids_generate_paths,
    _load_or_create_registry,
)


def _run_ids_generate(args: argparse.Namespace) -> int:
    """Run `pitloom ids generate`."""
    project_dir: Path = (args.project_dir or Path.cwd()).resolve()
    registry_path = (
        (project_dir / args.registry).resolve()
        if args.registry
        else (project_dir / DEFAULT_REGISTRY_FILENAME)
    )

    registry = _load_or_create_registry(registry_path, project_dir.name)
    if registry is None:
        return 1

    paths: list[Path] = args.paths or _default_ids_generate_paths(project_dir)
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
        f"pitloom ids: wrote {len(registry.files)} file(s) and "
        f"{len(registry.entities)} entit(y/ies) to {registry_path}"
    )
    return 0


def _run_ids_import(args: argparse.Namespace) -> int:
    """Run `pitloom ids import`."""
    sbom_path: Path = args.sbom.resolve()
    if not sbom_path.exists():
        print(f"ERROR: SBOM file not found: {sbom_path}", file=sys.stderr)
        return 1

    registry_path = (
        args.registry.resolve()
        if args.registry
        else Path.cwd() / DEFAULT_REGISTRY_FILENAME
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
        f"pitloom ids: imported into {registry_path} "
        f"({len(registry.files)} file(s), {len(registry.entities)} entit(y/ies))"
    )
    return 0


def _run_ids_cli(args: argparse.Namespace) -> int:
    """Dispatch `pitloom ids <command> ...` arguments."""
    if args.ids_command == "generate":
        return _run_ids_generate(args)
    if args.ids_command == "import":
        return _run_ids_import(args)
    return 1


def add_parser(subparsers: Any, _parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``ids`` subcommand to the main parser."""
    ids_parser = subparsers.add_parser(
        "ids",
        help="Manage the Loom ID registry.",
        description=(
            "Manage the Loom ID registry, a stable file/entity -> SPDX ID "
            "registry consulted by 'pitloom.loom', the Hatchling build hook, "
            "and the CLI."
        ),
    )
    ids_subparsers = ids_parser.add_subparsers(dest="ids_command", required=True)

    gen_parser = ids_subparsers.add_parser(
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
        "--registry",
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

    imp_parser = ids_subparsers.add_parser(
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
        "--registry",
        type=Path,
        default=None,
        metavar="FILE",
        help="Registry file to update.",
    )

    ids_parser.set_defaults(func=_run_ids_cli)
