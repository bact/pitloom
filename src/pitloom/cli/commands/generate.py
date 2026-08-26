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
    generate,
)
from pitloom.cli.commands.utils import cli_error_handler, resolve_effective_provenance
from pitloom.cli.options import _resolve_common_options


@cli_error_handler("SBOM generation failed")
def _run_generate_command(args: argparse.Namespace) -> int:
    """Smart generate mode.

    ``-o``/``--output`` is required here (unlike ``project``/``wheel``/
    ``model``/``env``/``enrich``, which each know their target type and
    so have an obvious default filename): ``generate`` dispatches across
    project/wheel/model/env targets, each with a different natural
    default name, so guessing one would be arbitrary. Failing fast is
    more transparent than picking a name the user didn't ask for.
    """
    if args.output is None:
        print(
            "ERROR: -o/--output is required for 'loom generate' "
            "(the target-detection dispatch has no single natural default "
            "filename -- pass -o FILE, or use 'loom project'/'loom wheel'/"
            "'loom model'/'loom env' directly for that target type's own "
            "default).",
            file=sys.stderr,
        )
        return 1

    target_path = Path(args.target) if args.target else None
    pitloom_config, creation_metadata, pretty, describe_relationship = (
        _resolve_common_options(args, target_dir=target_path)
    )
    generate(
        args.target,
        offline=args.offline or None,
        output_path=args.output,
        creation_metadata=creation_metadata,
        pretty=pretty,
        describe_relationship=describe_relationship,
        registry=args.registry,
        update_registry=args.update_registry,
        provenance=resolve_effective_provenance(pitloom_config, args),
        enrich=args.enrich,
        extract_file_header=args.extract_file_header,
        content_type=args.content_type,
        content_type_method=args.content_type_method,
    )
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
