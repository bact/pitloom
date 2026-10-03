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
from pitloom._sbom_io import write_sbom_output
from pitloom.assemble import (
    embed_sbom_in_wheel,
    generate_wheel_sbom,
    generate_wheel_sbom_with_metadata,
)
from pitloom.cli.commands._embed_wheel_batch import report_embed_result
from pitloom.cli.commands.utils import _print_sbom_output_path, cli_error_handler
from pitloom.cli.options import (
    add_allow_signed_wheel_argument,
    add_offline_argument,
)
from pitloom.cli.options_config import explicit_config_and_options
from pitloom.core.inert_options import (
    EMBED_STANDALONE,
    EMBEDDED_SBOM_PARAMS,
    INERT,
    WHEEL,
    forward_options,
    settle_inert,
)
from pitloom.core.no_effect import INERT_LOG_PREFIX, warn_no_effect
from pitloom.embed import embed_filename, refuse_unembeddable_wheel
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.extract.wheel import wheel_identity


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

    pitloom_config, options = explicit_config_and_options(args)

    embed = getattr(args, "embed", False)
    if args.allow_signed_wheel and not embed:
        warn_no_effect(
            INERT_LOG_PREFIX,
            wheel_path.name,
            ("--allow-signed-wheel",),
            "without --embed",
        )
    if embed:
        # The same SBOM, and the same warnings, as embed-wheel without a
        # project: canonical, no relationship descriptions, no registry
        # harvest. -o writes a copy of it.
        inert = INERT[EMBED_STANDALONE]
        settle_inert(EMBED_STANDALONE, target, {name: options[name] for name in inert})
        options.update(dict.fromkeys(inert))
        options.update(dict.fromkeys(EMBEDDED_SBOM_PARAMS, False))
    # With --embed, only write a standalone copy if the user explicitly
    # asked for one via -o; embedding into the wheel is the primary
    # output and shouldn't also litter cwd with a same-named file.
    output_path = (
        args.output
        if embed
        else args.output or (Path.cwd() / f"{wheel_path.name}{SPDX3_JSONLD_EXTENSION}")
    )

    if args.verbose:
        print(f"Pitloom version : {__version__}")
        print(f"Wheel file      : {wheel_path}")
        print(f"Output path     : {output_path or '(embedded only)'}")

    if embed:
        # As embed-wheel: refuse before generating (that may run a build).
        refuse_unembeddable_wheel(wheel_path, args.allow_signed_wheel)
    # With --embed, the -o copy is written once the embed has succeeded: a
    # wheel the embed refuses leaves nothing behind.
    sbom_json, wheel_metadata = generate_wheel_sbom_with_metadata(
        wheel_path,
        output_path=None if embed else output_path,
        pitloom_config=pitloom_config,
        # Subject as given, so the warning reads as `loom generate`'s does.
        **forward_options(WHEEL, target, generate_wheel_sbom, options),
    )

    if embed:
        _, arcname, removed, floored = embed_sbom_in_wheel(
            wheel_path,
            sbom_json,
            sbom_filename=embed_filename(
                pitloom_config.sbom_basename if pitloom_config else None
            ),
            # Already read (and warned about) by the generation above.
            identity=wheel_identity(wheel_metadata),
            allow_signed_wheel=args.allow_signed_wheel,
        )
        write_sbom_output(sbom_json, output_path)
        report_embed_result(arcname, wheel_path.name, removed, floored)

    if output_path is not None:
        _print_sbom_output_path(output_path)

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
    add_allow_signed_wheel_argument(wheel_parser)
    add_offline_argument(
        wheel_parser,
        " -- skip PyPI lookup, no error (local metadata already covers what it can).",
    )
    wheel_parser.set_defaults(func=_run_wheel_command)
