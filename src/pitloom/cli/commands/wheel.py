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

from pitloom.__about__ import __version__
from pitloom.assemble import (
    embed_sbom_in_wheel,
    generate_wheel_sbom,
)
from pitloom.cli.commands.embed_wheel import _report_embed_result
from pitloom.cli.commands.utils import cli_error_handler
from pitloom.cli.constants import _SPDX3_JSON_EXT
from pitloom.cli.options import _resolve_common_options


@cli_error_handler("wheel command failed")
def _run_wheel_command(args: argparse.Namespace) -> int:
    """Generate an Analyzed SBOM from a built wheel.

    ``--embed`` here is deliberately narrower than the ``embed-wheel``
    command (see :func:`_run_embed_wheel_command`): always the wheel's own
    Analyzed SBOM, one wheel, no project-directory scanning. Both paths
    converge on :func:`~pitloom.embed.embed_sbom_in_wheel` for the actual
    archive mutation (RECORD update, stale-entry cleanup, atomic
    rewrite), so a fix there benefits both without needing to be
    duplicated -- only SBOM *content* generation differs by design.
    """
    target: str = args.target
    wheel_path: Path = Path(target).resolve()
    if not wheel_path.exists():
        print(f"ERROR: wheel file not found: {wheel_path}", file=sys.stderr)
        return 1

    pitloom_config, creation, effective_pretty, effective_describe = (
        _resolve_common_options(args, load_project=False)
    )

    embed = getattr(args, "embed", False)
    # With --embed, only write a standalone copy if the user explicitly
    # asked for one via -o; embedding into the wheel is the primary
    # output and shouldn't also litter cwd with a same-named file.
    output_path = (
        args.output
        if embed
        else args.output or (Path.cwd() / f"{wheel_path.name}{_SPDX3_JSON_EXT}")
    )

    if args.verbose:
        print(f"Pitloom version : {__version__}")
        print(f"Wheel file      : {wheel_path}")
        print(f"Output path     : {output_path or '(embedded only)'}")

    sbom_json = generate_wheel_sbom(
        wheel_path,
        output_path=output_path,
        creation_metadata=creation,
        pretty=effective_pretty,
        describe_relationship=effective_describe,
        registry=args.registry,
        provenance=pitloom_config.provenance,
        offline=args.offline or None,
    )

    if embed:
        _, arcname, removed, floored = embed_sbom_in_wheel(wheel_path, sbom_json)
        _report_embed_result(arcname, wheel_path.name, removed, floored)

    return 0


def add_parser(subparsers: Any, parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``wheel`` subcommand."""
    # Note: Using 4-space indent
    # 3. Built Wheel: loom wheel <WHEEL_FILE>
    wheel_parser = subparsers.add_parser(
        "wheel",
        parents=[parent_parser],
        help="Generate an Analyzed SBOM from a built wheel (.whl).",
    )
    wheel_parser.add_argument(
        "target",
        type=str,
        help="Path to the built .whl file.",
    )
    wheel_parser.add_argument(
        "--embed",
        action="store_true",
        help="Embed the generated SBOM directly into the wheel archive (PEP 770).",
    )
    wheel_parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Forbid network access -- skip PyPI lookup, no error "
            "(local metadata already covers what it can)."
        ),
    )
    wheel_parser.set_defaults(func=_run_wheel_command)
