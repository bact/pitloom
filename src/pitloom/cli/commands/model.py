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
    generate_model_sbom,
)
from pitloom.cli.commands.utils import (
    _print_sbom_output_path,
    cli_error_handler,
    existing_model_path,
)
from pitloom.cli.options import (
    _resolve_hf_output_path,
    _resolve_model_output_path,
    add_offline_argument,
)
from pitloom.cli.options_config import explicit_config_and_options
from pitloom.core.inert_options import HF, MODEL_FILE, forward_options
from pitloom.extract.remote import is_huggingface_source, parse_hf_model_id


@cli_error_handler("model command failed")
def _run_model_command(args: argparse.Namespace) -> int:
    """Generate an AI Model SBOM from a local file or HF repository."""
    target: str = args.target
    model_target: Path | str
    if is_huggingface_source(target):
        model_id = parse_hf_model_id(target)
        if model_id is None:
            print(
                f"ERROR: not a valid Hugging Face URL or model ID: {target!r}",
                file=sys.stderr,
            )
            return 1
        output_path = _resolve_hf_output_path(args.output, model_id)
        if args.verbose:
            print(f"Pitloom version    : {__version__}")
            print(f"Hugging Face model : {model_id}")
            print(f"Output path        : {output_path}")
        model_target = model_id
    else:
        # The path as given goes to the generator, so its log lines name
        # the file as the user wrote it.
        given_path = Path(target)
        model_path: Path = given_path.resolve()
        opened_path = existing_model_path(given_path)
        if opened_path is None:
            print(f"ERROR: model file not found: {model_path}", file=sys.stderr)
            return 1
        output_path = _resolve_model_output_path(args.output, model_path)
        if args.verbose:
            print(f"Pitloom version: {__version__}")
            print(f"Model file      : {model_path}")
            print(f"Output path     : {output_path}")
        model_target = opened_path

    pitloom_config, options = explicit_config_and_options(args)
    # Same subject generate_model_sbom() settles its own options under.
    kind = MODEL_FILE if isinstance(model_target, Path) else HF
    generate_model_sbom(
        model_target,
        output_path=output_path,
        pitloom_config=pitloom_config,
        **forward_options(kind, str(model_target), generate_model_sbom, options),
    )
    _print_sbom_output_path(output_path)
    return 0


def add_parser(subparsers: Any, parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``model`` subcommand."""
    # Note: Using 4-space indent
    # 4. AI Model Asset: loom model <SOURCE> [--offline]
    model_parser = subparsers.add_parser(
        "model",
        parents=[parent_parser],
        help="Generate an AI Model SBOM (AIBOM) from a local file or HF repo.",
    )
    model_parser.add_argument(
        "target",
        type=str,
        help="Path to local AI model file or Hugging Face URL / model ID.",
    )
    add_offline_argument(
        model_parser,
        "; effect depends on the resolved target -- "
        "HF URL/ID: error, no fetch attempted (no local fallback exists). "
        "local model file: no-op (no network path exists).",
    )
    model_parser.set_defaults(func=_run_model_command)
