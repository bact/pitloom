# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Any

from pitloom.__about__ import __version__
from pitloom.assemble import (
    generate_model_sbom,
)
from pitloom.cli.options import (
    _resolve_creation_metadata,
    _resolve_hf_output_path,
    _resolve_model_output_path,
)
from pitloom.core.config import PitloomConfig
from pitloom.extract._huggingface import is_huggingface_source, parse_hf_model_id

_SPDX3_JSON_EXT = ".spdx3.json"
_PROJECT_PYPROJECT_SOURCE = "pyproject.toml"
_PROJECT_SETUP_CFG_SOURCE = "setup.cfg"
_PROJECT_SETUP_PY_SOURCE = "setup.py"


def _run_model_command(args: argparse.Namespace) -> int:
    """Generate an AI Model SBOM from a local file or HF repository."""
    target: str = args.target
    try:
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
            model_path: Path = Path(target).resolve()
            if not model_path.exists():
                print(f"ERROR: model file not found: {model_path}", file=sys.stderr)
                return 1
            output_path = _resolve_model_output_path(args.output, model_path)
            if args.verbose:
                print(f"Pitloom version: {__version__}")
                print(f"Model file      : {model_path}")
                print(f"Output path     : {output_path}")
            model_target = model_path

        pitloom_config = PitloomConfig()
        creation = _resolve_creation_metadata(args, pitloom_config)
        effective_pretty = args.pretty if args.pretty is not None else False
        effective_describe = (
            bool(args.describe_relationship)
            if args.describe_relationship is not None
            else False
        )

        generate_model_sbom(
            model_target,
            offline=args.offline or None,
            output_path=output_path,
            creation_metadata=creation.to_creation_metadata(),
            pretty=effective_pretty,
            describe_relationship=effective_describe,
            registry=args.registry,
            enrich=args.enrich,
        )
        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"ERROR: model SBOM generation failed: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1


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
    model_parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Forbid network access; effect depends on the resolved target -- "
            "HF URL/ID: error, no fetch attempted (no local fallback exists). "
            "local model file: no-op (no network path exists)."
        ),
    )
    model_parser.set_defaults(func=_run_model_command)
