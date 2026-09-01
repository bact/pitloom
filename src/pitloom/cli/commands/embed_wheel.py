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

from pitloom.assemble import (
    ConfigOverrides,
    embed_wheel_sbom,
)
from pitloom.cli.commands.utils import (
    _collect_wheel_paths,
    _print_sbom_output_path,
    cli_error_handler,
    resolve_effective_provenance,
)
from pitloom.cli.commands.validate_wheel import _validate_one_wheel
from pitloom.cli.commands.verify_wheel import _check_one_wheel
from pitloom.cli.options import _resolve_creation_metadata, add_offline_argument
from pitloom.core.config import PitloomConfig
from pitloom.extract.project import read_project


def _report_embed_result(
    arcname: str,
    wheel_name: str,
    removed: tuple[str, ...],
    timestamp_floored: bool = False,
) -> None:
    """Print the embed confirmation, plus one line per notable side effect.

    Shared by ``wheel --embed`` and ``embed-wheel`` so both report results
    identically -- see :func:`_run_wheel_command`/:func:`_run_embed_wheel_command`.
    """
    print(f"pitloom: embedded {arcname} into {wheel_name}")
    for stale_arcname in removed:
        print(
            f"INFO: removed stale SBOM {stale_arcname} from {wheel_name}",
            file=sys.stderr,
        )
    if timestamp_floored:
        print(
            f"INFO: {wheel_name}'s embedded SBOM entry timestamp was before "
            "1980 and was floored to 1980-01-01 (ZIP format limitation); "
            "the SBOM's own 'created' field keeps the true value",
            file=sys.stderr,
        )


def _run_post_embed_checks(
    args: argparse.Namespace, embedded_wheel_path: Path, arcname: str
) -> bool:
    """Run --verify/--validate against the wheel embed_wheel_sbom() just
    modified. Same functions verify-wheel/validate-wheel use standalone,
    chained here like `wheel --embed` chains into the same embed function.
    """
    embedded_basename = arcname.rsplit("/", 1)[-1]
    verify_ok = not args.verify or _check_one_wheel(
        embedded_wheel_path, embedded_basename
    )
    validate_ok = not args.validate or _validate_one_wheel(
        embedded_wheel_path, embedded_basename
    )
    return verify_ok and validate_ok


@cli_error_handler("wheel SBOM embedding failed")
def _run_embed_wheel_command(args: argparse.Namespace) -> int:
    """Embed an SPDX 3 SBOM into one or more built wheels (PEP 770).

    The richer counterpart to ``wheel --embed`` (see :func:`_run_wheel_command`):
    supports multiple wheels, a project directory (Build-type SBOM), a
    pre-generated ``--sbom`` file, and a custom ``--sbom-basename``. Both
    commands converge on :func:`~pitloom.embed.embed_sbom_in_wheel` for
    the actual archive mutation.
    """
    unique_wheels = _collect_wheel_paths(args.wheel_files)
    if not unique_wheels:
        return 1

    if len(unique_wheels) > 1 and args.output is not None:
        print(
            "ERROR: --output cannot be used when embedding multiple wheels",
            file=sys.stderr,
        )
        return 1

    project_dir = args.project_dir
    pitloom_config = PitloomConfig()
    if project_dir is not None:
        proj_path = Path(project_dir).resolve()
        if not proj_path.exists():
            print(
                f"ERROR: project directory not found: {proj_path}",
                file=sys.stderr,
            )
            return 1
        try:
            _, pitloom_config, _ = read_project(proj_path)
            project_dir = proj_path
        except FileNotFoundError:
            print(
                "ERROR: No pyproject.toml or setup.cfg found "
                f"in project directory: {proj_path}",
                file=sys.stderr,
            )
            return 1
    else:
        try:
            _, pitloom_config, _ = read_project(Path.cwd())
            project_dir = Path.cwd()
        except FileNotFoundError:
            pass

    creation = _resolve_creation_metadata(args, pitloom_config)

    overrides = ConfigOverrides(
        enrich=args.enrich,
        extract_file_header=args.extract_file_header,
        content_type=args.content_type,
        content_type_method=args.content_type_method,
        provenance=resolve_effective_provenance(pitloom_config, args),
        offline=args.offline,
    )
    all_ok = True
    for wheel_path in unique_wheels:
        output_path = args.output if len(unique_wheels) == 1 else None
        embedded_wheel_path, arcname, _, removed, floored = embed_wheel_sbom(
            wheel_path,
            project_dir=project_dir,
            pitloom_config=pitloom_config,
            sbom_path=args.sbom,
            output_path=output_path,
            sbom_basename=args.sbom_basename,
            creation_metadata=creation.to_creation_metadata(),
            registry=args.registry,
            overrides=overrides,
        )
        _report_embed_result(arcname, wheel_path.name, removed, floored)
        if output_path is not None:
            _print_sbom_output_path(output_path)

        if not _run_post_embed_checks(args, embedded_wheel_path, arcname):
            all_ok = False
    return 0 if all_ok else 1


def add_parser(subparsers: Any, parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``embed-wheel`` subcommand."""
    # Note: Using 4-space indent
    # 3b. Embed into Wheel: loom embed-wheel <WHEEL_FILES...>
    embed_parser = subparsers.add_parser(
        "embed-wheel",
        parents=[parent_parser],
        help="Embed an SPDX 3 SBOM into one or more built wheels (PEP 770).",
    )
    embed_parser.add_argument(
        "wheel_files",
        type=str,
        nargs="+",
        help="Path(s) or glob pattern(s) of built .whl file(s) to embed the SBOM into.",
    )
    embed_parser.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "Project directory containing pyproject.toml to extract project "
            "metadata, AI models, and file headers from (defaults to cwd)."
        ),
    )
    embed_parser.add_argument(
        "--sbom",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Pre-generated SBOM JSON file to embed directly instead of generating one."
        ),
    )
    embed_parser.add_argument(
        "--sbom-basename",
        type=str,
        default=None,
        metavar="NAME",
        help="Custom basename for the embedded SBOM inside .dist-info/sboms/.",
    )
    embed_parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "After embedding, also run 'verify-wheel' against the result "
            "(PEP 770 location + recommended-extension check)."
        ),
    )
    embed_parser.add_argument(
        "--validate",
        action="store_true",
        help=(
            "After embedding, also run 'validate-wheel' against the result "
            "(schema/SHACL content validation)."
        ),
    )
    add_offline_argument(embed_parser, " during SBOM generation.")
    embed_parser.set_defaults(func=_run_embed_wheel_command)
