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
    enrich_model,
)
from pitloom.cli.options import _resolve_creation_metadata
from pitloom.core.config import PitloomConfig

_SPDX3_JSON_EXT = ".spdx3.json"
_PROJECT_PYPROJECT_SOURCE = "pyproject.toml"
_PROJECT_SETUP_CFG_SOURCE = "setup.cfg"
_PROJECT_SETUP_PY_SOURCE = "setup.py"


def _run_enrich_command(args: argparse.Namespace) -> int:
    """Run enrichment only for a local AI model file; write a fragment."""
    target: str = args.target
    try:
        model_path: Path = Path(target).resolve()
        if not model_path.exists():
            print(f"ERROR: model file not found: {model_path}", file=sys.stderr)
            return 1

        pitloom_config = PitloomConfig()
        creation = _resolve_creation_metadata(args, pitloom_config)
        effective_pretty = args.pretty if args.pretty is not None else False

        output_path = args.output or (
            Path.cwd() / f"{model_path.name}.enrich{_SPDX3_JSON_EXT}"
        )

        if args.verbose:
            print(f"Pitloom version: {__version__}")
            print(f"Model file      : {model_path}")
            print(f"Output path     : {output_path}")
            if args.project_dir:
                print(f"Project dir     : {args.project_dir}")

        enrich_model(
            model_path,
            output_path=output_path,
            creation_metadata=creation.to_creation_metadata(),
            pretty=effective_pretty,
            enrich=args.enrich,
            project_target=args.project_dir,
            registry=args.registry,
        )
        print(f"Enrichment fragment written to: {output_path}")
        print(
            "Register it under [tool.pitloom.fragment] and re-run "
            "'loom project'/'loom generate' to merge it into a base SBOM."
        )
        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"ERROR: enrichment fragment generation failed: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1


def add_parser(subparsers: Any, parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``enrich`` subcommand."""
    # Note: Using 4-space indent
    # 4b. Enrichment only: loom enrich <SOURCE>
    enrich_parser = subparsers.add_parser(
        "enrich",
        parents=[parent_parser],
        help=(
            "Run enrichment only for a local AI model file; write a "
            "standalone fragment for merging into a base SBOM."
        ),
    )
    enrich_parser.add_argument(
        "target",
        type=str,
        help="Path to a local AI model file.",
    )
    enrich_parser.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "Project root the model belongs to, when the fragment will "
            "merge into a 'loom project'/'loom generate <dir>'-generated "
            "base document rather than a 'loom model'-generated one. "
            "Required for a correct merge in that case -- project-level "
            "and single-model documents assign the model's ai_AIPackage "
            "a different id."
        ),
    )
    enrich_parser.set_defaults(func=_run_enrich_command)
