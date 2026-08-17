# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pitloom.assemble import (
    generate,
)
from pitloom.cli.commands.utils import cli_error_handler
from pitloom.cli.constants import _SPDX3_JSON_EXT
from pitloom.cli.options import _resolve_common_options


@cli_error_handler("SBOM generation failed")
def _run_generate_command(args: argparse.Namespace) -> int:
    """Smart generate mode."""
    target_path = Path(args.target) if args.target else None
    pitloom_config, creation_metadata, pretty, describe_relationship = _resolve_common_options(
        args, target_dir=target_path
    )
    output_path = args.output
    sbom_json = generate(
        args.target,
        offline=args.offline or None,
        output_path=output_path,
        creation_metadata=creation_metadata,
        pretty=pretty,
        describe_relationship=describe_relationship,
        registry=args.registry,
        provenance=pitloom_config.provenance,
        enrich=args.enrich,
        extract_file_header=args.extract_file_header,
        content_type=args.content_type,
        content_type_method=args.content_type_method,
    )
    if output_path is None:
        fallback_path = Path(f"sbom{_SPDX3_JSON_EXT}")
        fallback_path.write_text(sbom_json, encoding="utf-8")
        print(f"Wrote SBOM to {fallback_path}")
    return 0


def add_parser(subparsers: Any, parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``generate`` subcommand."""
    # Note: Using 4-space indent
    # 1. Smart Entrypoint: loom generate [TARGET]
    gen_parser = subparsers.add_parser(
        "generate",
        parents=[parent_parser],
        help="Generate an SBOM with automatic target detection.",
    )
    gen_parser.add_argument(
        "target",
        type=str,
        nargs="?",
        default=".",
        help="Target path, sdist archive, .whl, model file, HF URL, or 'env'.",
    )
    gen_parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Forbid network access; effect depends on the resolved target -- "
            "HF URL/ID: error, no fetch attempted (no local fallback exists). "
            "project dir / .whl: skip PyPI lookup, no error (local metadata "
            "already covers what it can). "
            "local model file: no-op (no network path exists)."
        ),
    )
    gen_parser.set_defaults(func=_run_generate_command)
